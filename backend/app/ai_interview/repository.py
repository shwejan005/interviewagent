"""Persistence for application-owned screening and interview sessions.

Candidate and recruiter API reads deliberately use projections that never
return frozen resume input or internal assessment payloads. Worker-only reads
are explicit and expected to run with the organization RLS context set.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config.database import USE_POSTGRES, _get_conn, _ph, _row_to_dict
from app.hiring.repository import ApplicationStage, can_transition

_SQLITE_BEGIN_IMMEDIATE = "BEGIN IMMEDIATE"
_POSTGRES_FOR_UPDATE = " FOR UPDATE"
_AI_INTERVIEW_NOT_FOUND = "AI interview not found"
_INTERVIEW_TURN_NOT_FOUND = "Interview turn not found"
_DEFAULT_ROLE_LABEL = "this role"
_UTC_SUFFIX = "+00:00"


def _db_bool(value: bool):
    return bool(value) if USE_POSTGRES else int(bool(value))


class InterviewNotFoundError(LookupError):
    pass


class InterviewConflictError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value, fallback):
    if value is None or value == "":
        return fallback
    return json.loads(value) if isinstance(value, str) else value


def _apply_pinned_posting_context(run: dict) -> dict:
    policy = run.get("policy_snapshot") or {}
    run["role"] = policy.get("posting_title") or run.get("role", "")
    run["posting_description"] = policy.get("posting_description") or run.get("posting_description", "")
    return run


def _enqueue_job(
    cur,
    job_type: str,
    payload: dict,
    idempotency_key: str,
    tenant_key: str,
    *,
    delay_seconds: float = 0,
) -> int:
    p = _ph()
    encoded = json.dumps(payload, separators=(",", ":"))
    if USE_POSTGRES:
        cur.execute(
            f"""INSERT INTO background_jobs
                (job_type, payload, max_attempts, idempotency_key, tenant_key, available_at)
                VALUES ({p}, {p}, 5, {p}, {p}, CURRENT_TIMESTAMP + ({p} * INTERVAL '1 second'))
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING RETURNING id""",
            (job_type, encoded, idempotency_key, tenant_key, delay_seconds),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row["id"])
        cur.execute(f"SELECT id FROM background_jobs WHERE idempotency_key = {p}", (idempotency_key,))
        existing = cur.fetchone()
        if existing is None:
            raise RuntimeError("Idempotent AI-interview job lookup failed")
        return int(existing["id"])
    try:
        cur.execute(
            f"""INSERT INTO background_jobs
                (job_type, payload, max_attempts, idempotency_key, tenant_key, available_at)
                VALUES ({p}, {p}, 5, {p}, {p}, datetime('now', {p}))""",
            (job_type, encoded, idempotency_key, tenant_key, f"+{delay_seconds} seconds"),
        )
        return int(cur.lastrowid)
    except Exception as exc:
        # Only resolve the unique-key conflict; all other DB failures propagate.
        cur.execute(f"SELECT id FROM background_jobs WHERE idempotency_key = {p}", (idempotency_key,))
        existing = cur.fetchone()
        if existing is None:
            raise exc
        return int(existing["id"])


def _queue_invitation_lifecycle_jobs(
    cur,
    *,
    application_id: int,
    interview_id: int,
    org_id: int,
    candidate_user_id: int,
    role: str,
    window_days: int,
    invitation_round: int = 0,
) -> datetime:
    window_days = max(1, min(30, int(window_days)))
    expires_at = datetime.now(timezone.utc) + timedelta(days=window_days)
    payload = {
        "application_id": application_id,
        "interview_id": interview_id,
        "candidate_user_id": candidate_user_id,
        "org_id": org_id,
        "role": role,
        "invitation_round": invitation_round,
    }
    seconds = window_days * 24 * 60 * 60
    reminder_delays = (max(60, seconds // 2), max(60, seconds - 24 * 60 * 60))
    for reminder_number, delay in enumerate(reminder_delays, start=1):
        _enqueue_job(
            cur,
            "application_ai_interview_invitation_reminder",
            {**payload, "reminder_number": reminder_number},
            f"application-ai-invitation-reminder:{application_id}:{interview_id}:{invitation_round}:{reminder_number}",
            f"org:{org_id}",
            delay_seconds=delay,
        )
    _enqueue_job(
        cur,
        "application_ai_interview_invitation_expiry",
        payload,
        f"application-ai-invitation-expiry:{application_id}:{interview_id}:{invitation_round}",
        f"org:{org_id}",
        delay_seconds=seconds,
    )
    return expires_at


def insert_application_workflow_in_transaction(
    cur,
    *,
    application_id: int,
    org_id: int,
    candidate_user_id: int,
    policy_snapshot: dict,
    screening_input: dict,
) -> int:
    """Create the screening workflow and durable job in the caller's app txn."""
    p = _ph()
    values = (
        application_id,
        org_id,
        candidate_user_id,
        str(policy_snapshot.get("rubric_version", "posting-v1")),
        json.dumps(policy_snapshot, separators=(",", ":")),
        json.dumps(screening_input, separators=(",", ":")),
    )
    if USE_POSTGRES:
        cur.execute(
            f"""INSERT INTO application_ai_interviews
                (application_id, org_id, candidate_user_id, rubric_version,
                 policy_snapshot_json, screening_input_json, status, phase)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 'SCREENING_QUEUED', 'SCREENING')
                RETURNING id""",
            values,
        )
        interview_id = int(cur.fetchone()["id"])
    else:
        cur.execute(
            f"""INSERT INTO application_ai_interviews
                (application_id, org_id, candidate_user_id, rubric_version,
                 policy_snapshot_json, screening_input_json, status, phase)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 'SCREENING_QUEUED', 'SCREENING')""",
            values,
        )
        interview_id = int(cur.lastrowid)

    _enqueue_job(
        cur,
        "application_screening",
        {"application_id": application_id, "interview_id": interview_id, "org_id": org_id},
        f"application-screening:{application_id}",
        f"org:{org_id}",
    )
    return interview_id


def get_internal(application_id: int, org_id: Optional[int] = None) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        if org_id is None:
            cur.execute(
                f"SELECT ai.*, a.current_stage, a.status AS application_status, a.withdrawn_at, "
                f"a.posting_id, a.candidate_user_id AS application_candidate_user_id, "
                f"a.org_id AS application_org_id, a.evaluation_id AS application_evaluation_id, "
                f"jp.title AS role, jp.description AS posting_description "
                f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
                f"JOIN job_postings jp ON jp.id = a.posting_id WHERE ai.application_id = {p} "
                f"ORDER BY ai.attempt_no DESC LIMIT 1",
                (application_id,),
            )
        else:
            cur.execute(
                f"SELECT ai.*, a.current_stage, a.status AS application_status, a.withdrawn_at, "
                f"a.posting_id, a.candidate_user_id AS application_candidate_user_id, "
                f"a.org_id AS application_org_id, a.evaluation_id AS application_evaluation_id, "
                f"jp.title AS role, jp.description AS posting_description "
                f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
                f"JOIN job_postings jp ON jp.id = a.posting_id "
                f"WHERE ai.application_id = {p} AND ai.org_id = {p} "
                f"ORDER BY ai.attempt_no DESC LIMIT 1",
                (application_id, org_id),
            )
        row = _row_to_dict(cur.fetchone())
    if row is None:
        return None
    row["policy_snapshot"] = _json(row.pop("policy_snapshot_json", None), {})
    row["screening_input"] = _json(row.pop("screening_input_json", None), {})
    row["screening_result"] = _json(row.pop("screening_result_json", None), {})
    row["technical_questions"] = _json(row.pop("technical_questions_json", None), [])
    row["behavioral_questions"] = _json(row.pop("behavioral_questions_json", None), [])
    return _apply_pinned_posting_context(row)


