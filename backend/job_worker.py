"""Durable background job worker for agent execution."""

import asyncio
import logging
import os
import random
import signal
import socket
import time
import uuid
from typing import Awaitable, Callable, Mapping

import database as db
from crew_runner import AgentOutputError
from crew_runner import run_hiring_committee, run_hiring_recommendation
from finalization import finalize_evaluation
from observability import configure_logging, log_execution_event

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

    log_execution_event(
        logger,
        "job_claimed",
        job=job,
        worker_id=worker_id,
        status="RUNNING",
    )

    if await asyncio.to_thread(db.is_job_cancellation_requested, job["id"]):
        await asyncio.to_thread(db.cancel_job, job["id"], worker_id)
        log_execution_event(
            logger,
            "job_cancelled_before_execution",
            job=job,
            worker_id=worker_id,
            status="CANCELLED",
            cancellation_requested=True,
        )
        return True

    started_at = time.monotonic()
    log_execution_event(
        logger,
        "job_started",
        job=job,
        worker_id=worker_id,
        status="RUNNING",
    )
    try:
        handler = handlers.get(job["job_type"])
        if handler is None:
            raise ValueError(f"No handler registered for job type {job['job_type']}")
        await handler(job["payload"])
    except Exception as exc:
        logger.error(
            "Durable job handler failed",
            extra={
                "event": "job_handler_exception",
                "execution_fields": {
                    "job_id": job["id"],
                    "worker_id": worker_id,
                    "stage": job["job_type"],
                    "attempt": job.get("attempts"),
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                },
            },
        )
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
        log_execution_event(
            logger,
            "job_failed",
            job=job,
            worker_id=worker_id,
            status=status or "OWNERSHIP_LOST",
            duration_ms=(time.monotonic() - started_at) * 1000,
            error_type=type(exc).__name__,
            level=logging.WARNING,
        )
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
        log_execution_event(
            logger,
            "job_cancelled_by_worker",
            job=job,
            worker_id=worker_id,
            status="PENDING",
            duration_ms=(time.monotonic() - started_at) * 1000,
            error_type="CancelledError",
        )
        raise

    if await asyncio.to_thread(db.is_job_cancellation_requested, job["id"]):
        if not await asyncio.to_thread(db.cancel_job, job["id"], worker_id):
            log_execution_event(
                logger,
                "job_cancellation_ownership_lost",
                job=job,
                worker_id=worker_id,
                status="OWNERSHIP_LOST",
                duration_ms=(time.monotonic() - started_at) * 1000,
                cancellation_requested=True,
                level=logging.ERROR,
            )
        else:
            log_execution_event(
                logger,
                "job_cancelled_after_execution",
                job=job,
                worker_id=worker_id,
                status="CANCELLED",
                duration_ms=(time.monotonic() - started_at) * 1000,
                cancellation_requested=True,
            )
        return True

    completed = await asyncio.to_thread(db.complete_job, job["id"], worker_id)
    log_execution_event(
        logger,
        "job_completed" if completed else "job_completion_ownership_lost",
        job=job,
        worker_id=worker_id,
        status="COMPLETED" if completed else "OWNERSHIP_LOST",
        duration_ms=(time.monotonic() - started_at) * 1000,
        level=logging.INFO if completed else logging.ERROR,
    )
    return True


async def run_forever(
    worker_id: str | None = None,
    *,
    handlers: Mapping[str, JobHandler] = DEFAULT_HANDLERS,
    poll_seconds: int = 5,
    lease_seconds: int = 300,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Continuously drain jobs until a cooperative stop signal is received."""
    while stop_event is None or not stop_event.is_set():
        found_work = await run_once(
            worker_id,
            handlers=handlers,
            lease_seconds=lease_seconds,
        )
        if not found_work:
            if stop_event is None:
                await asyncio.sleep(poll_seconds)
            else:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
    logger.info(
        "worker_stopped",
        extra={
            "event": "worker_stopped",
            "execution_fields": {
                "worker_id": worker_id or "default",
                "status": "STOPPED",
            },
        },
    )


async def _run_worker_process() -> None:
    """Run the worker with signal-driven cooperative shutdown."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop(signum, _frame) -> None:
        logger.info(
            "worker_stop_requested",
            extra={
                "event": "worker_stop_requested",
                "execution_fields": {
                    "signal": signal.Signals(signum).name,
                    "status": "STOP_REQUESTED",
                },
            },
        )
        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    await run_forever(stop_event=stop_event)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(_run_worker_process())
