"""Persistence for application-owned screening and interview sessions.

Candidate and recruiter API reads deliberately use projections that never
return frozen resume input or internal assessment payloads. Worker-only reads
are explicit and expected to run with the organization RLS context set.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from app.config.database import USE_POSTGRES, _get_conn, _ph, _row_to_dict
from app.hiring.repository import ApplicationStage, can_transition

_SQLITE_BEGIN_IMMEDIATE = "BEGIN IMMEDIATE"
_POSTGRES_FOR_UPDATE = " FOR UPDATE"
_AI_INTERVIEW_NOT_FOUND = "AI interview not found"


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


def _enqueue_job(cur, job_type: str, payload: dict, idempotency_key: str, tenant_key: str) -> int:
    p = _ph()
    encoded = json.dumps(payload, separators=(",", ":"))
    if USE_POSTGRES:
        cur.execute(
            f"""INSERT INTO background_jobs
                (job_type, payload, max_attempts, idempotency_key, tenant_key)
                VALUES ({p}, {p}, 5, {p}, {p})
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING RETURNING id""",
            (job_type, encoded, idempotency_key, tenant_key),
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
                (job_type, payload, max_attempts, idempotency_key, tenant_key)
                VALUES ({p}, {p}, 5, {p}, {p})""",
            (job_type, encoded, idempotency_key, tenant_key),
        )
        return int(cur.lastrowid)
    except Exception as exc:
        # Only resolve the unique-key conflict; all other DB failures propagate.
        cur.execute(f"SELECT id FROM background_jobs WHERE idempotency_key = {p}", (idempotency_key,))
        existing = cur.fetchone()
        if existing is None:
            raise exc
        return int(existing["id"])


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
    return row


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
    return row