def get_internal_by_id(interview_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT ai.*, a.current_stage, a.status AS application_status, a.withdrawn_at, "
            f"a.posting_id, a.candidate_user_id AS application_candidate_user_id, "
            f"a.org_id AS application_org_id, a.evaluation_id AS application_evaluation_id, "
            f"jp.title AS role, jp.description AS posting_description "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id WHERE ai.id = {p}",
            (interview_id,),
        )
        row = _row_to_dict(cur.fetchone())
    if row is None:
        return None
    row["policy_snapshot"] = _json(row.pop("policy_snapshot_json", None), {})
    row["screening_input"] = _json(row.pop("screening_input_json", None), {})
    row["screening_result"] = _json(row.pop("screening_result_json", None), {})
    row["technical_questions"] = _json(row.pop("technical_questions_json", None), [])
    row["behavioral_questions"] = _json(row.pop("behavioral_questions_json", None), [])
    return _apply_pinned_posting_context(row)


def get_candidate_view(application_id: int, candidate_user_id: int) -> Optional[dict]:
    """Return only candidate-safe state and turns, never screening inputs or scores."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id, application_id, status, phase, modality, rubric_version, consent_version, current_question_id, "
            f"invitation_expires_at, policy_snapshot_json, "
            f"created_at, updated_at, started_at, completed_at "
            f"FROM application_ai_interviews WHERE application_id = {p} AND candidate_user_id = {p} "
            f"ORDER BY attempt_no DESC LIMIT 1",
            (application_id, candidate_user_id),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None:
            return None
        cur.execute(
            f"SELECT id, sequence_no, phase, question_type, competency_key, difficulty, "
            f"question_text, draft_answer_text, draft_updated_at, answer_text, answer_source, state FROM application_ai_interview_turns "
            f"WHERE interview_id = {p} ORDER BY sequence_no",
            (run["id"],),
        )
        turns = [_row_to_dict(row) for row in cur.fetchall()]
    run["turns"] = turns
    policy = _json(run.pop("policy_snapshot_json", None), {})
    settings = policy.get("interview_settings") or {}
    run["role_level"] = settings.get("role_level", "MID")
    run["candidate_notice_version"] = policy.get("candidate_notice_version", "ai-interview-v1")
    return run


def list_candidate_agenda(user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    """Return candidate-safe AI interview invitations and progress for the agenda."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT ai.application_id, ai.status, ai.phase, ai.modality, ai.created_at, "
            f"ai.updated_at, ai.started_at, ai.completed_at, ai.invitation_expires_at, jp.title AS posting_title, "
            f"o.name AS org_name FROM application_ai_interviews ai "
            f"JOIN applications a ON a.id = ai.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id "
            f"JOIN organizations o ON o.id = ai.org_id "
            f"WHERE ai.candidate_user_id = {p} AND a.withdrawn_at IS NULL "
            f"AND ai.status IN ('SCREENING_QUEUED', 'SCREENING', 'INTERVIEW_READY', 'INTERVIEW_IN_PROGRESS', 'ANSWER_PROCESSING', "
            f"'REPORT_PENDING', 'REPORT_READY', 'REVIEW_REQUIRED', 'EXPIRED') "
            f"AND ai.attempt_no = (SELECT MAX(latest.attempt_no) FROM application_ai_interviews latest "
            f"WHERE latest.application_id = ai.application_id) "
            f"ORDER BY COALESCE(ai.started_at, ai.created_at) DESC, ai.application_id DESC "
            f"LIMIT {p} OFFSET {p}",
            (user_id, limit, offset),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def get_recruiter_view(application_id: int, org_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id, application_id, status, phase, rubric_version, screening_result_json, "
            f"error_code, updated_at, started_at, completed_at "
            f"FROM application_ai_interviews WHERE application_id = {p} AND org_id = {p} "
            f"ORDER BY attempt_no DESC LIMIT 1",
            (application_id, org_id),
        )
        row = _row_to_dict(cur.fetchone())
    if row is not None:
        row["screening_result"] = _json(row.pop("screening_result_json", None), {})
    return row


