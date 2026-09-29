"""Durable background job worker for agent execution."""

import asyncio
import logging
import os
import random
import socket
import uuid
from typing import Awaitable, Callable, Mapping

import database as db
from crew_runner import AgentOutputError
from crew_runner import run_hiring_committee, run_hiring_recommendation
from finalization import finalize_evaluation

logger = logging.getLogger(__name__)

FINAL_DECISION_JOB = "final_decision"
RETRY_BASE_DELAY_SECONDS = float(os.getenv("JOB_RETRY_BASE_DELAY_SECONDS", "5"))
RETRY_MAX_DELAY_SECONDS = float(os.getenv("JOB_RETRY_MAX_DELAY_SECONDS", "900"))
RETRY_JITTER_RATIO = float(os.getenv("JOB_RETRY_JITTER_RATIO", "0.2"))
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


def _retry_delay(
    attempts: int,
    *,
    base_seconds: float = RETRY_BASE_DELAY_SECONDS,
    max_seconds: float = RETRY_MAX_DELAY_SECONDS,
) -> float:
    """Return a capped exponential delay with bounded multiplicative jitter."""
    base = min(max_seconds, base_seconds * (2 ** max(attempts - 1, 0)))
    jitter = random.uniform(1 - RETRY_JITTER_RATIO, 1 + RETRY_JITTER_RATIO)
    return min(max_seconds, max(0.0, base * jitter))


async def run_once(
    worker_id: str | None = None,
    *,
    handlers: Mapping[str, JobHandler] = DEFAULT_HANDLERS,
    lease_seconds: int = 300,
    retry_delay_seconds: float | None = None,
    retry_base_delay_seconds: float = RETRY_BASE_DELAY_SECONDS,
    retry_max_delay_seconds: float = RETRY_MAX_DELAY_SECONDS,
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
        delay = (
            retry_delay_seconds
            if retry_delay_seconds is not None
            else _retry_delay(
                job["attempts"],
                base_seconds=retry_base_delay_seconds,
                max_seconds=retry_max_delay_seconds,
            )
        )
        status = await asyncio.to_thread(
            db.fail_job,
            job["id"],
            worker_id,
            str(exc),
            retry_delay_seconds=delay,
            retryable=not isinstance(exc, AgentOutputError),
        )
        logger.warning("Job %s failure recorded with status %s", job["id"], status)
        return True
    except asyncio.CancelledError:
        await asyncio.shield(
            asyncio.to_thread(
                db.fail_job,
                job["id"],
                worker_id,
                "Worker task cancelled before job completion",
                retry_delay_seconds=0,
            )
        )
        raise

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
