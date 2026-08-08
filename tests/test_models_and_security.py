from __future__ import annotations

from hashlib import sha256

import pytest

from drift.demo import build_demo_incident
from drift.models import RemediationProposal, TargetRepository
from drift.reasoning import build_proposal
from drift.security import redact, validate_proposal, validate_target


def test_incident_identity_is_stable(settings):
    first = build_demo_incident(settings, event_id="same-event")
    second = build_demo_incident(settings, event_id="same-event")
    assert first.incident_id == second.incident_id
    assert first.incident_id.startswith("inc-")


def test_target_rejects_path_traversal():
    with pytest.raises(ValueError, match="path traversal"):
        TargetRepository(
            owner="acme",
            repo="drift-demo-target",
            base_branch="main",
            candidate_path="../secrets.txt",
            baseline_content="safe",
        )


def test_target_must_match_allowlist(settings):
    event = build_demo_incident(settings)
    validate_target(event, settings)
    event.target.repo = "other-repository"
    with pytest.raises(ValueError, match="repository"):
        validate_target(event, settings)


def test_proposal_requires_matching_baseline(settings):
    event = build_demo_incident(settings)
    proposal = build_proposal(
        event,
        replacement_content="A safe replacement with evidence and escalation.",
        rationale="test",
    )
    proposal.baseline_sha256 = sha256(b"different").hexdigest()
    with pytest.raises(ValueError, match="baseline hash"):
        validate_proposal(proposal, event, settings)


def test_high_risk_and_oversized_proposals_are_blocked(settings):
    event = build_demo_incident(settings)
    proposal = build_proposal(event, replacement_content="safe", rationale="test", risk="high")
    with pytest.raises(ValueError, match="high-risk"):
        validate_proposal(proposal, event, settings)

    proposal = RemediationProposal(
        target_path=event.target.candidate_path,
        baseline_sha256=sha256(event.target.baseline_content.encode()).hexdigest(),
        replacement_content="safe",
        unified_diff="x" * (settings.max_patch_bytes + 1),
        rationale="test",
        risk="low",
    )
    with pytest.raises(ValueError, match="patch exceeds"):
        validate_proposal(proposal, event, settings)


def test_secret_redaction():
    github_secret = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz123456"
    slack_secret = "https://hooks." + "slack.com/services/A/B/C"
    value = f"token=super-secret {github_secret} {slack_secret}"
    clean = redact(value)
    assert "super-secret" not in clean
    assert "ghp_" not in clean
    assert "hooks.slack.com" not in clean
    assert clean.count("[REDACTED]") >= 3
