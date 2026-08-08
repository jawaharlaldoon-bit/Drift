"""Deterministic GitHub and Slack adapters with explicit dry-run behavior."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import httpx

from .config import Settings


class IntegrationError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return self.status_code is None or self.status_code == 429 or self.status_code >= 500


@dataclass
class ExternalResult:
    external_id: str
    url: str
    payload: dict[str, Any]


class GitHubClient:
    API = "https://api.github.com"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def live(self) -> bool:
        return self.settings.action_mode == "live" and bool(self.settings.github_token)

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self.settings.github_token:
            raise IntegrationError("GitHub token is not configured")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.settings.github_token}",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        owned = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            response = await client.request(method, f"{self.API}{path}", headers=headers, **kwargs)
        finally:
            if owned:
                await client.aclose()
        if response.status_code >= 400:
            raise IntegrationError(
                f"GitHub returned HTTP {response.status_code}", status_code=response.status_code
            )
        return response.json() if response.content else {}

    async def create_issue(self, *, title: str, body: str, labels: list[str]) -> ExternalResult:
        if not self.live:
            return ExternalResult(
                external_id="dry-issue-101",
                url=f"https://github.com/{self.settings.github_full_name}/issues/101",
                payload={"dry_run": True},
            )
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        data = await self._request(
            "POST",
            f"/repos/{self.settings.github_full_name}/issues",
            json=payload,
        )
        return ExternalResult(str(data["number"]), data["html_url"], data)

    async def create_branch_and_commit(
        self,
        *,
        branch: str,
        path: str,
        content: str,
        message: str,
        expected_sha256: str,
    ) -> ExternalResult:
        if not self.live:
            return ExternalResult(
                external_id="dry-commit-a1b2c3",
                url=f"https://github.com/{self.settings.github_full_name}/tree/{branch}",
                payload={"dry_run": True, "branch": branch, "baseline_verified": True},
            )
        full_name = self.settings.github_full_name
        base = self.settings.github_base_branch
        existing = await self._request(
            "GET", f"/repos/{full_name}/contents/{path}", params={"ref": base}
        )
        current_content = base64.b64decode(existing["content"]).decode()
        if sha256(current_content.encode()).hexdigest() != expected_sha256:
            raise IntegrationError(
                "repository content changed after the incident was captured",
                status_code=409,
            )
        ref = await self._request("GET", f"/repos/{full_name}/git/ref/heads/{base}")
        base_sha = ref["object"]["sha"]
        await self._request(
            "POST",
            f"/repos/{full_name}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        commit = await self._request(
            "PUT",
            f"/repos/{full_name}/contents/{path}",
            json={
                "message": message,
                "content": base64.b64encode(content.encode()).decode(),
                "sha": existing["sha"],
                "branch": branch,
            },
        )
        return ExternalResult(
            commit["commit"]["sha"], commit["commit"]["html_url"], commit
        )

    async def create_draft_pull_request(
        self, *, title: str, body: str, branch: str
    ) -> ExternalResult:
        if not self.live:
            return ExternalResult(
                external_id="dry-pr-42",
                url=f"https://github.com/{self.settings.github_full_name}/pull/42",
                payload={"dry_run": True},
            )
        data = await self._request(
            "POST",
            f"/repos/{self.settings.github_full_name}/pulls",
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": self.settings.github_base_branch,
                "draft": True,
            },
        )
        return ExternalResult(str(data["number"]), data["html_url"], data)


class SlackClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def live(self) -> bool:
        return self.settings.action_mode == "live" and bool(self.settings.slack_webhook_url)

    async def post(self, payload: dict[str, Any]) -> ExternalResult:
        if not self.live:
            return ExternalResult(
                external_id="dry-slack-ok", url="https://slack.com/", payload={"dry_run": True}
            )
        assert self.settings.slack_webhook_url is not None
        owned = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.post(self.settings.slack_webhook_url, json=payload)
        finally:
            if owned:
                await client.aclose()
        if response.status_code >= 400:
            raise IntegrationError(
                f"Slack returned HTTP {response.status_code}", status_code=response.status_code
            )
        return ExternalResult("slack-ok", "https://slack.com/", {"status": response.text})


def detected_slack_payload(incident_id: str, service: str, severity: str, issue_url: str) -> dict:
    return {
        "text": f"Drift accepted {incident_id} from {service}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Drift incident accepted*\n`{incident_id}` · {service} · *{severity}*",
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"Evidence and progress: <{issue_url}|GitHub issue>"},
            },
        ],
    }


def completed_slack_payload(
    incident_id: str, *, passed: bool, pull_request_url: str | None, issue_url: str
) -> dict:
    if passed and pull_request_url:
        status = "Validation passed; a draft PR is awaiting human review."
        link = f"<{pull_request_url}|Review proof-carrying remediation>"
    else:
        status = "Validation blocked the candidate; no pull request was opened."
        link = f"<{issue_url}|Review the incident evidence>"
    return {
        "text": f"Drift completed {incident_id}: {status}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Drift workflow complete*\n`{incident_id}`"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"{status}\n{link}"}},
        ],
    }
