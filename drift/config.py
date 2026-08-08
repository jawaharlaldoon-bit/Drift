"""Typed runtime configuration. Modified for Drift in 2026."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    drift_env: str = "local"
    drift_demo_mode: bool = True
    drift_reasoning_backend: str = "deterministic"
    drift_build_revision: str = "dev"

    google_cloud_project: str = "data-shard-504916-r8"
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-3.5-flash"
    firestore_collection: str = "drift_incidents"
    pubsub_topic: str = "drift-incidents"
    pubsub_audience: str | None = None
    pubsub_service_account: str | None = None

    triage_confidence_threshold: float = Field(default=0.72, ge=0, le=1)
    github_owner: str = "jawaharlaldoon-bit"
    github_repo: str = "Drift"
    github_base_branch: str = "main"
    github_allowed_paths: str = (
        "demo_target/prompts/system.md,demo_target/config/agent-policy.yaml"
    )
    github_token: str | None = None
    slack_webhook_url: str | None = None
    demo_trigger_token: str = "local-demo-token"
    demo_target_url: str = "http://localhost:8082"
    max_patch_bytes: int = Field(default=12_000, ge=256, le=100_000)
    state_backend: str = "memory"
    action_mode: str = "dry-run"

    @field_validator("drift_reasoning_backend")
    @classmethod
    def validate_reasoning_backend(cls, value: str) -> str:
        allowed = {"deterministic", "gemini_adk"}
        if value not in allowed:
            raise ValueError(f"must be one of {sorted(allowed)}")
        return value

    @field_validator("state_backend")
    @classmethod
    def validate_state_backend(cls, value: str) -> str:
        if value not in {"memory", "firestore"}:
            raise ValueError("must be memory or firestore")
        return value

    @field_validator("action_mode")
    @classmethod
    def validate_action_mode(cls, value: str) -> str:
        if value not in {"dry-run", "live"}:
            raise ValueError("must be dry-run or live")
        return value

    @property
    def allowed_paths(self) -> tuple[str, ...]:
        return tuple(path.strip() for path in self.github_allowed_paths.split(",") if path.strip())

    @property
    def github_full_name(self) -> str:
        return f"{self.github_owner}/{self.github_repo}"

    @property
    def live_actions_ready(self) -> bool:
        return bool(self.action_mode == "live" and self.github_token and self.slack_webhook_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    get_settings.cache_clear()