def ensure_evaluation(interview_id: int) -> int:
    """Create the linked evaluation and attach it exactly once."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.evaluation_id, ai.application_id, ai.org_id, ai.candidate_user_id, ai.policy_snapshot_json, "
            f"jp.title AS role, u.full_name AS candidate_name "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id JOIN users u ON u.id = a.candidate_user_id "
            f"WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            raise InterviewNotFoundError(_AI_INTERVIEW_NOT_FOUND)
        if row["evaluation_id"]:
            return int(row["evaluation_id"])
        policy_snapshot = _json(row.pop("policy_snapshot_json", None), {})
        role = policy_snapshot.get("posting_title") or row["role"]
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
                f"VALUES ({p}, '', {p}, {p}, {p}) RETURNING id",
                (row["candidate_name"] or "", role, row["org_id"], row["candidate_user_id"]),
            )
            evaluation_id = int(cur.fetchone()["id"])
        else:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
                f"VALUES ({p}, '', {p}, {p}, {p})",
                (row["candidate_name"] or "", role, row["org_id"], row["candidate_user_id"]),
            )
            evaluation_id = int(cur.lastrowid)
        cur.execute(
            f"UPDATE application_ai_interviews SET evaluation_id = {p}, updated_at = {_now_sql()} WHERE id = {p}",
            (evaluation_id, interview_id),
        )
        cur.execute(
            f"UPDATE applications SET evaluation_id = {p}, updated_at = {_now_sql()} "
            f"WHERE id = {p} AND org_id = {p} AND evaluation_id IS NULL",
            (evaluation_id, row["application_id"], row["org_id"]),
        )
        return evaluation_id


def _now_sql() -> str:
    return "CURRENT_TIMESTAMP" if USE_POSTGRES else "datetime('now')"


def begin_screening(interview_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.status, ai.application_id, ai.org_id, a.current_stage, a.withdrawn_at "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        if row["withdrawn_at"]:
            cur.execute(
                f"UPDATE application_ai_interviews SET status = 'CANCELLED', updated_at = {_now_sql()} WHERE id = {p}",
                (interview_id,),
            )
            return {"status": "CANCELLED", "claimed": False}
        if row["current_stage"] in (str(ApplicationStage.REJECTED), str(ApplicationStage.HIRED), str(ApplicationStage.WITHDRAWN)):
            cur.execute(
                f"UPDATE application_ai_interviews SET status = 'CANCELLED', screening_input_json = '{{}}', "
                f"updated_at = {_now_sql()} WHERE id = {p}",
                (interview_id,),
            )
            return {"status": "CANCELLED", "claimed": False}
        if row["current_stage"] not in (str(ApplicationStage.APPLIED), str(ApplicationStage.SCREENING)):
            cur.execute(
                f"UPDATE application_ai_interviews SET status = 'REVIEW_REQUIRED', "
                f"error_code = 'APPLICATION_STAGE_CHANGED', screening_input_json = '{{}}', "
                f"error_message = 'Application stage changed before automatic screening began.', "
                f"updated_at = {_now_sql()} WHERE id = {p}",
                (interview_id,),
            )
            return {"status": "REVIEW_REQUIRED", "claimed": False}
        if row["status"] in ("CANCELLED", "EXPIRED", "REPORT_READY", "COMPLETED", "INTERVIEW_READY", "INTERVIEW_IN_PROGRESS", "ANSWER_PROCESSING", "REPORT_PENDING"):
            return {"status": row["status"], "claimed": False}
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'SCREENING', updated_at = {_now_sql()} "
            f"WHERE id = {p} AND status IN ('SCREENING_QUEUED', 'SCREENING')",
            (interview_id,),
        )
        if row["current_stage"] == str(ApplicationStage.APPLIED):
            _stage_change(
                cur,
                row["application_id"],
                row["org_id"],
                str(ApplicationStage.SCREENING),
                "Automatic application screening started.",
            )
        return {"status": "SCREENING", "claimed": cur.rowcount == 1}


def _stage_change(
    cur,
    application_id: int,
    org_id: int,
    target: str,
    note: str,
    *,
    actor_user_id: Optional[int] = None,
    is_automated: bool = True,
) -> None:
    p = _ph()
    lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
    cur.execute(
        f"SELECT current_stage FROM applications WHERE id = {p} AND org_id = {p}{lock}",
        (application_id, org_id),
    )
    row = cur.fetchone()
    if row is None:
        raise InterviewNotFoundError("Application not found")
    current = str(row["current_stage"])
    if current == target:
        return
    if not can_transition(current, target):
        raise InterviewConflictError(f"Cannot move application from {current} to {target}")
    status = target if target in {"HIRED", "REJECTED", "WITHDRAWN"} else "IN_PROGRESS"
    cur.execute(
        f"UPDATE applications SET current_stage = {p}, status = {p}, updated_at = {_now_sql()} "
        f"WHERE id = {p} AND org_id = {p}",
        (target, status, application_id, org_id),
    )
    cur.execute(
        f"INSERT INTO application_events (application_id, org_id, event_type, from_stage, to_stage, "
        f"actor_user_id, is_automated, note) VALUES ({p}, {p}, 'stage_changed', {p}, {p}, {p}, {p}, {p})",
        (application_id, org_id, current, target, actor_user_id, _db_bool(is_automated), note),
    )


def _insert_turn(cur, *, run: dict, sequence_no: int, phase: str, question: dict, question_type: str) -> int:
    p = _ph()
    values = (
        run["id"], run["application_id"], run["org_id"], run["candidate_user_id"],
        sequence_no, phase, question_type, question["competency_key"],
        question["difficulty"], question["question"],
    )
    sql = (
        f"INSERT INTO application_ai_interview_turns "
        f"(interview_id, application_id, org_id, candidate_user_id, sequence_no, phase, "
        f"question_type, competency_key, difficulty, question_text) "
        f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})"
    )
    if USE_POSTGRES:
        cur.execute(sql + " RETURNING id", values)
        return int(cur.fetchone()["id"])
    cur.execute(sql, values)
    return int(cur.lastrowid)


def _create_evaluation_in_transaction(cur, *, run: dict) -> int:
    p = _ph()
    if USE_POSTGRES:
        cur.execute(
            f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
            f"VALUES ({p}, '', {p}, {p}, {p}) RETURNING id",
            (run.get("candidate_name") or "", run["role"], run["org_id"], run["candidate_user_id"]),
        )
        evaluation_id = int(cur.fetchone()["id"])
    else:
        cur.execute(
            f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
            f"VALUES ({p}, '', {p}, {p}, {p})",
            (run.get("candidate_name") or "", run["role"], run["org_id"], run["candidate_user_id"]),
        )
        evaluation_id = int(cur.lastrowid)
    cur.execute(
        f"UPDATE application_ai_interviews SET evaluation_id = {p}, updated_at = {_now_sql()} WHERE id = {p}",
        (evaluation_id, run["id"]),
    )
    cur.execute(
        f"UPDATE applications SET evaluation_id = {p}, updated_at = {_now_sql()} "
        f"WHERE id = {p} AND org_id = {p} AND evaluation_id IS NULL",
        (evaluation_id, run["application_id"], run["org_id"]),
    )
    return evaluation_id


def save_screening_pass(interview_id: int, result: dict, raw_output: str, plan: dict) -> bool:
    """Persist a validated pass, initial turn, and stage transitions atomically."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.*, a.current_stage, a.withdrawn_at, jp.title AS role, "
            f"u.full_name AS candidate_name FROM application_ai_interviews ai "
            f"JOIN applications a ON a.id = ai.application_id JOIN job_postings jp ON jp.id = a.posting_id "
            f"JOIN users u ON u.id = a.candidate_user_id WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None:
            raise InterviewNotFoundError(_AI_INTERVIEW_NOT_FOUND)
        if run["withdrawn_at"] or run["status"] == "CANCELLED":
            return False
        if run["status"] in ("INTERVIEW_READY", "INTERVIEW_IN_PROGRESS", "ANSWER_PROCESSING", "REPORT_PENDING", "REPORT_READY", "COMPLETED"):
            return False
        if run["status"] != "SCREENING":
            raise InterviewConflictError(f"Cannot complete screening from {run['status']}")
        if run["current_stage"] not in (str(ApplicationStage.APPLIED), str(ApplicationStage.SCREENING)):
            cur.execute(
                f"UPDATE application_ai_interviews SET status = 'REVIEW_REQUIRED', "
                f"error_code = 'APPLICATION_STAGE_CHANGED', "
                f"error_message = 'Application stage changed while screening was running.', "
                f"screening_input_json = '{{}}', updated_at = {_now_sql()} WHERE id = {p}",
                (interview_id,),
            )
            return False

        run["candidate_name"] = run.get("candidate_name") or ""
        evaluation_id = run.get("evaluation_id")
        if evaluation_id is None:
            evaluation_id = _create_evaluation_in_transaction(cur, run=run)
        cur.execute(
            f"UPDATE evaluations SET current_round = 2, status = 'IN_PROGRESS', updated_at = {_now_sql()} WHERE id = {p}",
            (evaluation_id,),
        )

        if run["current_stage"] == str(ApplicationStage.APPLIED):
            _stage_change(cur, run["application_id"], run["org_id"], str(ApplicationStage.SCREENING), "Application screening passed the configured automated gate.")
        _stage_change(cur, run["application_id"], run["org_id"], str(ApplicationStage.AI_INTERVIEW), "AI interview prepared automatically after screening pass.")

        technical = plan.get("technical_questions", [])
        behavioral = plan.get("behavioral_questions", [])
        if not technical or not behavioral:
            raise ValueError("Question plan must include technical and behavioral questions")
        policy_snapshot = _json(run.get("policy_snapshot_json"), {})
        invitation_window_days = int((policy_snapshot.get("interview_settings") or {}).get("invitation_window_days", 7))
        invitation_expires_at = _queue_invitation_lifecycle_jobs(
            cur,
            application_id=int(run["application_id"]),
            interview_id=interview_id,
            org_id=int(run["org_id"]),
            candidate_user_id=int(run["candidate_user_id"]),
            role=str(run.get("role") or _DEFAULT_ROLE_LABEL),
            window_days=invitation_window_days,
        )
        cur.execute(
            f"UPDATE application_ai_interviews SET evaluation_id = {p}, status = 'INTERVIEW_READY', "
            f"phase = 'TECHNICAL', technical_questions_json = {p}, behavioral_questions_json = {p}, "
            f"screening_result_json = {p}, screening_input_json = '{{}}', phase_question_index = 0, "
            f"next_turn_sequence = 2, current_question_id = NULL, "
            f"follow_ups_for_question = 0, invitation_expires_at = {p}, invite_reminders_sent = 0, "
            f"updated_at = {_now_sql()} WHERE id = {p}",
            (
                evaluation_id,
                json.dumps(technical, separators=(",", ":")),
                json.dumps(behavioral, separators=(",", ":")),
                json.dumps({**result, "raw_summary": raw_output[:4000]}, separators=(",", ":")),
                invitation_expires_at.isoformat(),
                interview_id,
            ),
        )
        run.update({
            "id": interview_id,
            "application_id": run["application_id"],
            "org_id": run["org_id"],
            "candidate_user_id": run["candidate_user_id"],
        })
        first_turn_id = _insert_turn(cur, run=run, sequence_no=1, phase="TECHNICAL", question=technical[0], question_type="CORE")
        cur.execute(
            f"UPDATE application_ai_interviews SET current_question_id = {p} WHERE id = {p}",
            (first_turn_id, interview_id),
        )
        _enqueue_job(
            cur,
            "application_interview_ready_notification",
            {"application_id": run["application_id"], "interview_id": interview_id, "candidate_user_id": run["candidate_user_id"], "org_id": run["org_id"], "role": run["role"]},
            f"application-ai-ready-notification:{run['application_id']}:{interview_id}",
            f"org:{run['org_id']}",
        )
        return True


