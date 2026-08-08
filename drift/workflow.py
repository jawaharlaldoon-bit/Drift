"""Deterministic Taskmaster state machine and proof-carrying remediation workflow."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from time import perf_counter

from pydantic import HttpUrl

from .config import Settings, get_settings
from .events import EventBus, bus
from .integrations import (
    ExternalResult,
    GitHubClient,
    IntegrationError,
    SlackClient,
    completed_slack_payload,
    detected_slack_payload,
)
from .models import (
    ActionReceipt,
    ActionStatus,
    IncidentEvent,
    Route,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStage,
    utc_now,
)
from .reasoning import Reasoner, get_reasoner
from .retry import with_retry
from .security import fingerprint, redact, validate_proposal, validate_target
from .store import IncidentStore, get_store
from .telemetry import structured_log
from .validator import SandboxValidator


class DriftWorkflow:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        store: IncidentStore | None = None,
        reasoner: Reasoner | None = None,
        github: GitHubClient | None = None,
        slack: SlackClient | None = None,
        validator: SandboxValidator | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or get_store()
        self.reasoner = reasoner or get_reasoner(self.settings)
        self.github = github or GitHubClient(self.settings)
        self.slack = slack or SlackClient(self.settings)
        self.validator = validator or SandboxValidator(self.settings)
        self.bus = event_bus or bus

    async def process(self, event: IncidentEvent) -> tuple[WorkflowRun, bool]:
        run = WorkflowRun(
            incident_id=event.incident_id,
            source_event_id=event.event_id,
            source=event.source,
            service=event.service,
            trace_id=event.trace_id,
            demo=event.demo,
            event=event,
        )
        claimed, run = await self.store.claim(run)
        if not claimed:
            return run, True

        try:
            await self._emit(run, WorkflowStage.INGESTED, "Incident accepted", event.source)
            validate_target(event, self.settings)
            await self._emit(
                run,
                WorkflowStage.DEDUPLICATED,
                "Event identity claimed",
                f"{event.source}:{event.event_id}",
            )

            analysis = await self.reasoner.analyze(event)
            if (
                analysis.triage.route is Route.REMEDIATE
                and analysis.triage.confidence < self.settings.triage_confidence_threshold
            ):
                analysis.triage.route = Route.DOCUMENT
                analysis.triage.summary += " Confidence was below the remediation threshold."
            run.triage = analysis.triage
            await self._emit(
                run,
                WorkflowStage.TRIAGED,
                f"{analysis.triage.severity.value.title()} incident triaged",
                analysis.triage.summary,
                {
                    "category": analysis.triage.category.value,
                    "confidence": analysis.triage.confidence,
                    "route": analysis.triage.route.value,
                    "evidence": analysis.triage.evidence,
                },
            )
            run.investigation = analysis.investigation
            await self._emit(
                run,
                WorkflowStage.INVESTIGATED,
                "Root cause isolated",
                analysis.investigation.root_cause,
                {"causal_factors": analysis.investigation.causal_factors},
            )
            await self._emit(
                run,
                WorkflowStage.ROUTED,
                f"Routed to {analysis.triage.route.value}",
                f"Confidence {analysis.triage.confidence:.0%}; threshold "
                f"{self.settings.triage_confidence_threshold:.0%}.",
            )

            if analysis.triage.route is Route.IGNORE:
                await self._emit(
                    run, WorkflowStage.IGNORED, "No external action required", analysis.triage.summary
                )
                return run, False

            issue = await self._action(
                run,
                "github_issue",
                {"incident_id": run.incident_id, "summary": analysis.triage.summary},
                lambda: self.github.create_issue(
                    title=f"[Drift] {analysis.triage.severity.value}: {event.service} incident",
                    body=self._issue_body(run),
                    labels=[],
                ),
            )
            if issue.status is not ActionStatus.SUCCEEDED or not issue.external_url:
                raise RuntimeError("GitHub issue creation failed; remediation cannot be anchored")
            run.issue_url = issue.external_url
            await self._emit(
                run,
                WorkflowStage.ISSUE_CREATED,
                "GitHub incident created",
                str(issue.external_url),
            )
            await self._action(
                run,
                "slack_detected",
                {"incident_id": run.incident_id, "issue": str(issue.external_url)},
                lambda: self.slack.post(
                    detected_slack_payload(
                        run.incident_id,
                        event.service,
                        analysis.triage.severity.value,
                        str(issue.external_url),
                    )
                ),
                required=False,
            )

            if analysis.triage.route is Route.DOCUMENT:
                await self._emit(
                    run,
                    WorkflowStage.DOCUMENTED,
                    "Incident documented for human investigation",
                    "No repository change was authorized.",
                )
                return run, False

            if analysis.proposal is None:
                raise RuntimeError("remediation route did not produce a candidate")
            validate_proposal(analysis.proposal, event, self.settings)
            run.proposal = analysis.proposal
            await self._emit(
                run,
                WorkflowStage.CANDIDATE_GENERATED,
                "Constrained candidate generated",
                analysis.proposal.rationale,
                {
                    "target_path": analysis.proposal.target_path,
                    "risk": analysis.proposal.risk,
                    "diff": analysis.proposal.unified_diff,
                    "policy_review": analysis.policy_review,
                },
            )
            run.validation = await self.validator.validate(event, analysis.proposal)
            await self._emit(
                run,
                WorkflowStage.VALIDATED,
                "Replay gate passed" if run.validation.passed else "Replay gate blocked the patch",
                run.validation.gate_reason,
                {
                    "before_pass_rate": run.validation.before_pass_rate,
                    "after_pass_rate": run.validation.after_pass_rate,
                    "cases": len(run.validation.cases),
                },
            )
            if not run.validation.passed:
                await self._action(
                    run,
                    "slack_final",
                    {"incident_id": run.incident_id, "passed": False},
                    lambda: self.slack.post(
                        completed_slack_payload(
                            run.incident_id,
                            passed=False,
                            pull_request_url=None,
                            issue_url=str(run.issue_url),
                        )
                    ),
                    required=False,
                )
                await self._emit(
                    run,
                    WorkflowStage.DOCUMENTED,
                    "Candidate blocked; issue retained",
                    "No branch or pull request was created.",
                )
                return run, False

            run.branch_name = f"drift/incident-{run.incident_id.removeprefix('inc-')}"
            branch_name = run.branch_name
            proposal = run.proposal
            assert branch_name is not None and proposal is not None
            commit = await self._action(
                run,
                "github_branch_commit",
                {
                    "branch": branch_name,
                    "path": proposal.target_path,
                    "content_hash": fingerprint(proposal.replacement_content),
                },
                lambda: self.github.create_branch_and_commit(
                    branch=branch_name,
                    path=proposal.target_path,
                    content=proposal.replacement_content,
                    message=f"fix: contain {run.incident_id}",
                    expected_sha256=proposal.baseline_sha256,
                ),
            )
            if commit.status is not ActionStatus.SUCCEEDED:
                raise RuntimeError("validated candidate could not be committed")
            pull_request = await self._action(
                run,
                "github_draft_pr",
                {
                    "branch": branch_name,
                    "issue": str(run.issue_url),
                    "validation": run.validation.model_dump(mode="json"),
                },
                lambda: self.github.create_draft_pull_request(
                    title=f"[Drift] Contain {event.service} incident {run.incident_id}",
                    body=self._pull_request_body(run),
                    branch=branch_name,
                ),
            )
            if pull_request.status is not ActionStatus.SUCCEEDED or not pull_request.external_url:
                raise RuntimeError("draft pull request creation failed")
            run.pull_request_url = pull_request.external_url
            await self._emit(
                run,
                WorkflowStage.PR_OPENED,
                "Draft pull request opened",
                str(run.pull_request_url),
            )
            await self._action(
                run,
                "slack_final",
                {"incident_id": run.incident_id, "pr": str(run.pull_request_url)},
                lambda: self.slack.post(
                    completed_slack_payload(
                        run.incident_id,
                        passed=True,
                        pull_request_url=str(run.pull_request_url),
                        issue_url=str(run.issue_url),
                    )
                ),
                required=False,
            )
            await self._emit(
                run,
                WorkflowStage.NOTIFIED,
                "Outcome sent to the incident channel",
                "Notification failures are recorded without rolling back the pull request.",
            )
            await self._emit(
                run,
                WorkflowStage.AWAITING_REVIEW,
                "Awaiting human merge",
                "Drift never merges production changes automatically.",
            )
            return run, False
        except Exception as exc:  # noqa: BLE001 - workflow boundary records all failures safely
            run.failure = redact(f"{type(exc).__name__}: {exc}")
            await self._emit(
                run, WorkflowStage.FAILED, "Workflow stopped safely", run.failure
            )
            return run, False

    async def _emit(
        self,
        run: WorkflowRun,
        stage: WorkflowStage,
        title: str,
        detail: str = "",
        payload: dict | None = None,
    ) -> None:
        run.stage = stage
        run.updated_at = utc_now()
        event = WorkflowEvent(
            incident_id=run.incident_id,
            stage=stage,
            title=title,
            detail=redact(detail),
            payload=payload or {},
        )
        await self.store.save(run)
        await self.store.append_event(event)
        await self.bus.publish(event)
        structured_log(
            title,
            incident_id=run.incident_id,
            stage=stage.value,
            action_id=None,
            duration_ms=0,
            retry_count=0,
            sanitized_error=run.failure if stage is WorkflowStage.FAILED else None,
        )

    async def _action(
        self,
        run: WorkflowRun,
        kind: str,
        payload: dict,
        operation: Callable[[], Awaitable[ExternalResult]],
        *,
        required: bool = True,
    ) -> ActionReceipt:
        key = f"{run.source}:{run.source_event_id}:{kind}"
        receipt = ActionReceipt(
            action_kind=kind,
            idempotency_key=key,
            request_fingerprint=fingerprint(json.dumps(payload, sort_keys=True, default=str)),
        )
        reserved = await self.store.reserve_action(run.incident_id, receipt)
        if reserved.status is ActionStatus.SUCCEEDED:
            self._upsert_run_action(run, reserved)
            return reserved
        started = perf_counter()
        attempt_count = 0

        async def counted_operation() -> ExternalResult:
            nonlocal attempt_count
            attempt_count += 1
            return await operation()

        caught_error: Exception | None = None
        try:
            result, attempts = await with_retry(
                counted_operation,
                attempts=3,
                retryable=lambda error: not isinstance(error, IntegrationError) or error.retryable,
            )
            receipt.status = ActionStatus.SUCCEEDED
            receipt.attempts = attempts
            receipt.external_id = result.external_id
            receipt.external_url = HttpUrl(result.url)
        except Exception as exc:  # noqa: BLE001 - external boundary is recorded and contained
            caught_error = exc
            receipt.status = ActionStatus.FAILED
            receipt.attempts = attempt_count
            receipt.sanitized_error = redact(f"{type(exc).__name__}: {exc}")
        receipt.completed_at = utc_now()
        await self.store.complete_action(run.incident_id, receipt)
        self._upsert_run_action(run, receipt)
        await self.store.save(run)
        structured_log(
            f"External action {receipt.status.value}",
            severity="ERROR" if receipt.status is ActionStatus.FAILED else "INFO",
            incident_id=run.incident_id,
            stage=run.stage.value,
            action_id=receipt.idempotency_key,
            action_kind=kind,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            retry_count=max(0, receipt.attempts - 1),
            sanitized_error=receipt.sanitized_error,
        )
        if caught_error is not None and required:
            raise caught_error
        return receipt

    @staticmethod
    def _upsert_run_action(run: WorkflowRun, receipt: ActionReceipt) -> None:
        for index, current in enumerate(run.actions):
            if current.idempotency_key == receipt.idempotency_key:
                run.actions[index] = receipt
                return
        run.actions.append(receipt)

    @staticmethod
    def _issue_body(run: WorkflowRun) -> str:
        assert run.triage and run.investigation
        evidence = "\n".join(f"- {item}" for item in run.triage.evidence)
        factors = "\n".join(f"- {item}" for item in run.investigation.causal_factors)
        return f"""## Drift incident `{run.incident_id}`

**Service:** `{run.service}`  
**Trace:** `{run.trace_id}`  
**Severity:** `{run.triage.severity.value}`  
**Confidence:** `{run.triage.confidence:.0%}`

### Summary

{run.triage.summary}

### Evidence

{evidence}

### Root cause

{run.investigation.root_cause}

{factors}

Drift will attach a draft pull request only after live replay validation passes.
"""

    @staticmethod
    def _pull_request_body(run: WorkflowRun) -> str:
        assert run.proposal and run.validation and run.issue_url
        cases = "\n".join(
            f"- {'✅' if case.after_passed else '❌'} `{case.name}`: "
            f"before={'pass' if case.before_passed else 'fail'}, "
            f"after={'pass' if case.after_passed else 'fail'}"
            for case in run.validation.cases
        )
        return f"""## Proof-carrying remediation

Linked incident: {run.issue_url}

### Why this change

{run.proposal.rationale}

### Validation

- Baseline pass rate: **{run.validation.before_pass_rate:.0%}**
- Candidate pass rate: **{run.validation.after_pass_rate:.0%}**
- Gate: **PASSED**

{cases}

### Human boundary

This pull request is intentionally a draft. Drift does not merge or deploy production changes.
"""
