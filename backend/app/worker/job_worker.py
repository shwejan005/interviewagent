"""Durable background job worker for agent execution."""

import asyncio
import logging
import os
import random
import signal
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Mapping

from dotenv import load_dotenv

load_dotenv()

from app.config import database as db
from app.ai_interview import repository as ai_interview_db
from app.ai_interview.service import (
    assess_application_answer,
    generate_application_report,
    run_application_screening,
)
from app.evaluation.pipeline import (
    handle_behavioral,
    handle_screening,
    handle_technical,
)
from app.evaluation.runner import AgentOutputError, run_hiring_committee, run_hiring_recommendation
from app.evaluation.service import finalize_evaluation
from app.hiring import repository as hiring_db
from app.shared.observability import configure_logging, log_execution_event
from app.shared import notification_repository as notification_db
from app.shared.notifications import send_application_interview_ready_email

logger = logging.getLogger(__name__)

FINAL_DECISION_JOB = "final_decision"
SCREENING_JOB = "screening"
TECHNICAL_JOB = "technical_evaluation"
BEHAVIORAL_JOB = "behavioral_evaluation"
APPLICATION_SCREENING_JOB = "application_screening"
APPLICATION_INTERVIEW_ANSWER_JOB = "application_interview_answer"
APPLICATION_INTERVIEW_REPORT_JOB = "application_interview_report"
APPLICATION_INTERVIEW_READY_NOTIFICATION_JOB = "application_interview_ready_notification"
APPLICATION_AI_INVITATION_REMINDER_JOB = "application_ai_interview_invitation_reminder"
APPLICATION_AI_INVITATION_EXPIRY_JOB = "application_ai_interview_invitation_expiry"
HUMAN_INTERVIEW_SCHEDULED_NOTIFICATION_JOB = "human_interview_scheduled_notification"
APPLICATION_INTERVIEW_REPORT_READY_NOTIFICATION_JOB = "application_interview_report_ready_notification"
APPLICATION_AI_INTERVIEW_DAILY_DIGEST_JOB = "application_ai_interview_daily_digest"
CANDIDATE_INTERVIEW_AGENDA_HREF = "/interviews"
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


async def _with_org_context(payload: dict, operation: Callable[[], Awaitable[None]]) -> None:
    db.set_request_db_context(user_id=None, org_id=int(payload["org_id"]), is_worker=True)
    try:
        await operation()
    finally:
        db.clear_request_db_context()


async def _handle_application_screening(payload: dict) -> None:
    await _with_org_context(
        payload,
        lambda: run_application_screening(int(payload["interview_id"])),
    )


async def _handle_application_interview_answer(payload: dict) -> None:
    await _with_org_context(
        payload,
        lambda: assess_application_answer(int(payload["interview_id"]), int(payload["turn_id"])),
    )


async def _handle_application_interview_report(payload: dict) -> None:
    await _with_org_context(
        payload,
        lambda: generate_application_report(int(payload["interview_id"])),
    )


async def _handle_application_interview_ready_notification(payload: dict) -> None:
    async def send() -> None:
        user = await asyncio.to_thread(db.get_user, int(payload["candidate_user_id"]))
        org = await asyncio.to_thread(db.get_organization, int(payload["org_id"]))
        if user is None or org is None:
            logger.warning("AI interview notification skipped: recipient or organization missing.")
            return
        await asyncio.to_thread(
            notification_db.create_notification,
            int(payload["candidate_user_id"]),
            "AI_INTERVIEW_READY",
            "Your next interview step is ready",
            f"Your AI interview for {payload.get('role', 'this role')} is ready. Questions are text; answers are by voice.",
            href=CANDIDATE_INTERVIEW_AGENDA_HREF,
            org_id=int(payload["org_id"]),
            application_id=int(payload["application_id"]),
            dedupe_key=f"ai-interview-ready:{payload['application_id']}:{payload['interview_id']}:{payload.get('invitation_round', 0)}",
        )
        delivery = await asyncio.to_thread(
            send_application_interview_ready_email,
            user["email"],
            str(payload.get("role", "the role")),
            org["name"],
        )
        if delivery == "failed":
            raise RuntimeError("AI interview notification delivery failed; retry this notification job")

    await _with_org_context(payload, send)