def approve_screening_exception(
    application_id: int,
    org_id: int,
    reviewer_user_id: int,
    reason: str,
    plan: dict,
) -> Optional[dict]:
    """A deliberate human decision can send an exception through the interview.

    The core screening path never rejects or invites on a borderline result;
    this explicit override is reserved for an authorized recruiter review.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.*, a.current_stage, a.withdrawn_at, jp.title AS role, "
            f"u.full_name AS candidate_name FROM application_ai_interviews ai "
            f"JOIN applications a ON a.id = ai.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id "
            f"JOIN users u ON u.id = a.candidate_user_id "
            f"WHERE ai.application_id = {p} AND ai.org_id = {p} AND a.org_id = {p} "
            f"ORDER BY ai.attempt_no DESC LIMIT 1{lock}",
            (application_id, org_id, org_id),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None or run["withdrawn_at"]:
            raise InterviewNotFoundError("AI interview not found")
        if run["status"] == "INTERVIEW_READY":
            return {"interview_id": run["id"], "status": run["status"], "duplicate": True}
        if run["status"] != "REVIEW_REQUIRED":
            raise InterviewConflictError(f"Screening exception cannot be approved from {run['status']}")
        if run["current_stage"] != str(ApplicationStage.PENDING_REVIEW):
            raise InterviewConflictError("Application must be in human review before the screening exception can be approved")
        technical = plan.get("technical_questions", [])
        behavioral = plan.get("behavioral_questions", [])
        if not technical or not behavioral:
            raise ValueError("Question plan must include technical and behavioral questions")

        run["candidate_name"] = run.get("candidate_name") or ""
        evaluation_id = run.get("evaluation_id") or _create_evaluation_in_transaction(cur, run=run)
        cur.execute(
            f"UPDATE evaluations SET current_round = 2, status = 'IN_PROGRESS', updated_at = {_now_sql()} WHERE id = {p}",
            (evaluation_id,),
        )
        _stage_change(
            cur,
            application_id,
            org_id,
            str(ApplicationStage.AI_INTERVIEW),
            f"Reviewer approved the screening exception: {reason.strip()}",
            actor_user_id=reviewer_user_id,
            is_automated=False,
        )
        policy = _json(run.get("policy_snapshot_json"), {})
        invitation_window_days = int((policy.get("interview_settings") or {}).get("invitation_window_days", 7))
        invitation_expires_at = _queue_invitation_lifecycle_jobs(
            cur,
            application_id=application_id,
            interview_id=int(run["id"]),
            org_id=org_id,
            candidate_user_id=int(run["candidate_user_id"]),
            role=str(run.get("role") or _DEFAULT_ROLE_LABEL),
            window_days=invitation_window_days,
            invitation_round=int(run.get("reinvite_count") or 0),
        )
        cur.execute(
            f"UPDATE application_ai_interviews SET evaluation_id = {p}, status = 'INTERVIEW_READY', "
            f"phase = 'TECHNICAL', technical_questions_json = {p}, behavioral_questions_json = {p}, "
            f"screening_input_json = '{{}}', current_question_id = NULL, next_turn_sequence = 2, "
            f"phase_question_index = 0, follow_ups_for_question = 0, error_code = NULL, "
            f"error_message = NULL, invitation_expires_at = {p}, invite_reminders_sent = 0, updated_at = {_now_sql()} WHERE id = {p}",
            (
                evaluation_id,
                json.dumps(technical, separators=(",", ":")),
                json.dumps(behavioral, separators=(",", ":")),
                invitation_expires_at.isoformat(),
                run["id"],
            ),
        )
        run.update({"id": run["id"], "application_id": application_id, "org_id": org_id})
        turn_id = _insert_turn(cur, run=run, sequence_no=1, phase="TECHNICAL", question=technical[0], question_type="CORE")
        cur.execute(
            f"UPDATE application_ai_interviews SET current_question_id = {p} WHERE id = {p}",
            (turn_id, run["id"]),
        )
        _enqueue_job(
            cur,
            "application_interview_ready_notification",
            {"application_id": application_id, "interview_id": run["id"], "candidate_user_id": run["candidate_user_id"], "org_id": org_id, "role": run["role"]},
            f"application-ai-ready-notification:{application_id}:{run['id']}",
            f"org:{org_id}",
        )
        return {"interview_id": run["id"], "status": "INTERVIEW_READY", "duplicate": False}


def mark_review_required(interview_id: int, code: str, message: str, screening_result: Optional[dict] = None) -> bool:
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.*, a.withdrawn_at, a.current_stage FROM application_ai_interviews ai "
            f"JOIN applications a ON a.id = ai.application_id WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None:
            return False
        if run["withdrawn_at"] or run["status"] == "CANCELLED":
            return False
        if run["status"] in ("REPORT_READY", "COMPLETED"):
            return False
        if run.get("current_stage") in (str(ApplicationStage.REJECTED), str(ApplicationStage.HIRED), str(ApplicationStage.WITHDRAWN)):
            cur.execute(
                f"UPDATE application_ai_interviews SET status = 'CANCELLED', screening_input_json = '{{}}', "
                f"updated_at = {_now_sql()} WHERE id = {p}",
                (interview_id,),
            )
            return False
        result_json = run.get("screening_result_json") or "{}"
        if screening_result is not None:
            result_json = json.dumps(screening_result, separators=(",", ":"))
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'REVIEW_REQUIRED', "
            f"screening_result_json = {p}, error_code = {p}, error_message = {p}, "
            f"screening_input_json = '{{}}', updated_at = {_now_sql()} WHERE id = {p}",
            (result_json, code[:80], message[:1000], interview_id),
        )
        _stage_change(cur, run["application_id"], run["org_id"], str(ApplicationStage.PENDING_REVIEW), f"Automated assessment requires human review: {code}")
        return True


def start_interview(
    application_id: int,
    candidate_user_id: int,
    notice_version: str,
    modality: str = "TEXT",
) -> Optional[dict]:
    if modality not in {"TEXT", "VOICE"}:
        raise ValueError("Unsupported interview modality")
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.id, ai.status, ai.modality, ai.consent_version, ai.invitation_expires_at, "
            f"a.withdrawn_at, a.current_stage "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"WHERE ai.application_id = {p} AND ai.candidate_user_id = {p} "
            f"ORDER BY ai.attempt_no DESC LIMIT 1{lock}",
            (application_id, candidate_user_id),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None or run["withdrawn_at"]:
            return None
        should_start = _validate_interview_start(run, notice_version, modality)
        if not should_start:
            return {"status": run["status"], "started": False}
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'INTERVIEW_IN_PROGRESS', modality = {p}, "
            f"consent_version = {p}, consent_at = {_now_sql()}, started_at = COALESCE(started_at, {_now_sql()}), "
            f"updated_at = {_now_sql()} WHERE id = {p} AND status = 'INTERVIEW_READY'",
            (modality, notice_version, run["id"]),
        )
        started = cur.rowcount == 1
        for job_prefix in (
            f"application-ai-invitation-reminder:{application_id}:{run['id']}:",
            f"application-ai-invitation-expiry:{application_id}:{run['id']}:",
        ):
            cur.execute(
                f"UPDATE background_jobs SET status = 'CANCELLED', cancellation_requested = {'TRUE' if USE_POSTGRES else '1'}, "
                f"updated_at = {_now_sql()} WHERE status = 'PENDING' AND substr(idempotency_key, 1, {p}) = {p}",
                (len(job_prefix), job_prefix),
            )
        return {"status": "INTERVIEW_IN_PROGRESS", "started": started}


def switch_to_text_accommodation(
    application_id: int,
    candidate_user_id: int,
    notice_version: str,
) -> dict:
    """Let a candidate switch from browser speech to the disclosed text fallback."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.id, ai.status, ai.modality, ai.consent_version "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"WHERE ai.application_id = {p} AND ai.candidate_user_id = {p} "
            f"AND a.withdrawn_at IS NULL ORDER BY ai.attempt_no DESC LIMIT 1{lock}",
            (application_id, candidate_user_id),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None:
            raise InterviewNotFoundError(_AI_INTERVIEW_NOT_FOUND)
        if run["status"] != "INTERVIEW_IN_PROGRESS":
            raise InterviewConflictError("Text accommodation can only be selected during an active interview")
        if run.get("consent_version") != notice_version:
            raise InterviewConflictError("The interview notice changed. Review the current notice before changing modality.")
        if run.get("modality") == "TEXT":
            return {"modality": "TEXT", "duplicate": True}
        cur.execute(
            f"UPDATE application_ai_interviews SET modality = 'TEXT', updated_at = {_now_sql()} "
            f"WHERE id = {p} AND status = 'INTERVIEW_IN_PROGRESS' AND modality = 'VOICE'",
            (run["id"],),
        )
        if cur.rowcount != 1:
            raise InterviewConflictError("The interview changed while selecting the text accommodation")
        return {"modality": "TEXT", "duplicate": False}


