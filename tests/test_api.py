from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from drift.api import app
from drift.config import get_settings
from drift.demo import build_demo_incident
from drift.models import WorkflowRun, WorkflowStage


def test_healthz_does_not_expose_secrets():
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    body = response.json()
    serialized = response.text.lower()
    assert body["service"] == "drift-api"
    assert "github_token" not in serialized
    assert "slack_webhook" not in serialized
    assert "demo_trigger_token" not in serialized


def test_demo_trigger_requires_token():
    response = TestClient(app).post("/v1/demo/incidents", json={})
    assert response.status_code == 401


def test_failed_pubsub_workflow_requests_redelivery(monkeypatch):
    event = build_demo_incident(get_settings(), event_id="pubsub-failure")

    class FailedWorkflow:
        async def process(self, received):
            run = WorkflowRun(
                incident_id=received.incident_id,
                source_event_id=received.event_id,
                source=received.source,
                service=received.service,
                trace_id=received.trace_id,
                event=received,
                stage=WorkflowStage.FAILED,
                failure="GitHub exhausted its retry budget",
            )
            return run, False

    monkeypatch.setattr("drift.api.DriftWorkflow", FailedWorkflow)
    encoded = base64.b64encode(event.model_dump_json().encode()).decode()
    response = TestClient(app).post(
        "/v1/events/pubsub",
        json={"message": {"data": encoded, "messageId": "pubsub-failure"}},
    )
    assert response.status_code == 503
    assert "retry requested" in response.json()["detail"]
