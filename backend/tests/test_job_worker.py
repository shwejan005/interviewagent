"""Focused tests for durable worker claim and outcome transitions."""

import asyncio

import database as db
from job_worker import run_once


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