"""Durable background job worker for agent execution."""

import asyncio
import logging
import os
import socket
import uuid
from typing import Awaitable, Callable, Mapping

import database as db
from crew_runner import run_hiring_committee, run_hiring_recommendation
from finalization import finalize_evaluation

logger = logging.getLogger(__name__)

FINAL_DECISION_JOB = "final_decision"
JobHandler = Callable[[dict], Awaitable[None]]


async def _handle_final_decision(payload: dict) -> None:
    evaluation_id = int(payload["evaluation_id"])
    await finalize_evaluation(
        evaluation_id,
        run_recommendation=run_hiring_recommendation,
        run_committee=run_hiring_committee,
    )


DEFAULT_HANDLERS: Mapping[str, JobHandler] = {
    FINAL_DECISION_JOB: _handle_final_decision,
}


async def run_once(
    worker_id: str | None = None,
    *,
    handlers: Mapping[str, JobHandler] = DEFAULT_HANDLERS,
    lease_seconds: int = 300,
    retry_delay_seconds: int = 60,
) -> bool:
    """Claim and execute at most one job; return whether work was found."""
    worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
    job = await asyncio.to_thread(db.claim_next_job, worker_id, lease_seconds=lease_seconds)
    if job is None:
        return False

    try:
        handler = handlers.get(job["job_type"])
        if handler is None:
            raise ValueError(f"No handler registered for job type {job['job_type']}")
        await handler(job["payload"])
    except Exception as exc:
        logger.exception("Job %s failed on worker %s", job["id"], worker_id)
        status = await asyncio.to_thread(
            db.fail_job,
            job["id"],
            worker_id,
            str(exc),
            retry_delay_seconds=retry_delay_seconds,
        )
        logger.warning("Job %s failure recorded with status %s", job["id"], status)
        return True

    if not await asyncio.to_thread(db.complete_job, job["id"], worker_id):
        logger.error("Job %s completion lost worker ownership", job["id"])
    return True


async def run_forever(
    worker_id: str | None = None,
    *,
    poll_seconds: int = 5,
    lease_seconds: int = 300,
) -> None:
    """Continuously drain durable jobs until the process is stopped."""
    while True:
        found_work = await run_once(worker_id, lease_seconds=lease_seconds)
        if not found_work:
            await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_forever())