def get_candidate_view(application_id: int, candidate_user_id: int) -> Optional[dict]:
    """Return only candidate-safe state and turns, never screening inputs or scores."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id, application_id, status, phase, rubric_version, consent_version, current_question_id, "
            f"policy_snapshot_json, "
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
            f"question_text, answer_text, state FROM application_ai_interview_turns "
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
            f"SELECT ai.evaluation_id, ai.application_id, ai.org_id, ai.candidate_user_id, "
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
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
                f"VALUES ({p}, '', {p}, {p}, {p}) RETURNING id",
                (row["candidate_name"] or "", row["role"], row["org_id"], row["candidate_user_id"]),
            )
            evaluation_id = int(cur.fetchone()["id"])
        else:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
                f"VALUES ({p}, '', {p}, {p}, {p})",
                (row["candidate_name"] or "", row["role"], row["org_id"], row["candidate_user_id"]),
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
        cur.execute(
            f"UPDATE application_ai_interviews SET evaluation_id = {p}, status = 'INTERVIEW_READY', "
            f"phase = 'TECHNICAL', technical_questions_json = {p}, behavioral_questions_json = {p}, "
            f"screening_result_json = {p}, screening_input_json = '{{}}', phase_question_index = 0, "
            f"next_turn_sequence = 2, current_question_id = NULL, "
            f"follow_ups_for_question = 0, updated_at = {_now_sql()} WHERE id = {p}",
            (
                evaluation_id,
                json.dumps(technical, separators=(",", ":")),
                json.dumps(behavioral, separators=(",", ":")),
                json.dumps({**result, "raw_summary": raw_output[:4000]}, separators=(",", ":")),
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
        cur.execute(
            f"UPDATE application_ai_interviews SET evaluation_id = {p}, status = 'INTERVIEW_READY', "
            f"phase = 'TECHNICAL', technical_questions_json = {p}, behavioral_questions_json = {p}, "
            f"screening_input_json = '{{}}', current_question_id = NULL, next_turn_sequence = 2, "
            f"phase_question_index = 0, follow_ups_for_question = 0, error_code = NULL, "
            f"error_message = NULL, updated_at = {_now_sql()} WHERE id = {p}",
            (
                evaluation_id,
                json.dumps(technical, separators=(",", ":")),
                json.dumps(behavioral, separators=(",", ":")),
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


def start_interview(application_id: int, candidate_user_id: int, notice_version: str) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute(_SQLITE_BEGIN_IMMEDIATE)
        lock = _POSTGRES_FOR_UPDATE if USE_POSTGRES else ""
        cur.execute(
            f"SELECT ai.id, ai.status, ai.consent_version, a.withdrawn_at, a.current_stage "
            f"FROM application_ai_interviews ai JOIN applications a ON a.id = ai.application_id "
            f"WHERE ai.application_id = {p} AND ai.candidate_user_id = {p} "
            f"ORDER BY ai.attempt_no DESC LIMIT 1{lock}",
            (application_id, candidate_user_id),
        )
        run = _row_to_dict(cur.fetchone())
        if run is None or run["withdrawn_at"]:
            return None
        if run["current_stage"] != str(ApplicationStage.AI_INTERVIEW):
            raise InterviewConflictError("Application is not currently in the AI interview stage")
        if run["status"] == "INTERVIEW_IN_PROGRESS" and run.get("consent_version") == notice_version:
            return {"status": run["status"], "started": False}
        if run["status"] != "INTERVIEW_READY":
            raise InterviewConflictError(f"Interview cannot start from {run['status']}")
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'INTERVIEW_IN_PROGRESS', "
            f"consent_version = {p}, consent_at = {_now_sql()}, started_at = COALESCE(started_at, {_now_sql()}), "
            f"updated_at = {_now_sql()} WHERE id = {p} AND status = 'INTERVIEW_READY'",
            (notice_version, run["id"]),
        )
        return {"status": "INTERVIEW_IN_PROGRESS", "started": cur.rowcount == 1}


def _enqueue_job(cur, job_type: str, payload: dict, idempotency_key: str, tenant_key: str) -> int:
    p = _ph()
    encoded = json.dumps(payload, separators=(",", ":"))
    if USE_POSTGRES:
        cur.execute(
            f"""INSERT INTO background_jobs
                (job_type, payload, max_attempts, idempotency_key, tenant_key)
                VALUES ({p}, {p}, 5, {p}, {p})
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING RETURNING id""",
            (job_type, encoded, idempotency_key, tenant_key),
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
            f"INSERT INTO background_jobs (job_type, payload, max_attempts, idempotency_key, tenant_key) "
            f"VALUES ({p}, {p}, 5, {p}, {p})",
            (job_type, encoded, idempotency_key, tenant_key),
        )
        return int(cur.lastrowid)
    except Exception as exc:
        cur.execute(f"SELECT id FROM background_jobs WHERE idempotency_key = {p}", (idempotency_key,))
        row = cur.fetchone()
        if row is None:
            raise exc
        return int(row["id"])


def submit_answer(application_id: int, candidate_user_id: int, turn_id: int, answer: str) -> dict:
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
        run = _row_to_dict(cur.fetchone())
        if run is None or run["withdrawn_at"]:
            raise InterviewNotFoundError("Interview not found")
        if run["current_stage"] in (str(ApplicationStage.REJECTED), str(ApplicationStage.HIRED), str(ApplicationStage.WITHDRAWN)):
            raise InterviewConflictError("This application is no longer accepting interview answers")
        cur.execute(
            f"SELECT * FROM application_ai_interview_turns WHERE id = {p} AND interview_id = {p} "
            f"AND application_id = {p} AND candidate_user_id = {p}",
            (turn_id, run["id"], application_id, candidate_user_id),
        )
        turn = _row_to_dict(cur.fetchone())
        if turn is None:
            raise InterviewNotFoundError("Interview turn not found")
        if turn["answer_text"] is not None:
            if turn["answer_text"] != answer:
                raise InterviewConflictError("This question already has a different submitted answer")
            cur.execute(
                f"SELECT id FROM background_jobs WHERE idempotency_key = {p}",
                (f"application-ai-answer:{application_id}:{turn_id}",),
            )
            job = cur.fetchone()
            return {"status": run["status"], "job_id": int(job["id"]) if job else None, "duplicate": True}
        if run["status"] != "INTERVIEW_IN_PROGRESS":
            raise InterviewConflictError(f"Interview is not accepting answers ({run['status']})")
        cur.execute(
            f"SELECT id FROM application_ai_interview_turns WHERE interview_id = {p} "
            f"AND state IN ('ASKED', 'ANSWER_QUEUED') ORDER BY sequence_no DESC LIMIT 1",
            (run["id"],),
        )
        current = cur.fetchone()
        if current is None or int(current["id"]) != turn_id:
            raise InterviewConflictError("Answer the current interview question before continuing")
        cur.execute(
            f"UPDATE application_ai_interview_turns SET answer_text = {p}, state = 'ANSWER_QUEUED', "
            f"answered_at = {_now_sql()} WHERE id = {p} AND answer_text IS NULL",
            (answer, turn_id),
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
    return row


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
            raise InterviewNotFoundError("Interview turn not found")
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
        f"SELECT ai.application_id, ai.org_id, ai.evaluation_id, ai.rubric_version, ai.status, "
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
            f"application-ai-report:{application_id}:{interview_id}",
        ))
    for prefix in prefixes:
        cur.execute(
            f"UPDATE background_jobs SET status = CASE WHEN status = 'PENDING' THEN 'CANCELLED' ELSE status END, "
            f"cancellation_requested = {'TRUE' if USE_POSTGRES else '1'}, updated_at = {_now_sql()} "
            f"WHERE status IN ('PENDING', 'RUNNING') AND substr(idempotency_key, 1, {p}) = {p}",
            (len(prefix), prefix),
        )
