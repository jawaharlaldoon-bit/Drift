from __future__ import annotations

from drift.demo import build_demo_incident
from drift.events import EventBus
from drift.integrations import GitHubClient, IntegrationError, SlackClient
from drift.models import ValidationReport, WorkflowStage
from drift.store import MemoryIncidentStore
from drift.workflow import DriftWorkflow


def workflow(settings, **overrides):
    return DriftWorkflow(
        settings=settings,
        store=overrides.pop("store", MemoryIncidentStore()),
        event_bus=EventBus(),
        **overrides,
    )


async def test_complete_demo_creates_proof_carrying_pr(settings):
    run, duplicate = await workflow(settings).process(build_demo_incident(settings, event_id="e2e"))
    assert duplicate is False
    assert run.stage is WorkflowStage.AWAITING_REVIEW
    assert run.issue_url is not None
    assert run.pull_request_url is not None
    assert run.validation and run.validation.passed
    assert [action.action_kind for action in run.actions] == [
        "github_issue",
        "slack_detected",
        "github_branch_commit",
        "github_draft_pr",
        "slack_final",
    ]
    assert all(action.status.value == "succeeded" for action in run.actions)


async def test_duplicate_delivery_returns_existing_run_without_new_actions(settings):
    store = MemoryIncidentStore()
    engine = workflow(settings, store=store)
    event = build_demo_incident(settings, event_id="duplicate")
    first, first_duplicate = await engine.process(event)
    second, second_duplicate = await engine.process(event)
    assert first_duplicate is False
    assert second_duplicate is True
    assert second.incident_id == first.incident_id
    assert len(second.actions) == len(first.actions)


async def test_non_actionable_event_is_ignored(settings):
    event = build_demo_incident(settings, event_id="ignore")
    event.output_text = event.expected_behavior
    event.tool_events = []
    run, _ = await workflow(settings).process(event)
    assert run.stage is WorkflowStage.IGNORED
    assert run.actions == []


class BlockingValidator:
    async def validate(self, event, proposal):
        return ValidationReport(
            passed=False,
            before_pass_rate=0,
            after_pass_rate=0.75,
            gate_reason="one adversarial case failed",
            cases=[],
        )


async def test_failed_validation_blocks_branch_and_pr(settings):
    run, _ = await workflow(settings, validator=BlockingValidator()).process(
        build_demo_incident(settings, event_id="blocked")
    )
    assert run.stage is WorkflowStage.DOCUMENTED
    assert run.issue_url is not None
    assert run.pull_request_url is None
    kinds = [action.action_kind for action in run.actions]
    assert "github_branch_commit" not in kinds
    assert "github_draft_pr" not in kinds
    assert kinds.count("slack_final") == 1


class FailingSlack(SlackClient):
    async def post(self, payload):
        raise IntegrationError("Slack rejected the message", status_code=400)


async def test_slack_failure_does_not_rollback_pull_request(settings):
    run, _ = await workflow(settings, slack=FailingSlack(settings)).process(
        build_demo_incident(settings, event_id="slack-fails")
    )
    assert run.stage is WorkflowStage.AWAITING_REVIEW
    assert run.pull_request_url is not None
    failures = [item for item in run.actions if item.action_kind.startswith("slack")]
    assert failures
    assert all(item.status.value == "failed" for item in failures)


class FailingGitHub(GitHubClient):
    def __init__(self, settings):
        super().__init__(settings)
        self.calls = 0

    async def create_issue(self, *, title, body, labels):
        self.calls += 1
        raise IntegrationError("GitHub temporarily unavailable", status_code=503)


async def test_github_failure_retries_and_marks_workflow_for_dlq(settings):
    github = FailingGitHub(settings)
    run, _ = await workflow(settings, github=github).process(
        build_demo_incident(settings, event_id="github-fails")
    )
    assert github.calls == 3
    assert run.stage is WorkflowStage.FAILED
    assert run.actions[0].action_kind == "github_issue"
    assert run.actions[0].attempts == 3
    assert run.actions[0].status.value == "failed"
