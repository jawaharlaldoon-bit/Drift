"""Reasoning backends: deterministic local demo and Gemini-powered production path."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import unified_diff
from hashlib import sha256
from uuid import uuid4

from .config import Settings
from .models import (
    FailureCategory,
    IncidentEvent,
    Investigation,
    RemediationProposal,
    Route,
    Severity,
    TriageDecision,
)
from .security import redact


@dataclass
class AnalysisBundle:
    triage: TriageDecision
    investigation: Investigation
    proposal: RemediationProposal | None
    policy_review: str = ""


class Reasoner(ABC):
    @abstractmethod
    async def analyze(self, event: IncidentEvent) -> AnalysisBundle: ...


def build_proposal(
    event: IncidentEvent,
    *,
    replacement_content: str,
    rationale: str,
    risk: str = "low",
) -> RemediationProposal:
    before = event.target.baseline_content.splitlines(keepends=True)
    after = replacement_content.splitlines(keepends=True)
    diff = "".join(
        unified_diff(
            before,
            after,
            fromfile=f"a/{event.target.candidate_path}",
            tofile=f"b/{event.target.candidate_path}",
        )
    )
    return RemediationProposal(
        target_path=event.target.candidate_path,
        baseline_sha256=sha256(event.target.baseline_content.encode()).hexdigest(),
        replacement_content=replacement_content,
        unified_diff=diff,
        rationale=rationale,
        risk=risk,
    )


class DeterministicReasoner(Reasoner):
    """Reliable offline path. It is explicitly surfaced as demo mode in the UI."""

    async def analyze(self, event: IncidentEvent) -> AnalysisBundle:
        error_text = " ".join(tool.error or "" for tool in event.tool_events).lower()
        combined = f"{event.output_text} {error_text}".lower()

        if "invent" in combined or "unsupported" in combined or "delete" in combined:
            category = FailureCategory.UNSAFE_ACTION
            severity = Severity.CRITICAL
            confidence = 0.96
            route = Route.REMEDIATE
        elif any(tool.status.lower() in {"error", "failed", "timeout"} for tool in event.tool_events):
            category = FailureCategory.TOOL_FAILURE
            severity = Severity.HIGH
            confidence = 0.91
            route = Route.REMEDIATE
        elif event.output_text.strip() == event.expected_behavior.strip():
            category = FailureCategory.NON_ACTIONABLE
            severity = Severity.LOW
            confidence = 0.98
            route = Route.IGNORE
        else:
            category = FailureCategory.POLICY_DRIFT
            severity = Severity.MEDIUM
            confidence = 0.78
            route = Route.DOCUMENT

        evidence = [
            f"Observed output: {redact(event.output_text)[:240]}",
            f"Expected behavior: {redact(event.expected_behavior)[:240]}",
        ]
        evidence.extend(
            f"Tool {tool.name} returned {tool.status}: {redact(tool.error or str(tool.output))[:180]}"
            for tool in event.tool_events
        )
        triage = TriageDecision(
            severity=severity,
            category=category,
            confidence=confidence,
            summary=(
                "The agent recommended an unsupported operational action after its evidence tool failed."
                if route is Route.REMEDIATE
                else "The event does not meet the autonomous remediation threshold."
            ),
            evidence=evidence,
            route=route,
        )
        investigation = Investigation(
            root_cause=(
                "The system policy allowed the agent to replace missing tool evidence with a confident action."
            ),
            causal_factors=[
                "Evidence lookup did not return a verified result.",
                "The baseline policy did not require abstention on missing evidence.",
                "The response was not gated before reaching the operator.",
            ],
            recommended_change=(
                "Require cited tool evidence for operational claims and force escalation when a tool fails."
            ),
        )
        proposal = None
        if route is Route.REMEDIATE:
            replacement = (
                "# Operational response policy\n\n"
                "1. Use tool results as the only source for operational claims.\n"
                "2. If a required tool fails, times out, or returns no evidence, do not infer a cause.\n"
                "3. Never recommend destructive commands or production changes without verified evidence.\n"
                "4. State what evidence is missing and escalate to a human operator.\n"
                "5. Cite the successful tool result that supports each recommended action.\n"
            )
            proposal = build_proposal(
                event,
                replacement_content=replacement,
                rationale="Converts missing evidence from an invitation to guess into an explicit escalation.",
                risk="low",
            )
        return AnalysisBundle(
            triage=triage,
            investigation=investigation,
            proposal=proposal,
            policy_review="Deterministic guardrail review passed.",
        )


class GeminiAdkReasoner(Reasoner):
    """Runs the triage, remediation, and policy-review sequence through Google ADK."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def analyze(self, event: IncidentEvent) -> AnalysisBundle:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        from .adk_app import build_root_agent

        app_name = "drift"
        user_id = "event-router"
        session_id = f"incident-{uuid4().hex}"
        service = InMemorySessionService()
        await service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state={"incident_json": event.model_dump_json()},
        )
        runner = Runner(agent=build_root_agent(self.settings), app_name=app_name, session_service=service)
        message = types.Content(
            role="user",
            parts=[types.Part(text="Analyze this incident and produce a constrained remediation package.")],
        )
        async for _ in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            pass
        session = await service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        if session is None:
            raise RuntimeError("ADK session disappeared before results were collected")
        state = session.state
        triage = TriageDecision.model_validate(self._decode(state.get("triage_output")))
        investigation = Investigation.model_validate(self._decode(state.get("investigation_output")))
        proposal_data = self._decode(state.get("remediation_output"))
        proposal = None
        if triage.route is Route.REMEDIATE:
            proposal = build_proposal(
                event,
                replacement_content=str(proposal_data["replacement_content"]),
                rationale=str(proposal_data["rationale"]),
                risk=str(proposal_data.get("risk", "medium")),
            )
        return AnalysisBundle(
            triage=triage,
            investigation=investigation,
            proposal=proposal,
            policy_review=str(state.get("policy_review", "Gemini policy review completed.")),
        )

    @staticmethod
    def _decode(value):
        if isinstance(value, str):
            return json.loads(value)
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        raise ValueError("ADK agent did not emit structured state")


def get_reasoner(settings: Settings) -> Reasoner:
    if settings.drift_reasoning_backend == "gemini_adk":
        return GeminiAdkReasoner(settings)
    return DeterministicReasoner()
