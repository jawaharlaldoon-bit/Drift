from __future__ import annotations

import base64
from hashlib import sha256

import httpx

from drift.integrations import GitHubClient, IntegrationError, SlackClient


async def test_github_issue_branch_commit_and_draft_pr_contract(settings):
    settings.action_mode = "live"
    settings.github_token = "test-placeholder-token"
    baseline = "baseline policy\n"
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        assert request.headers["X-GitHub-Api-Version"] == "2026-03-10"
        assert request.headers["Authorization"].startswith("Bearer ")
        if request.url.path.endswith("/issues"):
            assert "labels" not in request.read().decode()
            return httpx.Response(
                201,
                json={"number": 7, "html_url": "https://github.com/acme/repo/issues/7"},
            )
        if "/contents/" in request.url.path and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "sha": "blob-sha",
                    "content": base64.b64encode(baseline.encode()).decode(),
                },
            )
        if "/git/ref/heads/" in request.url.path:
            return httpx.Response(200, json={"object": {"sha": "base-sha"}})
        if request.url.path.endswith("/git/refs"):
            return httpx.Response(201, json={"ref": "refs/heads/drift/incident-test"})
        if "/contents/" in request.url.path and request.method == "PUT":
            return httpx.Response(
                200,
                json={
                    "commit": {
                        "sha": "commit-sha",
                        "html_url": "https://github.com/acme/repo/commit/commit-sha",
                    }
                },
            )
        if request.url.path.endswith("/pulls"):
            assert '"draft":true' in request.read().decode()
            return httpx.Response(
                201,
                json={"number": 9, "html_url": "https://github.com/acme/repo/pull/9"},
            )
        raise AssertionError(f"unexpected GitHub request: {request.method} {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        github = GitHubClient(settings, client)
        issue = await github.create_issue(title="Incident", body="Evidence", labels=[])
        commit = await github.create_branch_and_commit(
            branch="drift/incident-test",
            path=settings.allowed_paths[0],
            content="safer policy\n",
            message="fix: contain incident",
            expected_sha256=sha256(baseline.encode()).hexdigest(),
        )
        pull = await github.create_draft_pull_request(
            title="Contain incident", body="Replay passed", branch="drift/incident-test"
        )

    assert issue.external_id == "7"
    assert commit.external_id == "commit-sha"
    assert pull.external_id == "9"
    assert [method for method, _ in seen].count("POST") == 3


async def test_github_rejects_a_stale_baseline_before_creating_branch(settings):
    settings.action_mode = "live"
    settings.github_token = "test-placeholder-token"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and "/contents/" in request.url.path
        content = base64.b64encode(b"changed upstream\n").decode()
        return httpx.Response(200, json={"sha": "new-sha", "content": content})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        github = GitHubClient(settings, client)
        try:
            await github.create_branch_and_commit(
                branch="drift/incident-stale",
                path=settings.allowed_paths[0],
                content="candidate\n",
                message="fix",
                expected_sha256=sha256(b"old baseline\n").hexdigest(),
            )
        except IntegrationError as exc:
            assert exc.status_code == 409
            assert exc.retryable is False
        else:
            raise AssertionError("stale baseline was accepted")


async def test_slack_webhook_contract(settings):
    settings.action_mode = "live"
    settings.slack_webhook_url = "https://example.test/slack"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.host == "example.test"
        assert '"text":"Drift completed"' in request.read().decode()
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await SlackClient(settings, client).post({"text": "Drift completed"})
    assert result.external_id == "slack-ok"