async def _handle_ai_interview_invitation_reminder(payload: dict) -> None:
    async def remind() -> None:
        current = await asyncio.to_thread(
            ai_interview_db.record_invitation_reminder,
            int(payload["interview_id"]),
            int(payload["reminder_number"]),
            int(payload.get("invitation_round", 0)),
        )
        if current is None:
            return
        await asyncio.to_thread(
            notification_db.create_notification,
            int(current["candidate_user_id"]),
            "AI_INTERVIEW_REMINDER",
            "Your AI interview invitation is waiting",
            f"Join the AI interview for {payload.get('role', 'this role')} before the invitation expires.",
            href=CANDIDATE_INTERVIEW_AGENDA_HREF,
            org_id=int(current["org_id"]),
            application_id=int(current["application_id"]),
            dedupe_key=f"ai-interview-invitation-reminder:{payload['interview_id']}:{payload.get('invitation_round', 0)}:{payload['reminder_number']}",
        )

    await _with_org_context(payload, remind)


async def _handle_ai_interview_invitation_expiry(payload: dict) -> None:
    async def expire() -> None:
        changed = await asyncio.to_thread(
            ai_interview_db.expire_invitation,
            int(payload["interview_id"]),
            int(payload.get("invitation_round", 0)),
        )
        if not changed:
            return
        application = await asyncio.to_thread(
            hiring_db.get_application,
            int(payload["application_id"]),
            int(payload["org_id"]),
        )
        members = await asyncio.to_thread(db.list_org_members, int(payload["org_id"]))
        recruiter_roles = {"org_owner", "org_admin", "recruiter", "hiring_manager"}
        for member in members:
            if member.get("role_name") not in recruiter_roles:
                continue
            await asyncio.to_thread(
                notification_db.create_notification,
                int(member["user_id"]),
                "AI_INTERVIEW_EXPIRED",
                "AI interview invitation expired",
                f"The candidate's AI interview invitation for {payload.get('role', 'this role')} expired without a start. Review or re-invite them.",
                href=f"/org/postings/{int(application['posting_id'])}" if application else "/org",
                org_id=int(payload["org_id"]),
                application_id=int(payload["application_id"]),
                dedupe_key=f"ai-interview-invitation-expired:{payload['interview_id']}:{payload.get('invitation_round', 0)}:{member['user_id']}",
            )

    await _with_org_context(payload, expire)


async def _handle_human_interview_scheduled_notification(payload: dict) -> None:
    async def notify_participant() -> None:
        body = (
            f"Your {payload.get('participant_role', 'INTERVIEWER').lower()} interview for "
            f"{payload.get('posting_title', 'this role')} is scheduled for "
            f"{payload.get('scheduled_start', 'the selected time')}. Join from your interview agenda in the app."
        )
        await asyncio.to_thread(
            notification_db.create_notification,
            int(payload["user_id"]),
            "HUMAN_INTERVIEW_SCHEDULED",
            "An in-app interview is scheduled",
            body,
            href=CANDIDATE_INTERVIEW_AGENDA_HREF,
            org_id=int(payload["org_id"]),
            application_id=int(payload["application_id"]),
            dedupe_key=f"human-interview-scheduled:{payload['interview_id']}:{payload['user_id']}",
        )

    await _with_org_context(payload, notify_participant)


async def _handle_human_interview_scorecards_ready_notification(payload: dict) -> None:
    async def notify_recruiters() -> None:
        interview = await asyncio.to_thread(hiring_db.get_interview, int(payload["interview_id"]), int(payload["org_id"]))
        if interview is None:
            return
        members = await asyncio.to_thread(db.list_org_members, int(payload["org_id"]))
        recruiter_roles = {"org_owner", "org_admin", "recruiter", "hiring_manager"}
        for member in members:
            if member.get("role_name") not in recruiter_roles:
                continue
            await asyncio.to_thread(
                notification_db.create_notification,
                int(member["user_id"]),
                "HUMAN_INTERVIEW_SCORECARDS_READY",
                "Human interview scorecards ready",
                "All assigned interviewers submitted independent scorecards. Review the panel and decide the next step.",
                href=f"/org/postings/{int(interview['posting_id'])}",
                org_id=int(payload["org_id"]),
                application_id=int(payload["application_id"]),
                dedupe_key=f"human-interview-scorecards-ready:{payload['interview_id']}:{member['user_id']}",
            )

    await _with_org_context(payload, notify_recruiters)


