from __future__ import annotations

import base64
import json

import pytest

from drift.demo import build_demo_incident
from drift.ingestion import PubSubEnvelope, decode_pubsub_envelope, normalize_logging_event


def test_pubsub_envelope_normalizes_incident(settings):
    event = build_demo_incident(settings, event_id="payload-id")
    data = base64.b64encode(event.model_dump_json().encode()).decode()
    envelope = PubSubEnvelope.model_validate(
        {"message": {"data": data, "messageId": "message-id", "attributes": {"kind": "ai"}}}
    )
    decoded = decode_pubsub_envelope(envelope)
    assert decoded.event_id == "payload-id"
    assert decoded.metadata["pubsub_message_id"] == "message-id"
    assert decoded.metadata["pubsub_attributes"] == {"kind": "ai"}


def test_pubsub_envelope_rejects_bad_data():
    envelope = PubSubEnvelope.model_validate({"message": {"data": "not-base64"}})
    with pytest.raises(ValueError, match="base64"):
        decode_pubsub_envelope(envelope)


def test_cloud_logging_adapter(settings):
    event = build_demo_incident(settings, event_id="logging-id")
    payload = {
        "insertId": "logging-id",
        "timestamp": event.occurred_at.isoformat(),
        "trace": "projects/demo/traces/abc",
        "resource": {"labels": {"service_name": "release-guardian"}},
        "jsonPayload": {"drift_incident": event.model_dump(mode="json")},
    }
    normalized = normalize_logging_event(json.loads(json.dumps(payload, default=str)))
    assert normalized.source == "drift.demo"
    assert normalized.metadata["cloud_logging"] is True
