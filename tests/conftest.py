from __future__ import annotations

import pytest

from drift.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        drift_env="test",
        drift_demo_mode=True,
        drift_reasoning_backend="deterministic",
        github_owner="acme",
        github_repo="drift-demo-target",
        github_base_branch="main",
        github_allowed_paths="prompts/system.md,config/agent-policy.yaml",
        demo_target_url="http://127.0.0.1:1",
        state_backend="memory",
        action_mode="dry-run",
        demo_trigger_token="test-token",
    )
