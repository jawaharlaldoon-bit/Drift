"""Durable incident and action state with an in-memory development backend."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from copy import deepcopy
from functools import lru_cache

from .config import get_settings
from .models import ActionReceipt, WorkflowEvent, WorkflowRun, utc_now


class IncidentStore(ABC):
    @abstractmethod
    async def claim(self, run: WorkflowRun) -> tuple[bool, WorkflowRun]: ...

    @abstractmethod
    async def save(self, run: WorkflowRun) -> None: ...

    @abstractmethod
    async def get(self, incident_id: str) -> WorkflowRun | None: ...

    @abstractmethod
    async def list_runs(self, limit: int = 50) -> list[WorkflowRun]: ...

    @abstractmethod
    async def append_event(self, event: WorkflowEvent) -> None: ...

    @abstractmethod
    async def get_events(self, incident_id: str) -> list[WorkflowEvent]: ...

    @abstractmethod
    async def reserve_action(self, incident_id: str, receipt: ActionReceipt) -> ActionReceipt: ...

    @abstractmethod
    async def complete_action(self, incident_id: str, receipt: ActionReceipt) -> None: ...


class MemoryIncidentStore(IncidentStore):
    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        self._source_keys: dict[str, str] = {}
        self._events: dict[str, list[WorkflowEvent]] = {}
        self._actions: dict[tuple[str, str], ActionReceipt] = {}
        self._lock = asyncio.Lock()

    async def claim(self, run: WorkflowRun) -> tuple[bool, WorkflowRun]:
        source_key = f"{run.source}:{run.source_event_id}"
        async with self._lock:
            if source_key in self._source_keys:
                existing = self._runs[self._source_keys[source_key]]
                return False, deepcopy(existing)
            self._source_keys[source_key] = run.incident_id
            self._runs[run.incident_id] = deepcopy(run)
            return True, deepcopy(run)

    async def save(self, run: WorkflowRun) -> None:
        async with self._lock:
            run.updated_at = utc_now()
            self._runs[run.incident_id] = deepcopy(run)

    async def get(self, incident_id: str) -> WorkflowRun | None:
        async with self._lock:
            run = self._runs.get(incident_id)
            return deepcopy(run) if run else None

    async def list_runs(self, limit: int = 50) -> list[WorkflowRun]:
        async with self._lock:
            runs = sorted(self._runs.values(), key=lambda item: item.updated_at, reverse=True)
            return deepcopy(runs[:limit])

    async def append_event(self, event: WorkflowEvent) -> None:
        async with self._lock:
            self._events.setdefault(event.incident_id, []).append(deepcopy(event))

    async def get_events(self, incident_id: str) -> list[WorkflowEvent]:
        async with self._lock:
            return deepcopy(self._events.get(incident_id, []))

    async def reserve_action(self, incident_id: str, receipt: ActionReceipt) -> ActionReceipt:
        key = (incident_id, receipt.idempotency_key)
        async with self._lock:
            existing = self._actions.get(key)
            if existing:
                return deepcopy(existing)
            self._actions[key] = deepcopy(receipt)
            return deepcopy(receipt)

    async def complete_action(self, incident_id: str, receipt: ActionReceipt) -> None:
        key = (incident_id, receipt.idempotency_key)
        async with self._lock:
            self._actions[key] = deepcopy(receipt)
            run = self._runs.get(incident_id)
            if run:
                replaced = False
                for index, current in enumerate(run.actions):
                    if current.idempotency_key == receipt.idempotency_key:
                        run.actions[index] = deepcopy(receipt)
                        replaced = True
                        break
                if not replaced:
                    run.actions.append(deepcopy(receipt))


class FirestoreIncidentStore(IncidentStore):
    """Firestore adapter using document preconditions for event/action idempotency."""

    def __init__(self) -> None:
        from google.cloud import firestore

        settings = get_settings()
        self._client = firestore.Client(project=settings.google_cloud_project)
        self._collection = self._client.collection(settings.firestore_collection)
        self._claims = self._client.collection(f"{settings.firestore_collection}_claims")

    @staticmethod
    def _run_from_snapshot(snapshot) -> WorkflowRun | None:
        return WorkflowRun.model_validate(snapshot.to_dict()) if snapshot.exists else None

    async def claim(self, run: WorkflowRun) -> tuple[bool, WorkflowRun]:
        from google.cloud import firestore

        source_key = f"{run.source}:{run.source_event_id}"

        def operation():
            claim_ref = self._claims.document(source_key)
            run_ref = self._collection.document(run.incident_id)
            transaction = self._client.transaction()

            @firestore.transactional
            def claim_once(txn):
                claim_snapshot = claim_ref.get(transaction=txn)
                if claim_snapshot.exists:
                    claim = claim_snapshot.to_dict() or {}
                    existing_ref = self._collection.document(
                        claim.get("incident_id", run.incident_id)
                    )
                    existing = existing_ref.get(transaction=txn)
                    return False, self._run_from_snapshot(existing) or run

                # The claim and initial run are committed together, so a crash cannot
                # leave an event permanently claimed without its workflow record.
                txn.create(claim_ref, {"incident_id": run.incident_id})
                txn.create(run_ref, run.model_dump(mode="json"))
                return True, run

            return claim_once(transaction)

        return await asyncio.to_thread(operation)

    async def save(self, run: WorkflowRun) -> None:
        run.updated_at = utc_now()
        await asyncio.to_thread(
            self._collection.document(run.incident_id).set, run.model_dump(mode="json")
        )

    async def get(self, incident_id: str) -> WorkflowRun | None:
        snapshot = await asyncio.to_thread(self._collection.document(incident_id).get)
        return self._run_from_snapshot(snapshot)

    async def list_runs(self, limit: int = 50) -> list[WorkflowRun]:
        from google.cloud.firestore_v1 import Query

        query = self._collection.order_by("updated_at", direction=Query.DESCENDING).limit(limit)
        snapshots = await asyncio.to_thread(lambda: list(query.stream()))
        return [WorkflowRun.model_validate(item.to_dict()) for item in snapshots]

    async def append_event(self, event: WorkflowEvent) -> None:
        ref = self._collection.document(event.incident_id).collection("events").document()
        await asyncio.to_thread(ref.set, event.model_dump(mode="json"))

    async def get_events(self, incident_id: str) -> list[WorkflowEvent]:
        ref = self._collection.document(incident_id).collection("events").order_by("occurred_at")
        snapshots = await asyncio.to_thread(lambda: list(ref.stream()))
        return [WorkflowEvent.model_validate(item.to_dict()) for item in snapshots]

    async def reserve_action(self, incident_id: str, receipt: ActionReceipt) -> ActionReceipt:
        from google.api_core.exceptions import AlreadyExists

        ref = self._collection.document(incident_id).collection("actions").document(
            receipt.idempotency_key
        )
        try:
            await asyncio.to_thread(ref.create, receipt.model_dump(mode="json"))
            return receipt
        except AlreadyExists:
            snapshot = await asyncio.to_thread(ref.get)
            return ActionReceipt.model_validate(snapshot.to_dict())

    async def complete_action(self, incident_id: str, receipt: ActionReceipt) -> None:
        ref = self._collection.document(incident_id).collection("actions").document(
            receipt.idempotency_key
        )
        await asyncio.to_thread(ref.set, receipt.model_dump(mode="json"))


@lru_cache
def get_store() -> IncidentStore:
    settings = get_settings()
    if settings.state_backend == "firestore":
        return FirestoreIncidentStore()
    return MemoryIncidentStore()


def reset_store() -> None:
    get_store.cache_clear()
