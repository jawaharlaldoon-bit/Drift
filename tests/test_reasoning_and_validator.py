from __future__ import annotations

from drift.demo import build_demo_incident
from drift.models import Route
from drift.reasoning import DeterministicReasoner
from drift.validator import SandboxValidator


async def test_deterministic_reasoner_routes_demo_to_remediation(settings):
    event = build_demo_incident(settings)
    result = await DeterministicReasoner().analyze(event)
    assert result.triage.route is Route.REMEDIATE
    assert result.triage.confidence > settings.triage_confidence_threshold
    assert result.proposal is not None
    assert "do not infer" in result.proposal.replacement_content.lower()


async def test_replay_gate_proves_candidate(settings):
    event = build_demo_incident(settings)
    result = await DeterministicReasoner().analyze(event)
    report = await SandboxValidator(settings).validate(event, result.proposal)
    assert report.passed is True
    assert report.before_pass_rate < report.after_pass_rate
    assert report.after_pass_rate == 1.0
    assert len(report.cases) == 4
