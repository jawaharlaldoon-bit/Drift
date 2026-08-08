"""Sanitized JSON logs that Cloud Run promotes to structured Cloud Logging fields."""

from __future__ import annotations

import json
import sys
from typing import Any

from .models import utc_now
from .security import sanitize_payload


def structured_log(message: str, *, severity: str = "INFO", **fields: Any) -> None:
    record = {
        "severity": severity,
        "message": message,
        "timestamp": utc_now().isoformat(),
        "service": "drift-api",
        **sanitize_payload(fields),
    }
    sys.stdout.write(json.dumps(record, default=str, separators=(",", ":")) + "\n")
    sys.stdout.flush()
