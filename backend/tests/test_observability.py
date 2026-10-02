"""Regression tests for safe structured execution metadata."""

import json
import logging

from app.shared.observability import JsonLogFormatter, log_execution_event


def test_execution_event_formatter_emits_stable_metadata_without_payload():
    record = logging.LogRecord(
        name="job_worker",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="execution_event",
        args=(),
        exc_info=None,
    )
    record.event = "job_completed"
    record.execution_fields = {
        "job_id": 7,
        "evaluation_id": 12,
        "worker_id": "worker-a",
        "stage": "final_decision",
        "attempt_id": "7:1",
        "status": "COMPLETED",
        "duration_ms": 42.5,
        "cancellation_requested": False,
    }

    formatted = json.loads(JsonLogFormatter().format(record))

    assert formatted["event"] == "job_completed"
    assert formatted["evaluation_id"] == 12
    assert formatted["attempt_id"] == "7:1"
    assert "payload" not in formatted


def test_execution_event_does_not_log_sensitive_job_payload(caplog):
    logger = logging.getLogger("test.execution")
    job = {
        "id": 9,
        "job_type": "final_decision",
        "attempts": 2,
        "payload": {
            "evaluation_id": 22,
            "resume_text": "private resume text",
            "answer": "private answer",
        },
    }

    with caplog.at_level(logging.INFO, logger="test.execution"):
        log_execution_event(
            logger,
            "job_started",
            job=job,
            worker_id="worker-a",
            status="RUNNING",
        )

    assert len(caplog.records) == 1
    assert caplog.records[0].event == "job_started"
    assert "private resume text" not in caplog.text
    assert "private answer" not in caplog.text