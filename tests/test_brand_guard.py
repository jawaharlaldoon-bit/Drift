from __future__ import annotations

from pathlib import Path

from scripts.brand_guard import scan


def test_repository_has_no_legacy_identity_outside_compliance_folder():
    root = Path(__file__).resolve().parent.parent
    assert scan(root) == []