def save_answer_draft(
    application_id: int,
    candidate_user_id: int,
    turn_id: int,
    draft_answer_text: str,
) -> dict:
    """Save a private draft for the candidate's current, unanswered interview turn."""
    p = _ph()
    draft_updated_at = _now()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.id AS interview_id, ai.status, ai.current_question_id, t.answer_text, "
            f"a.withdrawn_at, a.current_stage "
            f"FROM application_ai_interviews ai JOIN application_ai_interview_turns t "
            f"ON t.interview_id = ai.id JOIN applications a ON a.id = ai.application_id "
            f"WHERE ai.application_id = {p} AND ai.candidate_user_id = {p} "
            f"AND ai.id = (SELECT latest.id FROM application_ai_interviews latest "
            f"WHERE latest.application_id = {p} AND latest.candidate_user_id = {p} "
            f"ORDER BY latest.attempt_no DESC LIMIT 1) AND t.id = {p} "
            f"AND t.application_id = {p} AND t.candidate_user_id = {p}{lock}",
            (
                application_id,
                candidate_user_id,
                application_id,
                candidate_user_id,
                turn_id,
                application_id,
                candidate_user_id,
            ),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            raise InterviewNotFoundError(_INTERVIEW_TURN_NOT_FOUND)
        if row.get("withdrawn_at") or row.get("current_stage") != str(ApplicationStage.AI_INTERVIEW):
            raise InterviewConflictError("This application is no longer accepting interview drafts")
        if row["status"] != "INTERVIEW_IN_PROGRESS" or int(row.get("current_question_id") or 0) != turn_id:
            raise InterviewConflictError("Drafts can only be saved for the current interview question")
        if row.get("answer_text") is not None:
            raise InterviewConflictError("This interview question already has a submitted answer")
        cur.execute(
            f"UPDATE application_ai_interview_turns SET draft_answer_text = {p}, draft_updated_at = {p} "
            f"WHERE id = {p} AND candidate_user_id = {p} AND answer_text IS NULL",
            (draft_answer_text, draft_updated_at, turn_id, candidate_user_id),
        )
        if cur.rowcount != 1:
            raise InterviewConflictError("This interview question no longer accepts a draft")
        cur.execute(
            f"UPDATE application_ai_interviews SET updated_at = {_now_sql()} "
            f"WHERE id = {p} AND candidate_user_id = {p} AND status = 'INTERVIEW_IN_PROGRESS'",
            (row["interview_id"], candidate_user_id),
        )
        return {
            "turn_id": turn_id,
            "saved": True,
            "draft_answer_text": draft_answer_text,
            "draft_updated_at": draft_updated_at,
        }


def _enqueue_job(
    cur,
    job_type: str,
    payload: dict,
    idempotency_key: str,
    tenant_key: str,
    *,
    delay_seconds: float = 0,
) -> int:
    p = _ph()
    encoded = json.dumps(payload, separators=(",", ":"))
    if USE_POSTGRES:
        cur.execute(
            f"""INSERT INTO background_jobs
                (job_type, payload, max_attempts, idempotency_key, tenant_key, available_at)
                VALUES ({p}, {p}, 5, {p}, {p}, CURRENT_TIMESTAMP + ({p} * INTERVAL '1 second'))
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING RETURNING id""",
            (job_type, encoded, idempotency_key, tenant_key, delay_seconds),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row["id"])
        cur.execute(f"SELECT id FROM background_jobs WHERE idempotency_key = {p}", (idempotency_key,))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Idempotent application interview job lookup failed")
        return int(row["id"])
    try:
        cur.execute(
            f"INSERT INTO background_jobs (job_type, payload, max_attempts, idempotency_key, tenant_key, available_at) "
            f"VALUES ({p}, {p}, 5, {p}, {p}, datetime('now', {p}))",
            (job_type, encoded, idempotency_key, tenant_key, f"+{delay_seconds} seconds"),
        )
        return int(cur.lastrowid)
    except Exception as exc:
        cur.execute(f"SELECT id FROM background_jobs WHERE idempotency_key = {p}", (idempotency_key,))
        row = cur.fetchone()
        if row is None:
            raise exc
        return int(row["id"])


def _validate_answer_application(run: Optional[dict]) -> dict:
    if run is None or run.get("withdrawn_at"):
        raise InterviewNotFoundError("Interview not found")
    terminal = {str(ApplicationStage.REJECTED), str(ApplicationStage.HIRED), str(ApplicationStage.WITHDRAWN)}
    if run["current_stage"] in terminal:
        raise InterviewConflictError("This application is no longer accepting interview answers")
    return run


def _answer_retry_result(cur, run: dict, turn: dict, application_id: int, turn_id: int, answer: str, source: str) -> Optional[dict]:
    if turn["answer_text"] is None:
        return None
    if turn["answer_text"] != answer or turn.get("answer_source", "TEXT") != source:
        raise InterviewConflictError("This question already has a different submitted answer")
    p = _ph()
    cur.execute(
        f"SELECT id FROM background_jobs WHERE idempotency_key = {p}",
        (f"application-ai-answer:{application_id}:{turn_id}",),
    )
    job = cur.fetchone()
    return {"status": run["status"], "job_id": int(job["id"]) if job else None, "duplicate": True}


def _validate_current_answer_turn(cur, run: dict, turn_id: int) -> None:
    p = _ph()
    cur.execute(
        f"SELECT id FROM application_ai_interview_turns WHERE interview_id = {p} "
        "AND state IN ('ASKED', 'ANSWER_QUEUED') ORDER BY sequence_no DESC LIMIT 1",
        (run["id"],),
    )
    current = cur.fetchone()
    if current is None or int(current["id"]) != turn_id:
        raise InterviewConflictError("Answer the current interview question before continuing")


def submit_answer(
    application_id: int,
    candidate_user_id: int,
    turn_id: int,
    answer: str,
    source: str = "TEXT",
) -> dict:
    if source not in {"TEXT", "VOICE"}:
        raise ValueError("Unsupported answer source")
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.id, ai.org_id, ai.status, a.withdrawn_at, a.current_stage FROM application_ai_interviews ai "
            f"JOIN applications a ON a.id = ai.application_id WHERE ai.application_id = {p} "
            f"AND ai.candidate_user_id = {p} ORDER BY ai.attempt_no DESC LIMIT 1{lock}",
            (application_id, candidate_user_id),
        )
        run = _validate_answer_application(_row_to_dict(cur.fetchone()))
        cur.execute(
            f"SELECT * FROM application_ai_interview_turns WHERE id = {p} AND interview_id = {p} "
            f"AND application_id = {p} AND candidate_user_id = {p}",
            (turn_id, run["id"], application_id, candidate_user_id),
        )
        turn = _row_to_dict(cur.fetchone())
        if turn is None:
            raise InterviewNotFoundError(_INTERVIEW_TURN_NOT_FOUND)
        retry = _answer_retry_result(cur, run, turn, application_id, turn_id, answer, source)
        if retry is not None:
            return retry
        if run["status"] != "INTERVIEW_IN_PROGRESS":
            raise InterviewConflictError(f"Interview is not accepting answers ({run['status']})")
        _validate_current_answer_turn(cur, run, turn_id)
        cur.execute(
            f"UPDATE application_ai_interview_turns SET answer_text = {p}, answer_source = {p}, draft_answer_text = '', "
            f"draft_updated_at = NULL, state = 'ANSWER_QUEUED', "
            f"answered_at = {_now_sql()} WHERE id = {p} AND answer_text IS NULL",
            (answer, source, turn_id),
        )
        if cur.rowcount != 1:
            raise InterviewConflictError("This answer has already been submitted")
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'ANSWER_PROCESSING', updated_at = {_now_sql()} "
            f"WHERE id = {p} AND status = 'INTERVIEW_IN_PROGRESS'",
            (run["id"],),
        )
        job_id = _enqueue_job(
            cur,
            "application_interview_answer",
            {"application_id": application_id, "interview_id": run["id"], "turn_id": turn_id, "org_id": run["org_id"]},
            f"application-ai-answer:{application_id}:{turn_id}",
            f"org:{run['org_id']}",
        )
        return {"status": "ANSWER_PROCESSING", "job_id": job_id, "duplicate": False}