async def _handle_application_interview_report_ready_notification(payload: dict) -> None:
    async def notify_recruiters() -> None:
        application = await asyncio.to_thread(
            hiring_db.get_application,
            int(payload["application_id"]),
            int(payload["org_id"]),
        )
        members = await asyncio.to_thread(db.list_org_members, int(payload["org_id"]))
        roles = {"org_owner", "org_admin", "recruiter", "hiring_manager"}
        for member in members:
            if member.get("role_name") not in roles:
                continue
            await asyncio.to_thread(
                notification_db.create_notification,
                int(member["user_id"]),
                "AI_INTERVIEW_REPORT_READY",
                "AI interview report ready for review",
                "The evidence report and advisory fit nudge are ready. A human recruiter must decide the next step.",
                href=f"/org/postings/{int(application['posting_id'])}" if application else "/org",
                org_id=int(payload["org_id"]),
                application_id=int(payload["application_id"]),
                dedupe_key=f"ai-interview-report-ready:{payload['application_id']}:{member['user_id']}",
            )

    await _with_org_context(payload, notify_recruiters)


async def _handle_application_ai_interview_daily_digest(payload: dict) -> None:
    async def deliver_digest() -> None:
        digest_end = datetime.fromisoformat(str(payload["digest_day"])).replace(hour=17, tzinfo=timezone.utc)
        digest_start = digest_end - timedelta(days=1)
        reports = await asyncio.to_thread(
            hiring_db.list_reports_ready_for_digest,
            int(payload["org_id"]),
            digest_start.isoformat(),
            digest_end.isoformat(),
        )
        if not reports:
            return
        members = await asyncio.to_thread(db.list_org_members, int(payload["org_id"]))
        roles = {"org_owner", "org_admin", "recruiter", "hiring_manager"}
        role_titles = list(dict.fromkeys(str(report["posting_title"]) for report in reports))
        title_summary = ", ".join(role_titles[:4])
        if len(role_titles) > 4:
            title_summary = f"{title_summary}, and {len(role_titles) - 4} more roles"
        body = f"{len(reports)} AI interview report(s) were prepared in the last day for: {title_summary}. Review the evidence and record a human decision."
        for member in members:
            if member.get("role_name") not in roles:
                continue
            await asyncio.to_thread(
                notification_db.create_notification,
                int(member["user_id"]),
                "AI_INTERVIEW_DAILY_DIGEST",
                "Daily AI interview report digest",
                body,
                href="/org",
                org_id=int(payload["org_id"]),
                dedupe_key=f"ai-interview-daily-digest:{payload['org_id']}:{payload['digest_day']}:{member['user_id']}",
            )

    await _with_org_context(payload, deliver_digest)


