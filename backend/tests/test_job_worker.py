"""Focused tests for durable worker claim and outcome transitions."""

import asyncio

import pytest

from app.config import database as db
from app.evaluation.runner import AgentOutputError
from app.worker import job_worker
from app.worker.job_worker import _retry_delay, run_forever, run_once


def test_retry_delay_is_capped_and_jittered(monkeypatch):
    monkeypatch.setattr(job_worker.random, "uniform", lambda minimum, maximum: maximum)

    assert _retry_delay(1, base_seconds=10, max_seconds=30) == pytest.approx(12)
    assert _retry_delay(4, base_seconds=10, max_seconds=30) == pytest.approx(30)


def test_worker_completes_a_claimed_job(isolated_db):
    job_id = isolated_db.enqueue_job("test_success", {"value": 7})
    seen = []

    async def handler(payload):
        seen.append(payload)

    found_work = asyncio.run(
        run_once("worker-a", handlers={"test_success": handler})
    )

    assert found_work is True
    assert seen == [{"value": 7}]
    assert isolated_db.get_job(job_id)["status"] == "COMPLETED"


def test_worker_failure_is_retryable_then_dead_letters(isolated_db):
    job_id = isolated_db.enqueue_job("test_failure", {}, max_attempts=2)

    async def handler(payload):
        raise RuntimeError("deterministic failure")

    handlers = {"test_failure": handler}
    asyncio.run(run_once("worker-a", handlers=handlers, retry_delay_seconds=0))
    assert isolated_db.get_job(job_id)["status"] == "PENDING"

    asyncio.run(run_once("worker-a", handlers=handlers, retry_delay_seconds=0))
    job = isolated_db.get_job(job_id)
    assert job["status"] == "DEAD"
    assert job["attempts"] == 2
    assert job["last_error"] == "deterministic failure"


def test_worker_cancellation_releases_claim_for_immediate_retry(isolated_db):
    job_id = isolated_db.enqueue_job("test_cancelled", {}, max_attempts=2)

    async def handler(payload):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run_once("worker-a", handlers={"test_cancelled": handler}))

    job = isolated_db.get_job(job_id)
    assert job["status"] == "PENDING"
    assert job["locked_by"] is None
    assert job["available_at"] <= job["updated_at"]


def test_non_retryable_agent_output_is_dead_lettered(isolated_db):
    job_id = isolated_db.enqueue_job("test_invalid_output", {}, max_attempts=3)

    async def handler(payload):
        raise AgentOutputError("invalid verdict", "raw output")

    asyncio.run(run_once("worker-a", handlers={"test_invalid_output": handler}))

    job = isolated_db.get_job(job_id)
    assert job["status"] == "DEAD"
    assert job["attempts"] == 1


def test_cancelled_pending_job_is_not_executed(isolated_db):
    job_id = isolated_db.enqueue_job("test_cancelled", {})
    assert isolated_db.request_job_cancellation(job_id) is True
    seen = []

    async def handler(payload):
        seen.append(payload)

    assert asyncio.run(run_once("worker-a", handlers={"test_cancelled": handler})) is False
    assert seen == []
    assert isolated_db.get_job(job_id)["status"] == "CANCELLED"


def test_cancellation_requested_during_handler_does_not_complete_job(isolated_db):
    job_id = isolated_db.enqueue_job("test_cancel_during_run", {})

    async def handler(payload):
        assert isolated_db.request_job_cancellation(job_id) is True

    asyncio.run(run_once("worker-a", handlers={"test_cancel_during_run": handler}))
    assert isolated_db.get_job(job_id)["status"] == "CANCELLED"


def test_worker_stop_event_drains_current_job_then_exits(isolated_db):
    job_id = isolated_db.enqueue_job("test_stop", {})
    stop_event = asyncio.Event()
    seen = []

    async def handler(payload):
        seen.append(payload)
        stop_event.set()

    asyncio.run(
        run_forever(
            "worker-a",
            handlers={"test_stop": handler},
            stop_event=stop_event,
            poll_seconds=0,
        )
    )

    assert seen == [{}]
    assert isolated_db.get_job(job_id)["status"] == "COMPLETED"