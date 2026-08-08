"""Normalization for Pub/Sub push envelopes and Cloud Logging-style events."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .models import IncidentEvent
from .security import sanitize_payload


class PubSubMessage(BaseModel):
    data: str
    messageId: str | None = None
    publishTime: datetime | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str | None = None


def decode_pubsub_envelope(envelope: PubSubEnvelope) -> IncidentEvent:
    try:
        raw = base64.b64decode(envelope.message.data, validate=True)
        payload: dict[str, Any] = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Pub/Sub data must be base64-encoded IncidentEvent JSON") from exc
    payload = sanitize_payload(payload)
    payload.setdefault("event_id", envelope.message.messageId)
    payload.setdefault("occurred_at", envelope.message.publishTime or datetime.now(UTC))
    payload.setdefault("metadata", {})
    payload["metadata"].update(
        {
            "pubsub_message_id": envelope.message.messageId,
            "subscription": envelope.subscription,
            "pubsub_attributes": envelope.message.attributes,
        }
    )
    return IncidentEvent.model_validate(payload)


def normalize_logging_event(payload: dict[str, Any]) -> IncidentEvent:
    """Normalize a documented adapter shape produced from a Cloud Logging sink."""
    safe = sanitize_payload(payload)
    json_payload = safe.get("jsonPayload", {})
    labels = safe.get("resource", {}).get("labels", {})
    incident = json_payload.get("drift_incident", json_payload)
    incident.setdefault("event_id", safe.get("insertId"))
    incident.setdefault("source", "google.cloud.logging")
    incident.setdefault("service", labels.get("service_name", "unknown-service"))
    incident.setdefault("trace_id", safe.get("trace", incident.get("event_id", "unknown-trace")))
    incident.setdefault("occurred_at", safe.get("timestamp", datetime.now(UTC)))
    incident.setdefault("metadata", {})
    incident["metadata"]["cloud_logging"] = True
    return IncidentEvent.model_validate(incident)