def get_answer_context(interview_id: int, turn_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT t.*, ai.policy_snapshot_json, ai.technical_questions_json, "
            f"ai.behavioral_questions_json, ai.phase_question_index, ai.follow_ups_for_question, "
            f"ai.status AS interview_status, ai.evaluation_id, ai.application_id, ai.org_id, "
            f"ai.candidate_user_id, jp.title AS role, jp.description AS posting_description, "
            f"a.withdrawn_at FROM application_ai_interview_turns t "
            f"JOIN application_ai_interviews ai ON ai.id = t.interview_id "
            f"JOIN applications a ON a.id = ai.application_id JOIN job_postings jp ON jp.id = a.posting_id "
            f"WHERE ai.id = {p} AND t.id = {p}",
            (interview_id, turn_id),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None:
            return None
        cur.execute(
            f"SELECT sequence_no, phase, question_type, competency_key, difficulty, question_text, answer_text "
            f"FROM application_ai_interview_turns WHERE interview_id = {p} AND sequence_no < {p} "
            f"AND answer_text IS NOT NULL ORDER BY sequence_no",
            (interview_id, row["sequence_no"]),
        )
        row["prior_turns"] = [_row_to_dict(turn) for turn in cur.fetchall()]
    row["policy_snapshot"] = _json(row.pop("policy_snapshot_json", None), {})
    row["technical_questions"] = _json(row.pop("technical_questions_json", None), [])
    row["behavioral_questions"] = _json(row.pop("behavioral_questions_json", None), [])
    return _apply_pinned_posting_context(row)


def _apply_assessment_row(cur, *, run: dict, turn: dict, assessment: dict) -> dict:
    """Persist an assessment and create the next turn or enqueue report job."""
    p = _ph()
    cur.execute(
        f"UPDATE application_ai_interview_turns SET assessment_json = {p}, state = 'ASSESSED' "
        f"WHERE id = {p} AND state = 'ANSWER_QUEUED'",
        (json.dumps(assessment, separators=(",", ":")), turn["id"]),
    )
    if cur.rowcount == 0:
        cur.execute(f"SELECT state FROM application_ai_interview_turns WHERE id = {p}", (turn["id"],))
        stored = cur.fetchone()
        if stored and stored["state"] == "ASSESSED":
            return {"status": run["status"], "duplicate": True}
        raise InterviewConflictError("Answer turn is no longer queued for assessment")

    phase = turn["phase"]
    settings = run["policy_snapshot"].get("interview_settings", {})
    max_followups = int(settings.get("max_followups_per_question", 1))
    followups_used = int(run.get("follow_ups_for_question", 0))
    followup_question = (assessment.get("follow_up_question") or "").strip()
    prior_question_texts = {item["question_text"].strip().casefold() for item in run["all_turns"]}
    can_follow_up = (
        followup_question
        and followups_used < max_followups
        and len(followup_question) >= 12
        and followup_question.casefold() not in prior_question_texts
    )

    if can_follow_up:
        base_difficulty = int(turn["difficulty"])
        requested = max(1, min(3, int(assessment.get("next_difficulty", base_difficulty))))
        difficulty = max(base_difficulty - 1, min(base_difficulty + 1, requested))
        sequence = run["next_turn_sequence"]
        new_turn_id = _insert_turn(
            cur,
            run=run,
            sequence_no=sequence,
            phase=phase,
            question={"competency_key": turn["competency_key"], "difficulty": difficulty, "question": followup_question},
            question_type="FOLLOW_UP",
        )
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'INTERVIEW_IN_PROGRESS', "
            f"current_question_id = {p}, next_turn_sequence = {p}, "
            f"follow_ups_for_question = follow_ups_for_question + 1, updated_at = {_now_sql()} WHERE id = {p}",
            (new_turn_id, sequence + 1, run["id"]),
        )
        return {"status": "INTERVIEW_IN_PROGRESS", "next_turn_id": new_turn_id, "duplicate": False}

    questions = run["technical_questions"] if phase == "TECHNICAL" else run["behavioral_questions"]
    next_index = int(run["phase_question_index"]) + 1
    if next_index < len(questions):
        next_question = dict(questions[next_index])
        previous_difficulty = int(turn["difficulty"])
        requested_difficulty = max(1, min(3, int(assessment.get("next_difficulty", previous_difficulty))))
        next_question["difficulty"] = max(previous_difficulty - 1, min(previous_difficulty + 1, requested_difficulty))
        sequence = run["next_turn_sequence"]
        new_turn_id = _insert_turn(cur, run=run, sequence_no=sequence, phase=phase, question=next_question, question_type="CORE")
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'INTERVIEW_IN_PROGRESS', "
            f"current_question_id = {p}, phase_question_index = {p}, follow_ups_for_question = 0, "
            f"next_turn_sequence = {p}, updated_at = {_now_sql()} WHERE id = {p}",
            (new_turn_id, next_index, sequence + 1, run["id"]),
        )
        return {"status": "INTERVIEW_IN_PROGRESS", "next_turn_id": new_turn_id, "duplicate": False}

    if phase == "TECHNICAL":
        behavioral = run["behavioral_questions"]
        if not behavioral:
            raise ValueError("Behavioral question plan is missing")
        sequence = run["next_turn_sequence"]
        new_turn_id = _insert_turn(cur, run=run, sequence_no=sequence, phase="BEHAVIORAL", question=behavioral[0], question_type="CORE")
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'INTERVIEW_IN_PROGRESS', phase = 'BEHAVIORAL', "
            f"current_question_id = {p}, phase_question_index = 0, follow_ups_for_question = 0, "
            f"next_turn_sequence = {p}, updated_at = {_now_sql()} WHERE id = {p}",
            (new_turn_id, sequence + 1, run["id"]),
        )
        return {"status": "INTERVIEW_IN_PROGRESS", "next_turn_id": new_turn_id, "duplicate": False}

    cur.execute(
        f"UPDATE application_ai_interviews SET status = 'REPORT_PENDING', phase = 'COMPLETE', "
        f"current_question_id = NULL, completed_at = {_now_sql()}, updated_at = {_now_sql()} WHERE id = {p}",
        (run["id"],),
    )
    job_id = _enqueue_job(
        cur,
        "application_interview_report",
        {"application_id": run["application_id"], "interview_id": run["id"], "org_id": run["org_id"]},
        f"application-ai-report:{run['application_id']}:{run['id']}",
        f"org:{run['org_id']}",
    )
    return {"status": "REPORT_PENDING", "job_id": job_id, "duplicate": False}


def apply_answer_assessment(interview_id: int, turn_id: int, assessment: dict) -> dict:
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.*, a.current_stage, a.withdrawn_at FROM application_ai_interviews ai "
            f"JOIN applications a ON a.id = ai.application_id WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        run_row = _row_to_dict(cur.fetchone())
        if run_row is None:
            raise InterviewNotFoundError(_AI_INTERVIEW_NOT_FOUND)
        if run_row["withdrawn_at"] or run_row["status"] == "CANCELLED":
            return {"status": "CANCELLED", "duplicate": False}
        cur.execute(
            f"SELECT * FROM application_ai_interview_turns WHERE id = {p} AND interview_id = {p}",
            (turn_id, interview_id),
        )
        turn = _row_to_dict(cur.fetchone())
        if turn is None:
            raise InterviewNotFoundError(_INTERVIEW_TURN_NOT_FOUND)
        run = dict(run_row)
        run["policy_snapshot"] = _json(run.pop("policy_snapshot_json", None), {})
        run["technical_questions"] = _json(run.pop("technical_questions_json", None), [])
        run["behavioral_questions"] = _json(run.pop("behavioral_questions_json", None), [])
        cur.execute(
            f"SELECT question_text FROM application_ai_interview_turns WHERE interview_id = {p}",
            (interview_id,),
        )
        run["all_turns"] = [_row_to_dict(row) for row in cur.fetchall()]
        return _apply_assessment_row(cur, run=run, turn=turn, assessment=assessment)


def list_turns_internal(interview_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM application_ai_interview_turns WHERE interview_id = {p} ORDER BY sequence_no",
            (interview_id,),
        )
        rows = [_row_to_dict(row) for row in cur.fetchall()]
    for row in rows:
        row["assessment"] = _json(row.pop("assessment_json", None), {})
    return rows


def _report_run(cur, interview_id: int) -> Optional[dict]:
    p = _ph()
    lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
    cur.execute(
        f"SELECT ai.application_id, ai.org_id, ai.candidate_user_id, ai.evaluation_id, ai.rubric_version, ai.status, "
        f"a.posting_id, a.current_stage, a.withdrawn_at "
        f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
        f"WHERE ai.id = {p}{lock}",
        (interview_id,),
    )
    return _row_to_dict(cur.fetchone())