DEFAULT_HANDLERS: Mapping[str, JobHandler] = {
    FINAL_DECISION_JOB: _handle_final_decision,
    SCREENING_JOB: handle_screening,
    TECHNICAL_JOB: handle_technical,
    BEHAVIORAL_JOB: handle_behavioral,
    APPLICATION_SCREENING_JOB: _handle_application_screening,
    APPLICATION_INTERVIEW_ANSWER_JOB: _handle_application_interview_answer,
    APPLICATION_INTERVIEW_REPORT_JOB: _handle_application_interview_report,
    APPLICATION_INTERVIEW_READY_NOTIFICATION_JOB: _handle_application_interview_ready_notification,
    APPLICATION_AI_INVITATION_REMINDER_JOB: _handle_ai_interview_invitation_reminder,
    APPLICATION_AI_INVITATION_EXPIRY_JOB: _handle_ai_interview_invitation_expiry,
    HUMAN_INTERVIEW_SCHEDULED_NOTIFICATION_JOB: _handle_human_interview_scheduled_notification,
    APPLICATION_INTERVIEW_REPORT_READY_NOTIFICATION_JOB: _handle_application_interview_report_ready_notification,
    APPLICATION_AI_INTERVIEW_DAILY_DIGEST_JOB: _handle_application_ai_interview_daily_digest,
    "human_interview_scorecards_ready_notification": _handle_human_interview_scorecards_ready_notification,
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
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat(job["id"], worker_id, lease_seconds, heartbeat_stop))
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
        status = await _fail_job(
            job,
            worker_id,
            exc,
            retry_delay_seconds=retry_delay_seconds,
            retry_base_delay_seconds=retry_base_delay_seconds,
            retry_max_delay_seconds=retry_max_delay_seconds,
        )
        log_execution_event(logger, "job_failed", job=job, worker_id=worker_id,
                            status=status or "OWNERSHIP_LOST",
                            duration_ms=(time.monotonic() - started_at) * 1000,
                            error_type=type(exc).__name__, level=logging.WARNING)
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
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)

    if await _cancel_after_execution(job, worker_id, started_at):
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


async def _heartbeat(job_id: int, worker_id: str, lease_seconds: int, stop_event: asyncio.Event) -> None:
    interval = max(1.0, lease_seconds / 3)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            alive = await asyncio.to_thread(db.heartbeat_job, job_id, worker_id)
            if not alive:
                logger.error("Lost lease for job %s", job_id)
                return


async def _fail_job(
    job: dict,
    worker_id: str,
    error: Exception,
    *,
    retry_delay_seconds: float | None,
    retry_base_delay_seconds: float,
    retry_max_delay_seconds: float,
) -> str | None:
    logger.exception(
        "Durable job handler failed",
        extra={
            "event": "job_handler_exception",
            "execution_fields": {
                "job_id": job["id"],
                "worker_id": worker_id,
                "stage": job["job_type"],
                "attempt": job.get("attempts"),
                "status": "FAILED",
                "error_type": type(error).__name__,
            },
        },
    )
    delay = retry_delay_seconds
    if delay is None:
        delay = _retry_delay(job["attempts"], base_seconds=retry_base_delay_seconds, max_seconds=retry_max_delay_seconds)
    status = await asyncio.to_thread(
        db.fail_job,
        job["id"],
        worker_id,
        str(error),
        retry_delay_seconds=delay,
        retryable=not isinstance(error, AgentOutputError),
    )
    if status == "DEAD":
        await _mark_ai_interview_job_for_review(job)
    return status


async def _mark_ai_interview_job_for_review(job: dict) -> None:
    if job["job_type"] not in {
        APPLICATION_SCREENING_JOB,
        APPLICATION_INTERVIEW_ANSWER_JOB,
        APPLICATION_INTERVIEW_REPORT_JOB,
    }:
        return
    try:
        db.set_request_db_context(user_id=None, org_id=int(job["payload"]["org_id"]), is_worker=True)
        await asyncio.to_thread(
            ai_interview_db.mark_job_failure,
            int(job["payload"]["interview_id"]),
            "AI_JOB_EXHAUSTED",
            "The automated interview service could not complete this step. Human review is required.",
        )
    except Exception:
        logger.exception("Could not mark exhausted application AI-interview job for review")
    finally:
        db.clear_request_db_context()


async def _cancel_after_execution(job: dict, worker_id: str, started_at: float) -> bool:
    if not await asyncio.to_thread(db.is_job_cancellation_requested, job["id"]):
        return False
    cancelled = await asyncio.to_thread(db.cancel_job, job["id"], worker_id)
    log_execution_event(
        logger,
        "job_cancelled_after_execution" if cancelled else "job_cancellation_ownership_lost",
        job=job,
        worker_id=worker_id,
        status="CANCELLED" if cancelled else "OWNERSHIP_LOST",
        duration_ms=(time.monotonic() - started_at) * 1000,
        cancellation_requested=True,
        level=logging.INFO if cancelled else logging.ERROR,
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
    await asyncio.to_thread(db.init_db)
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
