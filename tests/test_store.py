from __future__ import annotations

from drift.demo import build_demo_incident
from drift.models import ActionReceipt, ActionStatus, WorkflowRun
from drift.store import MemoryIncidentStore


def make_run(settings, event_id="event-1"):
    event = build_demo_incident(settings, event_id=event_id)
    return WorkflowRun(
        incident_id=event.incident_id,
        source_event_id=event.event_id,
        source=event.source,
        service=event.service,
        trace_id=event.trace_id,
        event=event,
    )


async def test_claim_is_idempotent(settings):
    store = MemoryIncidentStore()
    run = make_run(settings)
    claimed, _ = await store.claim(run)
    duplicate, existing = await store.claim(make_run(settings))
    assert claimed is True
    assert duplicate is False
    assert existing.incident_id == run.incident_id


async def test_action_receipts_are_idempotent(settings):
    store = MemoryIncidentStore()
    run = make_run(settings)
    await store.claim(run)
    receipt = ActionReceipt(
        action_kind="github_issue",
        idempotency_key="source:event:github_issue",
        request_fingerprint="abc",
    )
    first = await store.reserve_action(run.incident_id, receipt)
    first.status = ActionStatus.SUCCEEDED
    await store.complete_action(run.incident_id, first)
    duplicate = await store.reserve_action(run.incident_id, receipt)
    assert duplicate.status is ActionStatus.SUCCEEDED
