"""Domain contracts for the Drift workflow. Modified for Drift in 2026."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FailureCategory(str, Enum):
    HALLUCINATION = "hallucination"
    TOOL_FAILURE = "tool_failure"
    POLICY_DRIFT = "policy_drift"
    UNSAFE_ACTION = "unsafe_action"
    NON_ACTIONABLE = "non_actionable"


class Route(str, Enum):
    IGNORE = "ignore"
    DOCUMENT = "document"
    REMEDIATE = "remediate"


class WorkflowStage(str, Enum):
    INGESTED = "ingested"
    DEDUPLICATED = "deduplicated"
    TRIAGED = "triaged"
    INVESTIGATED = "investigated"
    ROUTED = "routed"
    ISSUE_CREATED = "issue_created"
    CANDIDATE_GENERATED = "candidate_generated"
    VALIDATED = "validated"
    PR_OPENED = "pr_opened"
    NOTIFIED = "notified"
    AWAITING_REVIEW = "awaiting_review"
    DOCUMENTED = "documented"
    IGNORED = "ignored"
    FAILED = "failed"


TERMINAL_STAGES = {
    WorkflowStage.AWAITING_REVIEW,
    WorkflowStage.DOCUMENTED,
    WorkflowStage.IGNORED,
    WorkflowStage.FAILED,
}


class ToolEvent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    status: str = Field(default="unknown", max_length=40)
    input: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    error: str | None = Field(default=None, max_length=2_000)


class TargetRepository(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    base_branch: str = Field(default="main", min_length=1, max_length=120)
    candidate_path: str = Field(min_length=1, max_length=300)
    baseline_content: str = Field(min_length=1, max_length=50_000)

    @field_validator("candidate_path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        value = value.replace("\\", "/").lstrip("/")
        if ".." in value.split("/"):
            raise ValueError("path traversal is not allowed")
        return value


class IncidentEvent(BaseModel):
    event_id: str = Field(min_length=3, max_length=200)
    source: str = Field(min_length=2, max_length=120)
    service: str = Field(min_length=2, max_length=120)
    occurred_at: datetime = Field(default_factory=utc_now)
    trace_id: str = Field(min_length=3, max_length=200)
    input_text: str = Field(min_length=1, max_length=20_000)
    output_text: str = Field(min_length=1, max_length=40_000)
    expected_behavior: str = Field(min_length=1, max_length=20_000)
    tool_events: list[ToolEvent] = Field(default_factory=list, max_length=50)
    target: TargetRepository
    metadata: dict[str, Any] = Field(default_factory=dict)
    demo: bool = False

    @property
    def incident_id(self) -> str:
        digest = sha256(f"{self.source}:{self.event_id}".encode()).hexdigest()[:16]
        return f"inc-{digest}"


class TriageDecision(BaseModel):
    severity: Severity
    category: FailureCategory
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=2_000)
    evidence: list[str] = Field(default_factory=list, max_length=12)
    route: Route


class Investigation(BaseModel):
    root_cause: str = Field(min_length=1, max_length=4_000)
    causal_factors: list[str] = Field(default_factory=list, max_length=12)
    runbook: str = Field(default="proof-carrying-remediation", max_length=120)
    recommended_change: str = Field(min_length=1, max_length=4_000)


class RemediationProposal(BaseModel):
    target_path: str
    baseline_sha256: str
    replacement_content: str = Field(min_length=1, max_length=50_000)
    unified_diff: str = Field(min_length=1, max_length=60_000)
    rationale: str = Field(min_length=1, max_length=4_000)
    risk: str = Field(pattern="^(low|medium|high)$")


class ValidationCase(BaseModel):
    name: str
    input_text: str
    expected_behavior: str
    before_output: str
    after_output: str
    before_passed: bool
    after_passed: bool


class ValidationReport(BaseModel):
    passed: bool
    before_pass_rate: float = Field(ge=0, le=1)
    after_pass_rate: float = Field(ge=0, le=1)
    baseline_avg_latency_ms: float = Field(default=0, ge=0)
    candidate_avg_latency_ms: float = Field(default=0, ge=0)
    cases: list[ValidationCase] = Field(default_factory=list)
    gate_reason: str


class ActionStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ActionReceipt(BaseModel):
    action_kind: str
    idempotency_key: str
    request_fingerprint: str
    status: ActionStatus = ActionStatus.PENDING
    attempts: int = 0
    external_id: str | None = None
    external_url: HttpUrl | None = None
    sanitized_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class WorkflowEvent(BaseModel):
    incident_id: str
    stage: WorkflowStage
    title: str
    detail: str = ""
    occurred_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    incident_id: str
    source_event_id: str
    source: str
    service: str
    trace_id: str
    demo: bool = False
    stage: WorkflowStage = WorkflowStage.INGESTED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    event: IncidentEvent
    triage: TriageDecision | None = None
    investigation: Investigation | None = None
    proposal: RemediationProposal | None = None
    validation: ValidationReport | None = None
    actions: list[ActionReceipt] = Field(default_factory=list)
    issue_url: HttpUrl | None = None
    pull_request_url: HttpUrl | None = None
    branch_name: str | None = None
    failure: str | None = None

    @property
    def terminal(self) -> bool:
        return self.stage in TERMINAL_STAGES


class IncidentSummary(BaseModel):
    incident_id: str
    service: str
    stage: WorkflowStage
    severity: Severity | None
    summary: str
    demo: bool
    updated_at: datetime

    @classmethod
    def from_run(cls, run: WorkflowRun) -> IncidentSummary:
        return cls(
            incident_id=run.incident_id,
            service=run.service,
            stage=run.stage,
            severity=run.triage.severity if run.triage else None,
            summary=run.triage.summary if run.triage else "Incident accepted",
            demo=run.demo,
            updated_at=run.updated_at,
        )
