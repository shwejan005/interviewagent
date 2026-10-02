"""Small structured logging primitives for operational execution events."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Render log records as safe, single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "event", None)
        if event:
            payload["event"] = event
        fields = getattr(record, "execution_fields", None)
        if fields:
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def configure_logging() -> None:
    """Configure the process root logger for machine-readable output."""
    root_logger = logging.getLogger()
    root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())
    formatter = JsonLogFormatter()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


def log_execution_event(
    logger: logging.Logger,
    event: str,
    *,
    job: dict[str, Any],
    worker_id: str,
    status: str,
    duration_ms: float | None = None,
    error_type: str | None = None,
    cancellation_requested: bool = False,
    level: int = logging.INFO,
) -> None:
    """Emit execution metadata without logging job payload or candidate data."""
    payload = job.get("payload") or {}
    fields: dict[str, Any] = {
        "job_id": job["id"],
        "worker_id": worker_id,
        "stage": job["job_type"],
        "attempt": job.get("attempts"),
        "attempt_id": f"{job['id']}:{job.get('attempts', 0)}",
        "status": status,
        "cancellation_requested": cancellation_requested,
    }
    evaluation_id = payload.get("evaluation_id")
    if isinstance(evaluation_id, int):
        fields["evaluation_id"] = evaluation_id
    trace_id = payload.get("trace_id")
    if isinstance(trace_id, str) and trace_id:
        fields["trace_id"] = trace_id
    if duration_ms is not None:
        fields["duration_ms"] = round(duration_ms, 2)
    if error_type:
        fields["error_type"] = error_type
    logger.log(
        level,
        "execution_event",
        extra={"event": event, "execution_fields": fields},
    )