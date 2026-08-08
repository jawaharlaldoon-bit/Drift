"""Input containment and redaction for untrusted incident evidence."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any

from .config import Settings
from .models import IncidentEvent, RemediationProposal

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"https://hooks\.slack\.com/services/[^\s]+"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
]


def redact(value: str) -> str:
    clean = value
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean[:20_000]


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {str(k)[:120]: sanitize_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(v) for v in value[:100]]
    return value


def validate_target(event: IncidentEvent, settings: Settings) -> None:
    target = event.target
    if f"{target.owner}/{target.repo}" != settings.github_full_name:
        raise ValueError("target repository is not allow-listed")
    if target.base_branch != settings.github_base_branch:
        raise ValueError("target base branch is not allow-listed")
    normalized = str(PurePosixPath(target.candidate_path))
    if normalized != target.candidate_path or normalized not in settings.allowed_paths:
        raise ValueError("target path is not allow-listed")


def validate_proposal(proposal: RemediationProposal, event: IncidentEvent, settings: Settings) -> None:
    validate_target(event, settings)
    if proposal.target_path != event.target.candidate_path:
        raise ValueError("proposal changed the authorized target path")
    if proposal.baseline_sha256 != sha256(event.target.baseline_content.encode()).hexdigest():
        raise ValueError("proposal baseline hash does not match the incident")
    patch_bytes = len(proposal.unified_diff.encode())
    if patch_bytes > settings.max_patch_bytes:
        raise ValueError(f"patch exceeds {settings.max_patch_bytes} bytes")
    if proposal.risk == "high":
        raise ValueError("high-risk proposals cannot create pull requests")


def fingerprint(payload: str) -> str:
    return sha256(payload.encode()).hexdigest()