def _upsert_application_report(
    cur,
    run: dict,
    *,
    competency_scores: list[dict],
    overall_weighted_score: Optional[float],
    recommendation: str,
    interview_details: dict,
) -> None:
    p = _ph()
    columns = (
        "application_id, evaluation_id, posting_id, org_id, competency_scores_json, "
        "overall_weighted_score, recommendation, rubric_version, interview_details_json"
    )
    values = (
        run["application_id"], run["evaluation_id"], run["posting_id"], run["org_id"],
        json.dumps(competency_scores, separators=(",", ":")), overall_weighted_score,
        recommendation, run["rubric_version"], json.dumps(interview_details, separators=(",", ":")),
    )
    if USE_POSTGRES:
        timestamp = "CURRENT_TIMESTAMP"
        updates = (
            "evaluation_id = EXCLUDED.evaluation_id, posting_id = EXCLUDED.posting_id, "
            "org_id = EXCLUDED.org_id, competency_scores_json = EXCLUDED.competency_scores_json, "
            "overall_weighted_score = EXCLUDED.overall_weighted_score, "
            "recommendation = EXCLUDED.recommendation, rubric_version = EXCLUDED.rubric_version, "
            "interview_details_json = EXCLUDED.interview_details_json, generated_at = CURRENT_TIMESTAMP"
        )
    else:
        timestamp = "datetime('now')"
        updates = (
            "evaluation_id = excluded.evaluation_id, posting_id = excluded.posting_id, "
            "org_id = excluded.org_id, competency_scores_json = excluded.competency_scores_json, "
            "overall_weighted_score = excluded.overall_weighted_score, "
            "recommendation = excluded.recommendation, rubric_version = excluded.rubric_version, "
            "interview_details_json = excluded.interview_details_json, generated_at = datetime('now')"
        )
    cur.execute(
        f"INSERT INTO application_interview_reports ({columns}, generated_at) "
        f"VALUES ({', '.join([p] * len(values))}, {timestamp}) "
        f"ON CONFLICT (application_id) DO UPDATE SET {updates}",
        values,
    )


def _complete_linked_evaluation(cur, run: dict, overall_weighted_score: Optional[float]) -> None:
    p = _ph()
    cur.execute(
        f"UPDATE evaluations SET status = 'COMPLETE', current_round = 4, "
        f"overall_score = {p}, updated_at = {_now_sql()} WHERE id = {p}",
        (overall_weighted_score, run["evaluation_id"]),
    )
    if cur.rowcount != 1:
        raise InterviewConflictError("Linked evaluation could not be completed")


def _publish_report_state(cur, interview_id: int, run: dict) -> None:
    if run["current_stage"] == str(ApplicationStage.AI_INTERVIEW):
        _stage_change(
            cur,
            run["application_id"],
            run["org_id"],
            str(ApplicationStage.PENDING_REVIEW),
            "AI interview report is ready for human review.",
        )
    p = _ph()
    cur.execute(
        f"UPDATE application_ai_interviews SET status = 'REPORT_READY', screening_input_json = '{{}}', "
        f"error_code = NULL, error_message = NULL, updated_at = {_now_sql()} WHERE id = {p}",
        (interview_id,),
    )


def persist_application_report(
    interview_id: int,
    *,
    competency_scores: list[dict],
    overall_weighted_score: Optional[float],
    recommendation: str,
    interview_details: dict,
) -> bool:
    """Persist report, evaluation completion, and publication state atomically.

    Withdrawal or a terminal application decision wins if it commits before
    this transaction obtains the application/session locks.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        run = _report_run(cur, interview_id)
        if run is None or run["withdrawn_at"] or run["status"] == "CANCELLED":
            return False
        if run["status"] == "REPORT_READY":
            return True
        if run["status"] != "REPORT_PENDING":
            raise InterviewConflictError(f"Report cannot be persisted from {run['status']}")
        if run["current_stage"] in {
            str(ApplicationStage.REJECTED),
            str(ApplicationStage.HIRED),
            str(ApplicationStage.WITHDRAWN),
        }:
            cur.execute(
                f"UPDATE application_ai_interviews SET status = 'CANCELLED', screening_input_json = '{{}}', "
                f"updated_at = {_now_sql()} WHERE id = {p}",
                (interview_id,),
            )
            return False
        if run["evaluation_id"] is None:
            raise InterviewConflictError("AI interview is missing its evaluation record")
        _upsert_application_report(
            cur,
            run,
            competency_scores=competency_scores,
            overall_weighted_score=overall_weighted_score,
            recommendation=recommendation,
            interview_details=interview_details,
        )
        _complete_linked_evaluation(cur, run, overall_weighted_score)
        _publish_report_state(cur, interview_id, run)
        _enqueue_job(
            cur,
            "application_interview_report_ready_notification",
            {
                "application_id": int(run["application_id"]),
                "interview_id": interview_id,
                "org_id": int(run["org_id"]),
                "candidate_user_id": int(run["candidate_user_id"]),
            },
            f"application-ai-report-ready-notification:{run['application_id']}:{interview_id}",
            f"org:{run['org_id']}",
        )
        now = datetime.now(timezone.utc)
        digest_at = now.replace(hour=17, minute=0, second=0, microsecond=0)
        if now >= digest_at:
            digest_at += timedelta(days=1)
        digest_delay = max(1.0, (digest_at - now).total_seconds())
        digest_day = digest_at.date().isoformat()
        _enqueue_job(
            cur,
            "application_ai_interview_daily_digest",
            {"org_id": int(run["org_id"]), "digest_day": digest_day},
            f"application-ai-daily-digest:{run['org_id']}:{digest_day}",
            f"org:{run['org_id']}",
            delay_seconds=digest_delay,
        )
        return True


def mark_job_failure(interview_id: int, code: str, message: str) -> bool:
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.application_id, ai.org_id, ai.status, a.withdrawn_at, a.current_stage "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None or run["withdrawn_at"] or run["status"] in ("CANCELLED", "REPORT_READY", "COMPLETED"):
            return False
        if run["current_stage"] in (str(ApplicationStage.REJECTED), str(ApplicationStage.HIRED), str(ApplicationStage.WITHDRAWN)):
            cur.execute(
                f"UPDATE application_ai_interviews SET status = 'CANCELLED', screening_input_json = '{{}}', "
                f"updated_at = {_now_sql()} WHERE id = {p}",
                (interview_id,),
            )
            return False
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'REVIEW_REQUIRED', error_code = {p}, "
            f"error_message = {p}, updated_at = {_now_sql()} WHERE id = {p}",
            (code[:80], message[:1000], interview_id),
        )
        _stage_change(cur, run["application_id"], run["org_id"], str(ApplicationStage.PENDING_REVIEW), f"AI interview requires human review: {code}")
        return True


def record_invitation_reminder(interview_id: int, reminder_number: int, invitation_round: int) -> Optional[dict]:
    """Claim a reminder only while the matching invitation is still ready."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.application_id, ai.org_id, ai.candidate_user_id, ai.status, ai.invite_reminders_sent, "
            f"ai.reinvite_count, ai.invitation_expires_at, jp.title AS role "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        row = _row_to_dict(cur.fetchone())
        if row is None or row["status"] != "INTERVIEW_READY":
            return None
        if int(row.get("reinvite_count") or 0) != invitation_round:
            return None
        expires = row.get("invitation_expires_at")
        if expires is not None:
            expires_at = expires if isinstance(expires, datetime) else datetime.fromisoformat(str(expires).replace("Z", _UTC_SUFFIX))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return None
        cur.execute(
            f"UPDATE application_ai_interviews SET invite_reminders_sent = CASE "
            f"WHEN invite_reminders_sent < {p} THEN {p} ELSE invite_reminders_sent END, updated_at = {_now_sql()} "
            f"WHERE id = {p} AND status = 'INTERVIEW_READY' AND reinvite_count = {p}",
            (reminder_number, reminder_number, interview_id, invitation_round),
        )
        if cur.rowcount != 1:
            return None
        return row


def expire_invitation(interview_id: int, invitation_round: int) -> bool:
    """Expire an unstarted AI invite and move it to the recruiter review queue."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.application_id, ai.org_id, ai.status, ai.reinvite_count, ai.invitation_expires_at, "
            f"a.current_stage, a.withdrawn_at FROM application_ai_interviews ai "
            f"JOIN applications a ON a.id = ai.application_id WHERE ai.id = {p}{lock}",
            (interview_id,),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None or run["status"] != "INTERVIEW_READY" or int(run.get("reinvite_count") or 0) != invitation_round:
            return False
        expires = run.get("invitation_expires_at")
        if expires is None:
            return False
        expires_at = expires if isinstance(expires, datetime) else datetime.fromisoformat(str(expires).replace("Z", _UTC_SUFFIX))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > datetime.now(timezone.utc):
            return False
        if run.get("withdrawn_at") or run["current_stage"] != str(ApplicationStage.AI_INTERVIEW):
            return False
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'EXPIRED', screening_input_json = '{{}}', "
            f"updated_at = {_now_sql()} WHERE id = {p} AND status = 'INTERVIEW_READY'",
            (interview_id,),
        )
        if cur.rowcount != 1:
            return False
        _stage_change(
            cur,
            int(run["application_id"]),
            int(run["org_id"]),
            str(ApplicationStage.PENDING_REVIEW),
            "AI interview invitation expired without a candidate start; recruiter follow-up is required.",
        )
        return True


def _validate_interview_start(run: dict, notice_version: str, modality: str) -> bool:
    if run["current_stage"] != str(ApplicationStage.AI_INTERVIEW):
        raise InterviewConflictError("Application is not currently in the AI interview stage")
    expiry_value = run.get("invitation_expires_at")
    if expiry_value is not None:
        expiry = expiry_value if isinstance(expiry_value, datetime) else datetime.fromisoformat(str(expiry_value).replace("Z", _UTC_SUFFIX))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise InterviewConflictError("This AI interview invitation has expired. Contact the hiring team to request a new invitation.")
    if run["status"] == "INTERVIEW_IN_PROGRESS" and run.get("consent_version") == notice_version:
        if run.get("modality", "TEXT") != modality:
            raise InterviewConflictError("Interview modality cannot be changed after it starts")
        return False
    if run["status"] != "INTERVIEW_READY":
        raise InterviewConflictError(f"Interview cannot start from {run['status']}")
    return True


def reinvite_expired_interview(
    application_id: int,
    org_id: int,
    recruiter_user_id: int,
    reason: str,
) -> dict:
    """Re-open an expired invitation with new timer jobs and an audit timeline event."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.*, a.current_stage, a.withdrawn_at, jp.title AS role "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id WHERE ai.application_id = {p} AND ai.org_id = {p} "
            f"ORDER BY ai.attempt_no DESC LIMIT 1{lock}",
            (application_id, org_id),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None or run.get("withdrawn_at"):
            raise InterviewNotFoundError(_AI_INTERVIEW_NOT_FOUND)
        if run["status"] != "EXPIRED" or run["current_stage"] != str(ApplicationStage.PENDING_REVIEW):
            raise InterviewConflictError("Only an expired AI interview awaiting review can be re-invited.")
        policy = _json(run.get("policy_snapshot_json"), {})
        invitation_round = int(run.get("reinvite_count") or 0) + 1
        window_days = int((policy.get("interview_settings") or {}).get("invitation_window_days", 7))
        deadline = _queue_invitation_lifecycle_jobs(
            cur,
            application_id=application_id,
            interview_id=int(run["id"]),
            org_id=org_id,
            candidate_user_id=int(run["candidate_user_id"]),
            role=str(run.get("role") or _DEFAULT_ROLE_LABEL),
            window_days=window_days,
            invitation_round=invitation_round,
        )
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'INTERVIEW_READY', phase = 'TECHNICAL', "
            f"invitation_expires_at = {p}, invite_reminders_sent = 0, reinvite_count = {p}, "
            f"consent_version = NULL, consent_at = NULL, updated_at = {_now_sql()} "
            f"WHERE id = {p} AND status = 'EXPIRED'",
            (deadline.isoformat(), invitation_round, run["id"]),
        )
        if cur.rowcount != 1:
            raise InterviewConflictError("This AI interview changed while it was being re-invited.")
        _stage_change(
            cur,
            application_id,
            org_id,
            str(ApplicationStage.AI_INTERVIEW),
            f"Recruiter re-invited the candidate to the AI interview: {reason.strip()}",
            actor_user_id=recruiter_user_id,
        )
        _enqueue_job(
            cur,
            "application_interview_ready_notification",
            {"application_id": application_id, "interview_id": int(run["id"]), "candidate_user_id": int(run["candidate_user_id"]), "org_id": org_id, "role": run.get("role", _DEFAULT_ROLE_LABEL), "invitation_round": invitation_round},
            f"application-ai-ready-notification:{application_id}:{run['id']}:reinvite:{invitation_round}",
            f"org:{org_id}",
        )
        return {"application_id": application_id, "status": "INTERVIEW_READY", "invitation_expires_at": deadline.isoformat(), "invitation_round": invitation_round}


def cancel_for_withdrawal(cur, application_id: int) -> None:
    p = _ph()
    cur.execute(
        f"SELECT id FROM application_ai_interviews WHERE application_id = {p} "
        f"AND status NOT IN ('REPORT_READY', 'COMPLETED', 'CANCELLED')",
        (application_id,),
    )
    interview_ids = [int(row["id"]) for row in cur.fetchall()]
    cur.execute(
        f"UPDATE application_ai_interviews SET status = 'CANCELLED', screening_input_json = '{{}}', "
        f"updated_at = {_now_sql()} "
        f"WHERE application_id = {p} AND status NOT IN ('REPORT_READY', 'COMPLETED', 'CANCELLED')",
        (application_id,),
    )
    prefixes = [f"application-screening:{application_id}", f"application-ai-answer:{application_id}:"]
    for interview_id in interview_ids:
        prefixes.extend((
            f"application-ai-ready-notification:{application_id}:{interview_id}",
            f"application-ai-report-ready-notification:{application_id}:{interview_id}",
            f"application-ai-report:{application_id}:{interview_id}",
            f"application-ai-invitation-reminder:{application_id}:{interview_id}:",
            f"application-ai-invitation-expiry:{application_id}:{interview_id}:",
        ))
    for prefix in prefixes:
        cur.execute(
            f"UPDATE background_jobs SET status = CASE WHEN status = 'PENDING' THEN 'CANCELLED' ELSE status END, "
            f"cancellation_requested = {'TRUE' if USE_POSTGRES else '1'}, updated_at = {_now_sql()} "
            f"WHERE status IN ('PENDING', 'RUNNING') AND substr(idempotency_key, 1, {p}) = {p}",
            (len(prefix), prefix),
        )


def cancel_for_account_deletion(cur, application_id: int) -> None:
    """Cancel all application AI jobs before deleting the candidate's records.

    Unlike withdrawal, account deletion also cancels post-completion delivery
    jobs so a late notification cannot recreate inbox data for a deleted user.
    """
    p = _ph()
    cur.execute(
        f"SELECT id FROM application_ai_interviews WHERE application_id = {p}",
        (application_id,),
    )
    interview_ids = [int(row["id"]) for row in cur.fetchall()]
    prefixes = [f"application-screening:{application_id}", f"application-ai-answer:{application_id}:"]
    for interview_id in interview_ids:
        prefixes.extend((
            f"application-ai-ready-notification:{application_id}:{interview_id}",
            f"application-ai-report-ready-notification:{application_id}:{interview_id}",
            f"application-ai-report:{application_id}:{interview_id}",
            f"application-ai-invitation-reminder:{application_id}:{interview_id}:",
            f"application-ai-invitation-expiry:{application_id}:{interview_id}:",
        ))
    for prefix in prefixes:
        cur.execute(
            f"UPDATE background_jobs SET status = CASE WHEN status = 'PENDING' THEN 'CANCELLED' ELSE status END, "
            f"cancellation_requested = {'TRUE' if USE_POSTGRES else '1'}, updated_at = {_now_sql()} "
            f"WHERE status IN ('PENDING', 'RUNNING') AND substr(idempotency_key, 1, {p}) = {p}",
            (len(prefix), prefix),
        )
