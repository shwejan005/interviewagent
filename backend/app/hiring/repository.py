"""
Hiring domain: campaigns, job postings, applications.

The application state machine lives here rather than in the route layer, so
that a transition is validated in exactly one place regardless of whether it
was triggered by a recruiter action, an automated stage, or a candidate
withdrawal.

Every function that reads a tenant-scoped row takes org_id and filters on it
in SQL. That is belt-and-braces alongside `authz.assert_tenant` — the route
layer check can be forgotten, whereas a query that cannot express a
cross-tenant read is structurally safer.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Optional

from app.config.database import _get_conn, _ph, _row_to_dict, USE_POSTGRES, _IntegrityError

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: bool):
    return value if USE_POSTGRES else int(bool(value))


class PostingStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"


class ApplicationStage(StrEnum):
    APPLIED = "APPLIED"
    SCREENING = "SCREENING"
    AI_INTERVIEW = "AI_INTERVIEW"
    # Terminal-adjacent: an automated stage produced an adverse recommendation
    # and is waiting on a human. See DECISIONS.md D-10.
    PENDING_REVIEW = "PENDING_REVIEW"
    TECHNICAL = "TECHNICAL"
    BEHAVIORAL = "BEHAVIORAL"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    HIRED = "HIRED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


TERMINAL_STAGES = frozenset({
    ApplicationStage.HIRED,
    ApplicationStage.REJECTED,
    ApplicationStage.WITHDRAWN,
})

# Allowed transitions. Encoded explicitly rather than "anything goes" so that
# an out-of-order or replayed request is rejected instead of corrupting the
# pipeline history.
_ALLOWED_TRANSITIONS: dict[ApplicationStage, frozenset[ApplicationStage]] = {
    ApplicationStage.APPLIED: frozenset({
        ApplicationStage.SCREENING, ApplicationStage.AI_INTERVIEW, ApplicationStage.PENDING_REVIEW,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.SCREENING: frozenset({
        ApplicationStage.TECHNICAL, ApplicationStage.AI_INTERVIEW, ApplicationStage.PENDING_REVIEW,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.PENDING_REVIEW: frozenset({
        # A human can override an adverse automated recommendation in either
        # direction — that is the entire point of the stage existing.
        ApplicationStage.SCREENING, ApplicationStage.AI_INTERVIEW, ApplicationStage.TECHNICAL,
        ApplicationStage.BEHAVIORAL, ApplicationStage.INTERVIEW,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.AI_INTERVIEW: frozenset({
        ApplicationStage.PENDING_REVIEW, ApplicationStage.INTERVIEW,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.TECHNICAL: frozenset({
        ApplicationStage.BEHAVIORAL, ApplicationStage.INTERVIEW,
        ApplicationStage.PENDING_REVIEW, ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.BEHAVIORAL: frozenset({
        ApplicationStage.INTERVIEW, ApplicationStage.OFFER,
        ApplicationStage.PENDING_REVIEW, ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.INTERVIEW: frozenset({
        ApplicationStage.OFFER, ApplicationStage.PENDING_REVIEW,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.OFFER: frozenset({
        ApplicationStage.HIRED, ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.HIRED: frozenset(),
    ApplicationStage.REJECTED: frozenset(),
    ApplicationStage.WITHDRAWN: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a stage change is not permitted from the current stage."""


class DuplicateApplicationError(Exception):
    """Raised when a candidate applies twice to the same posting."""


class DuplicateInterviewError(Exception):
    """Raised when an application already has an active scheduled interview."""


def can_transition(from_stage: str, to_stage: str) -> bool:
    try:
        source = ApplicationStage(from_stage)
        target = ApplicationStage(to_stage)
    except ValueError:
        return False
    return target in _ALLOWED_TRANSITIONS.get(source, frozenset())


# ── Campaigns ────────────────────────────────────────────────────────


def create_campaign(org_id: int, name: str, description: str = "",
                    created_by: Optional[int] = None, department: str = "",
                    hiring_manager: str = "", priority: str = "MEDIUM",
                    target_hires: Optional[int] = None,
                    target_close_date: Optional[str] = None) -> int:
    payload = {
        "org_id": org_id,
        "name": name,
        "description": description,
        "created_by": created_by,
        "department": department,
        "hiring_manager": hiring_manager,
        "priority": priority,
        "target_hires": target_hires,
        "target_close_date": target_close_date,
    }
    p = _ph()
    placeholders = ", ".join([p] * len(payload))
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO campaigns ({', '.join(payload)}) "
                f"VALUES ({placeholders}) RETURNING id",
                tuple(payload.values()),
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO campaigns ({', '.join(payload)}) VALUES ({placeholders})",
            tuple(payload.values()),
        )
        return cur.lastrowid


def assign_campaign_member(campaign_id: int, user_id: int, member_role: str = "RECRUITER") -> None:
    """Assign a user to a campaign; repeated assignment is idempotent."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO campaign_members (campaign_id, user_id, member_role) "
                f"VALUES ({p}, {p}, {p}) ON CONFLICT (campaign_id, user_id) DO NOTHING",
                (campaign_id, user_id, member_role),
            )
        else:
            cur.execute(
                f"INSERT OR IGNORE INTO campaign_members (campaign_id, user_id, member_role) "
                f"VALUES ({p}, {p}, {p})",
                (campaign_id, user_id, member_role),
            )


def is_campaign_member(campaign_id: int, user_id: int, org_id: int) -> bool:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT 1 FROM campaign_members cm JOIN campaigns c ON c.id = cm.campaign_id "
            f"WHERE cm.campaign_id = {p} AND cm.user_id = {p} AND c.org_id = {p}",
            (campaign_id, user_id, org_id),
        )
        return cur.fetchone() is not None


def is_user_assigned_to_application(application_id: int, org_id: int, user_id: int) -> bool:
    """Return whether a user is an active participant in an application interview."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT 1 FROM interview_participants ip "
            f"JOIN interviews i ON i.id = ip.interview_id "
            f"WHERE i.application_id = {p} AND i.org_id = {p} AND ip.user_id = {p} "
            f"AND i.status = 'SCHEDULED'",
            (application_id, org_id, user_id),
        )
        return cur.fetchone() is not None


def get_campaign(campaign_id: int, org_id: int) -> Optional[dict]:
    """Always org-scoped — a campaign cannot be read across tenants."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM campaigns WHERE id = {p} AND org_id = {p} AND deleted_at IS NULL",
            (campaign_id, org_id),
        )
        return _row_to_dict(cur.fetchone())


def list_campaigns(
    org_id: int,
    limit: int = 50,
    offset: int = 0,
    assigned_user_id: Optional[int] = None,
) -> list[dict]:
    """Campaign overview, with per-campaign role/applicant counts so the
    recruiter dashboard can render its stats without an N+1 fetch per card."""
    p = _ph()
    with _get_conn() as (conn, cur):
        assignment_join = ""
        assignment_where = ""
        params = []
        if assigned_user_id is not None:
            assignment_join = f" JOIN campaign_members cm ON cm.campaign_id = c.id AND cm.user_id = {p}"
            assignment_where = " AND cm.id IS NOT NULL"
            params.append(assigned_user_id)
        params.append(org_id)
        cur.execute(
            f"SELECT c.*, "
            f"(SELECT COUNT(*) FROM job_postings jp WHERE jp.campaign_id = c.id "
            f"AND jp.deleted_at IS NULL) AS posting_count, "
            f"(SELECT COUNT(*) FROM applications a JOIN job_postings jp2 "
            f"ON jp2.id = a.posting_id WHERE jp2.campaign_id = c.id) AS applicant_count "
            f"FROM campaigns c{assignment_join} WHERE c.org_id = {p} AND c.deleted_at IS NULL {assignment_where} "
            f"ORDER BY c.created_at DESC LIMIT {p} OFFSET {p}",
            (*params, limit, offset),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def update_campaign(campaign_id: int, org_id: int, **fields) -> bool:
    allowed = {
        "name", "description", "status", "department", "hiring_manager",
        "priority", "target_hires", "target_close_date",
    }
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not data:
        return False
    data["updated_at"] = _now()
    p = _ph()
    clause = ", ".join(f"{k} = {p}" for k in data)
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE campaigns SET {clause} WHERE id = {p} AND org_id = {p}",
            (*data.values(), campaign_id, org_id),
        )
        return cur.rowcount > 0


# ── Job postings ─────────────────────────────────────────────────────

_POSTING_JSON_FIELDS = ("required_skills", "screening_questions")


def _decode_posting(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None
    for field in _POSTING_JSON_FIELDS:
        if isinstance(row.get(field), str):
            row[field] = json.loads(row[field])
    row["auto_reject_enabled"] = bool(row.get("auto_reject_enabled"))
    return row


def create_posting(org_id: int, campaign_id: int, title: str, created_by: Optional[int] = None,
                   **fields) -> int:
    payload = {
        "org_id": org_id,
        "campaign_id": campaign_id,
        "title": title,
        "description": fields.get("description", ""),
        "location": fields.get("location", ""),
        "employment_type": fields.get("employment_type", "FULL_TIME"),
        "remote_policy": fields.get("remote_policy", "ONSITE"),
        "min_experience": fields.get("min_experience"),
        "max_experience": fields.get("max_experience"),
        "salary_min": fields.get("salary_min"),
        "salary_max": fields.get("salary_max"),
        "currency": fields.get("currency", "INR"),
        "required_skills": json.dumps(fields.get("required_skills", [])),
        "screening_questions": json.dumps(fields.get("screening_questions", [])),
        "auto_reject_enabled": _bool(fields.get("auto_reject_enabled", False)),
        "created_by": created_by,
    }
    p = _ph()
    placeholders = ", ".join([p] * len(payload))
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO job_postings ({', '.join(payload)}) "
                f"VALUES ({placeholders}) RETURNING id",
                tuple(payload.values()),
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO job_postings ({', '.join(payload)}) VALUES ({placeholders})",
            tuple(payload.values()),
        )
        return cur.lastrowid


def get_posting(posting_id: int, org_id: Optional[int] = None) -> Optional[dict]:
    """Fetch a posting.

    org_id is optional because candidates legitimately read *published*
    postings across organizations — that is the job board. Callers passing
    None must not expose draft or closed postings; use
    :func:`get_published_posting` for candidate-facing reads.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        if org_id is None:
            cur.execute(
                f"SELECT * FROM job_postings WHERE id = {p} AND deleted_at IS NULL",
                (posting_id,),
            )
        else:
            cur.execute(
                f"SELECT * FROM job_postings WHERE id = {p} AND org_id = {p} "
                f"AND deleted_at IS NULL",
                (posting_id, org_id),
            )
        return _decode_posting(_row_to_dict(cur.fetchone()))


def get_published_posting(posting_id: int) -> Optional[dict]:
    """Candidate-facing read: published postings only, any organization."""
    posting = get_posting(posting_id)
    if posting is None or posting["status"] != PostingStatus.PUBLISHED:
        return None
    return posting


def list_postings(org_id: int, campaign_id: Optional[int] = None,
                  status: Optional[str] = None, limit: int = 50, offset: int = 0,
                  assigned_user_id: Optional[int] = None) -> list[dict]:
    """Recruiter-facing listing, always org-scoped, with an applicant count
    per posting so a campaign drill-down can render role cards at a glance."""
    p = _ph()
    clauses = [f"jp.org_id = {p}", "jp.deleted_at IS NULL"]
    params: list = []
    assignment_join = ""
    if assigned_user_id is not None:
        assignment_join = f" JOIN campaign_members cm ON cm.campaign_id = jp.campaign_id AND cm.user_id = {p}"
        params.append(assigned_user_id)
    params.append(org_id)
    if campaign_id is not None:
        clauses.append(f"jp.campaign_id = {p}")
        params.append(campaign_id)
    if status is not None:
        clauses.append(f"jp.status = {p}")
        params.append(status)
    params.extend([limit, offset])
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT jp.*, "
            f"(SELECT COUNT(*) FROM applications a WHERE a.posting_id = jp.id) AS applicant_count "
            f"FROM job_postings jp{assignment_join} WHERE {' AND '.join(clauses)} "
            f"ORDER BY jp.created_at DESC LIMIT {p} OFFSET {p}",
            tuple(params),
        )
        return [_decode_posting(_row_to_dict(r)) for r in cur.fetchall()]


def search_published_postings(query: Optional[str] = None, location: Optional[str] = None,
                              remote_policy: Optional[str] = None,
                              limit: int = 50, offset: int = 0) -> dict:
    """Public job board: published postings across all organizations."""
    p = _ph()
    clauses = [f"p.status = {p}", "p.deleted_at IS NULL"]
    params: list = [str(PostingStatus.PUBLISHED)]

    if query:
        clauses.append(f"(LOWER(p.title) LIKE {p} OR LOWER(p.description) LIKE {p})")
        like = f"%{query.casefold()}%"
        params.extend([like, like])
    if location:
        clauses.append(f"LOWER(p.location) LIKE {p}")
        params.append(f"%{location.casefold()}%")
    if remote_policy:
        clauses.append(f"p.remote_policy = {p}")
        params.append(remote_policy)

    where = " AND ".join(clauses)
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT COUNT(*) AS c FROM job_postings p WHERE {where}", tuple(params))
        total = cur.fetchone()["c"]
        cur.execute(
            f"SELECT p.*, o.name AS org_name, o.slug AS org_slug "
            f"FROM job_postings p JOIN organizations o ON o.id = p.org_id "
            f"WHERE {where} ORDER BY p.published_at DESC, p.id DESC LIMIT {p} OFFSET {p}",
            (*params, limit, offset),
        )
        postings = [_decode_posting(_row_to_dict(r)) for r in cur.fetchall()]
    return {"postings": postings, "total": total, "limit": limit, "offset": offset}


def update_posting(posting_id: int, org_id: int, **fields) -> bool:
    allowed = {
        "title", "description", "location", "employment_type", "remote_policy",
        "min_experience", "max_experience", "salary_min", "salary_max",
        "currency", "auto_reject_enabled",
    }
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    for json_field in _POSTING_JSON_FIELDS:
        if fields.get(json_field) is not None:
            data[json_field] = json.dumps(fields[json_field])
    if "auto_reject_enabled" in data:
        data["auto_reject_enabled"] = _bool(data["auto_reject_enabled"])
    if not data:
        return False
    data["updated_at"] = _now()

    p = _ph()
    clause = ", ".join(f"{k} = {p}" for k in data)
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE job_postings SET {clause} WHERE id = {p} AND org_id = {p} "
            f"AND deleted_at IS NULL",
            (*data.values(), posting_id, org_id),
        )
        return cur.rowcount > 0


def set_posting_status(posting_id: int, org_id: int, status: str) -> bool:
    p = _ph()
    now = _now()
    extra, params = "", []
    if status == PostingStatus.PUBLISHED:
        extra = f", published_at = {p}"
        params.append(now)
    elif status == PostingStatus.CLOSED:
        extra = f", closed_at = {p}"
        params.append(now)

    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE job_postings SET status = {p}, updated_at = {p}{extra} "
            f"WHERE id = {p} AND org_id = {p} AND deleted_at IS NULL",
            (status, now, *params, posting_id, org_id),
        )
        return cur.rowcount > 0


# ── Applications ─────────────────────────────────────────────────────


def create_application(org_id: int, posting_id: int, candidate_user_id: int,
                       profile_id: Optional[int], snapshot: dict,
                       answers: Optional[list[dict]] = None,
                       source: str = "DIRECT",
                       ai_interview_policy: Optional[dict] = None,
                       ai_interview_screening_input: Optional[dict] = None) -> int:
    """Submit an application.

    Raises DuplicateApplicationError if the candidate already has a live
    application to this posting (enforced by a partial unique index, so two
    concurrent submissions cannot both succeed).
    """
    p = _ph()
    try:
        with _get_conn() as (conn, cur):
            columns = [
                "org_id", "posting_id", "candidate_user_id", "profile_id",
                "profile_snapshot", "source",
            ]
            values = (
                org_id, posting_id, candidate_user_id, profile_id,
                json.dumps(snapshot), source,
            )
            placeholders = ", ".join([p] * len(columns))
            if USE_POSTGRES:
                cur.execute(
                    f"INSERT INTO applications ({', '.join(columns)}) "
                    f"VALUES ({placeholders}) RETURNING id",
                    values,
                )
                application_id = cur.fetchone()["id"]
            else:
                cur.execute(
                    f"INSERT INTO applications ({', '.join(columns)}) VALUES ({placeholders})",
                    values,
                )
                application_id = cur.lastrowid

            for answer in answers or []:
                cur.execute(
                    f"INSERT INTO application_answers "
                    f"(application_id, question_key, question_text, answer_text) "
                    f"VALUES ({p}, {p}, {p}, {p})",
                    (
                        application_id,
                        answer.get("question_key", ""),
                        answer.get("question_text", ""),
                        answer.get("answer_text", ""),
                    ),
                )

            cur.execute(
                f"INSERT INTO application_events "
                f"(application_id, org_id, event_type, to_stage, actor_user_id) "
                f"VALUES ({p}, {p}, {p}, {p}, {p})",
                (application_id, org_id, "submitted",
                 str(ApplicationStage.APPLIED), candidate_user_id),
            )
            if ai_interview_policy is not None and ai_interview_screening_input is not None:
                # Local import avoids a hiring<->interview package import cycle.
                from app.ai_interview.repository import insert_application_workflow_in_transaction

                insert_application_workflow_in_transaction(
                    cur,
                    application_id=application_id,
                    org_id=org_id,
                    candidate_user_id=candidate_user_id,
                    policy_snapshot=ai_interview_policy,
                    screening_input=ai_interview_screening_input,
                )
        return application_id
    except _IntegrityError as exc:
        with _get_conn() as (conn, cur):
            cur.execute(
                f"SELECT id FROM applications WHERE posting_id = {_ph()} AND candidate_user_id = {_ph()} "
                f"AND withdrawn_at IS NULL ORDER BY id DESC LIMIT 1",
                (posting_id, candidate_user_id),
            )
            existing = cur.fetchone()
        if existing is not None:
            raise DuplicateApplicationError("You have already applied to this posting.") from exc
        raise


def get_application(application_id: int, org_id: Optional[int] = None) -> Optional[dict]:
    """Full application detail, joined to the candidate's name/email.

    The recruiter detail drawer needs both — without this join the caller
    silently gets an application row with no way to identify who it belongs
    to, which reads as a stuck loading state rather than the missing data it
    actually is.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        select = (
            "SELECT a.*, u.full_name AS candidate_name, u.email AS candidate_email, "
            "ai.status AS ai_interview_status, ai.phase AS ai_interview_phase "
            "FROM applications a JOIN users u ON u.id = a.candidate_user_id "
            "LEFT JOIN application_ai_interviews ai ON ai.application_id = a.id "
            "AND ai.status NOT IN ('CANCELLED', 'EXPIRED') "
        )
        if org_id is None:
            cur.execute(f"{select}WHERE a.id = {p}", (application_id,))
        else:
            cur.execute(
                f"{select}WHERE a.id = {p} AND a.org_id = {p}",
                (application_id, org_id),
            )
        row = _row_to_dict(cur.fetchone())
    if row and isinstance(row.get("profile_snapshot"), str):
        row["profile_snapshot"] = json.loads(row["profile_snapshot"])
    return row


def get_application_by_evaluation_id(evaluation_id: int) -> Optional[dict]:
    """Reverse lookup used by finalization to find the application (if any)
    an evaluation belongs to, so posting-scoped report generation stays a
    no-op for evaluations created outside the recruiter pipeline."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id, org_id, posting_id FROM applications WHERE evaluation_id = {p}",
            (evaluation_id,),
        )
        return _row_to_dict(cur.fetchone())


def attach_evaluation(application_id: int, org_id: int, evaluation_id: int) -> bool:
    """Attach one evaluation to an application within the same tenant."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE applications SET evaluation_id = {p}, updated_at = {p} "
            f"WHERE id = {p} AND org_id = {p} AND evaluation_id IS NULL",
            (evaluation_id, _now(), application_id, org_id),
        )
        return cur.rowcount == 1


def list_applications_for_posting(posting_id: int, org_id: int, stage: Optional[str] = None,
                                  limit: int = 50, offset: int = 0) -> list[dict]:
    """Recruiter pipeline view, org-scoped in SQL."""
    p = _ph()
    clauses = [f"a.posting_id = {p}", f"a.org_id = {p}"]
    params: list = [posting_id, org_id]
    if stage:
        clauses.append(f"a.current_stage = {p}")
        params.append(stage)
    params.extend([limit, offset])

    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT a.*, u.full_name AS candidate_name, u.email AS candidate_email, "
            f"ai.status AS ai_interview_status, ai.phase AS ai_interview_phase "
            f"FROM applications a JOIN users u ON u.id = a.candidate_user_id "
            f"LEFT JOIN application_ai_interviews ai ON ai.application_id = a.id "
            f"AND ai.status NOT IN ('CANCELLED', 'EXPIRED') "
            f"WHERE {' AND '.join(clauses)} ORDER BY a.created_at DESC LIMIT {p} OFFSET {p}",
            tuple(params),
        )
        rows = [_row_to_dict(r) for r in cur.fetchall()]
    for row in rows:
        if isinstance(row.get("profile_snapshot"), str):
            row["profile_snapshot"] = json.loads(row["profile_snapshot"])
    return rows


def list_applications_for_candidate(candidate_user_id: int, limit: int = 50,
                                    offset: int = 0) -> list[dict]:
    """Candidate's own application tracker, joined to posting and org names."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT a.id, a.status, a.current_stage, a.created_at, a.updated_at, "
            f"a.withdrawn_at, p.id AS posting_id, p.title AS posting_title, "
            f"p.location, p.remote_policy, o.name AS org_name, "
            f"ai.status AS ai_interview_status, ai.phase AS ai_interview_phase "
            f"FROM applications a "
            f"JOIN job_postings p ON p.id = a.posting_id "
            f"JOIN organizations o ON o.id = a.org_id "
            f"LEFT JOIN application_ai_interviews ai ON ai.application_id = a.id "
            f"AND ai.status NOT IN ('CANCELLED', 'EXPIRED') "
            f"WHERE a.candidate_user_id = {p} "
            f"ORDER BY a.created_at DESC LIMIT {p} OFFSET {p}",
            (candidate_user_id, limit, offset),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def transition_application(application_id: int, org_id: int, to_stage: str,
                           actor_user_id: Optional[int], note: str = "",
                           is_automated: bool = False) -> dict:
    """Move an application to a new stage, validating the transition.

    Reads the current stage and writes the new one inside a single connection
    so a concurrent transition cannot interleave between check and write.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")
        select_suffix = " FOR UPDATE" if USE_POSTGRES else ""
        cur.execute(
            f"SELECT current_stage FROM applications WHERE id = {p} AND org_id = {p}{select_suffix}",
            (application_id, org_id),
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError("Application not found.")

        from_stage = row["current_stage"]
        if not can_transition(from_stage, to_stage):
            raise InvalidTransitionError(
                f"Cannot move an application from {from_stage} to {to_stage}."
            )

        status = to_stage if to_stage in TERMINAL_STAGES else "IN_PROGRESS"
        cur.execute(
            f"UPDATE applications SET current_stage = {p}, status = {p}, updated_at = {p} "
            f"WHERE id = {p} AND org_id = {p}",
            (to_stage, status, _now(), application_id, org_id),
        )
        cur.execute(
            f"INSERT INTO application_events "
            f"(application_id, org_id, event_type, from_stage, to_stage, "
            f"actor_user_id, is_automated, note) "
            f"VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})",
            (application_id, org_id, "stage_changed", from_stage, to_stage,
             actor_user_id, _bool(is_automated), note),
        )

    return {"application_id": application_id, "from_stage": from_stage, "to_stage": to_stage}


def withdraw_application(application_id: int, candidate_user_id: int) -> bool:
    """Candidate-initiated withdrawal, scoped to their own application."""
    p = _ph()
    now = _now()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT org_id, current_stage FROM applications "
            f"WHERE id = {p} AND candidate_user_id = {p} AND withdrawn_at IS NULL",
            (application_id, candidate_user_id),
        )
        row = cur.fetchone()
        if row is None:
            return False

        cur.execute(
            f"UPDATE applications SET current_stage = {p}, status = {p}, "
            f"withdrawn_at = {p}, updated_at = {p} WHERE id = {p}",
            (str(ApplicationStage.WITHDRAWN), str(ApplicationStage.WITHDRAWN),
             now, now, application_id),
        )
        cur.execute(
            f"INSERT INTO application_events "
            f"(application_id, org_id, event_type, from_stage, to_stage, actor_user_id) "
            f"VALUES ({p}, {p}, {p}, {p}, {p}, {p})",
            (application_id, row["org_id"], "withdrawn", row["current_stage"],
             str(ApplicationStage.WITHDRAWN), candidate_user_id),
        )
        from app.ai_interview.repository import cancel_for_withdrawal

        cancel_for_withdrawal(cur, application_id)
        return True


# ── Interview scheduling ────────────────────────────────────────────

def create_interview(
    org_id: int,
    application_id: int,
    title: str,
    scheduled_start: str,
    scheduled_end: str,
    timezone_name: str,
    meeting_url: str,
    created_by: int,
    interviewer_user_ids: list[int],
) -> dict:
    """Schedule one interview and persist its candidate/interviewer participants."""
    start = _parse_ts(scheduled_start)
    end = _parse_ts(scheduled_end)
    if start is None or end is None or end <= start:
        raise ValueError("scheduled_end must be later than scheduled_start")

    p = _ph()
    participant_ids = list(dict.fromkeys(interviewer_user_ids))
    with _get_conn() as (conn, cur):
        if not USE_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")
        cur.execute(
            f"SELECT candidate_user_id, current_stage FROM applications "
            f"WHERE id = {p} AND org_id = {p}",
            (application_id, org_id),
        )
        application = _row_to_dict(cur.fetchone())
        if application is None:
            raise LookupError("Application not found.")

        cur.execute(
            f"SELECT id FROM interviews WHERE application_id = {p} AND org_id = {p} "
            f"AND status = 'SCHEDULED'",
            (application_id, org_id),
        )
        if cur.fetchone() is not None:
            raise DuplicateInterviewError("This application already has a scheduled interview.")

        for user_id in participant_ids:
            cur.execute(
                f"SELECT id FROM org_memberships WHERE org_id = {p} AND user_id = {p} "
                f"AND status = 'ACTIVE' AND deleted_at IS NULL",
                (org_id, user_id),
            )
            if cur.fetchone() is None:
                raise LookupError("Every interviewer must be an active organization member.")

        columns = (
            "org_id", "application_id", "title", "scheduled_start", "scheduled_end",
            "timezone", "meeting_url", "created_by",
        )
        values = (
            org_id, application_id, title, start.isoformat(), end.isoformat(),
            timezone_name, meeting_url, created_by,
        )
        placeholders = ", ".join([p] * len(columns))
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO interviews ({', '.join(columns)}) VALUES ({placeholders}) "
                f"RETURNING id",
                values,
            )
            interview_id = cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO interviews ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            interview_id = cur.lastrowid

        participants = [(application["candidate_user_id"], "CANDIDATE")]
        participants.extend((user_id, "INTERVIEWER") for user_id in participant_ids)
        for user_id, participant_role in participants:
            cur.execute(
                f"INSERT INTO interview_participants (interview_id, user_id, participant_role) "
                f"VALUES ({p}, {p}, {p})",
                (interview_id, user_id, participant_role),
            )

    return get_interview(interview_id, org_id)


def get_interview(interview_id: int, org_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT i.*, a.candidate_user_id, a.posting_id "
            f"FROM interviews i JOIN applications a ON a.id = i.application_id "
            f"WHERE i.id = {p} AND i.org_id = {p}",
            (interview_id, org_id),
        )
        interview = _row_to_dict(cur.fetchone())
        if interview is None:
            return None
        cur.execute(
            f"SELECT ip.user_id, ip.participant_role, u.full_name, u.email "
            f"FROM interview_participants ip JOIN users u ON u.id = ip.user_id "
            f"WHERE ip.interview_id = {p} ORDER BY ip.id",
            (interview_id,),
        )
        interview["participants"] = [_row_to_dict(row) for row in cur.fetchall()]
        return interview


def list_interviews_for_application(application_id: int, org_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id FROM interviews WHERE application_id = {p} AND org_id = {p} "
            f"ORDER BY scheduled_start DESC",
            (application_id, org_id),
        )
        ids = [row["id"] for row in cur.fetchall()]
    return [get_interview(interview_id, org_id) for interview_id in ids]


def list_interviews_for_user(user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT DISTINCT i.id, i.org_id, i.application_id, i.title, "
            f"i.scheduled_start, i.scheduled_end, i.timezone, i.meeting_url, i.status, "
            f"jp.title AS posting_title, o.name AS org_name "
            f"FROM interviews i JOIN interview_participants ip ON ip.interview_id = i.id "
            f"JOIN applications a ON a.id = i.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id "
            f"JOIN organizations o ON o.id = i.org_id "
            f"WHERE ip.user_id = {p} ORDER BY i.scheduled_start DESC LIMIT {p} OFFSET {p}",
            (user_id, limit, offset),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def cancel_interview(interview_id: int, org_id: int) -> bool:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE interviews SET status = 'CANCELLED', updated_at = {p} "
            f"WHERE id = {p} AND org_id = {p} AND status = 'SCHEDULED'",
            (_now(), interview_id, org_id),
        )
        return cur.rowcount == 1


def list_application_events(application_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM application_events WHERE application_id = {p} ORDER BY id ASC",
            (application_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def get_application_answers(application_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT question_key, question_text, answer_text FROM application_answers "
            f"WHERE application_id = {p} ORDER BY id",
            (application_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def count_applications_for_posting(posting_id: int, org_id: int) -> dict:
    """Per-stage counts for a posting's pipeline funnel."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT current_stage, COUNT(*) AS c FROM applications "
            f"WHERE posting_id = {p} AND org_id = {p} GROUP BY current_stage",
            (posting_id, org_id),
        )
        counts = {r["current_stage"]: r["c"] for r in cur.fetchall()}
    return {"by_stage": counts, "total": sum(counts.values())}


# ── Referrals ────────────────────────────────────────────────────────


class DuplicateReferralError(Exception):
    """Raised when the same candidate already has a pending referral for this posting."""


def create_referral(org_id: int, posting_id: int, referred_by_user_id: int,
                    candidate_email: str, note: str = "") -> int:
    """Refer a candidate to a posting.

    candidate_user_id is resolved from the email if that person is already
    registered; if not, the referral is still recorded (candidate_user_id
    stays NULL) so it can be linked once they sign up. There is no
    not-yet-a-user notification path yet — see docs/PRODUCT_BLUEPRINT.md
    Phase 4 (invitations) for where that belongs.
    """
    from app.config.database import get_user_by_email, normalize_email

    p = _ph()
    normalized = normalize_email(candidate_email)
    user = get_user_by_email(candidate_email)

    try:
        with _get_conn() as (conn, cur):
            columns = ["org_id", "posting_id", "referred_by_user_id",
                      "candidate_user_id", "candidate_email", "note"]
            values = (org_id, posting_id, referred_by_user_id,
                      user["id"] if user else None, normalized, note)
            placeholders = ", ".join([p] * len(columns))
            if USE_POSTGRES:
                cur.execute(
                    f"INSERT INTO referrals ({', '.join(columns)}) "
                    f"VALUES ({placeholders}) RETURNING id",
                    values,
                )
                return cur.fetchone()["id"]
            cur.execute(
                f"INSERT INTO referrals ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            return cur.lastrowid
    except _IntegrityError as exc:
        raise DuplicateReferralError(
            "This candidate already has a pending referral for this posting."
        ) from exc


def get_referral(referral_id: int, org_id: Optional[int] = None) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        if org_id is None:
            cur.execute(f"SELECT * FROM referrals WHERE id = {p}", (referral_id,))
        else:
            cur.execute(
                f"SELECT * FROM referrals WHERE id = {p} AND org_id = {p}",
                (referral_id, org_id),
            )
        return _row_to_dict(cur.fetchone())


def list_referrals_for_org(org_id: int, posting_id: Optional[int] = None,
                           limit: int = 50, offset: int = 0) -> list[dict]:
    p = _ph()
    clauses = [f"org_id = {p}"]
    params: list = [org_id]
    if posting_id is not None:
        clauses.append(f"posting_id = {p}")
        params.append(posting_id)
    params.extend([limit, offset])
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM referrals WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
            tuple(params),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def list_referrals_for_candidate(candidate_email: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """A candidate's referral inbox, matched by email.

    Matched on email rather than candidate_user_id so a referral sent before
    registration still shows up once the person signs in with that address.
    """
    from app.config.database import normalize_email

    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT r.*, jp.title AS posting_title, o.name AS org_name "
            f"FROM referrals r "
            f"JOIN job_postings jp ON jp.id = r.posting_id "
            f"JOIN organizations o ON o.id = r.org_id "
            f"WHERE r.candidate_email = {p} "
            f"ORDER BY r.created_at DESC LIMIT {p} OFFSET {p}",
            (normalize_email(candidate_email), limit, offset),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def respond_to_referral(referral_id: int, status: str,
                        resulting_application_id: Optional[int] = None) -> bool:
    """Mark a referral APPLIED or DECLINED. Only a PENDING referral can be actioned."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE referrals SET status = {p}, responded_at = {p}, "
            f"resulting_application_id = {p} "
            f"WHERE id = {p} AND status = 'PENDING'",
            (status, _now(), resulting_application_id, referral_id),
        )
        return cur.rowcount > 0


# ── Analytics ────────────────────────────────────────────────────────


def get_funnel(org_id: int, campaign_id: Optional[int] = None,
              posting_id: Optional[int] = None) -> dict:
    """Stage counts and stage-to-stage conversion across a scope.

    Conversion is computed against the ever-reached count per stage (i.e.
    "how many applications ever reached SCREENING" vs "how many are
    currently sitting in SCREENING"), using application_events rather than
    current_stage, so an application that has since moved on still counts
    at every stage it passed through.
    """
    p = _ph()
    clauses = [f"a.org_id = {p}"]
    params: list = [org_id]
    if campaign_id is not None:
        clauses.append(f"jp.campaign_id = {p}")
        params.append(campaign_id)
    if posting_id is not None:
        clauses.append(f"a.posting_id = {p}")
        params.append(posting_id)

    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT ae.to_stage, COUNT(DISTINCT ae.application_id) AS c "
            f"FROM application_events ae "
            f"JOIN applications a ON a.id = ae.application_id "
            f"JOIN job_postings jp ON jp.id = a.posting_id "
            f"WHERE {' AND '.join(clauses)} AND ae.to_stage IS NOT NULL "
            f"GROUP BY ae.to_stage",
            tuple(params),
        )
        reached = {r["to_stage"]: r["c"] for r in cur.fetchall()}

    ordered_stages = [
        "APPLIED", "SCREENING", "TECHNICAL", "BEHAVIORAL",
        "INTERVIEW", "OFFER", "HIRED",
    ]
    funnel = []
    applied_count = reached.get("APPLIED", 0)
    previous_count = applied_count
    for stage in ordered_stages:
        count = reached.get(stage, 0)
        conversion_from_previous = round(count / previous_count, 3) if previous_count else None
        conversion_from_start = round(count / applied_count, 3) if applied_count else None
        funnel.append({
            "stage": stage, "reached": count,
            "conversion_from_previous_stage": conversion_from_previous,
            "conversion_from_applied": conversion_from_start,
        })
        if count:
            previous_count = count

    return {
        "funnel": funnel,
        "rejected": reached.get("REJECTED", 0),
        "withdrawn": reached.get("WITHDRAWN", 0),
    }


def get_selection_rates(org_id: int, segment_by: str) -> dict:
    """Selection-rate divergence across a segment, using only data already
    on file (no protected-characteristic collection — see DECISIONS.md D-05).

    This is a general disparate-impact-style calculator, not a legally
    compliant EEO bias audit: it reports the same four-fifths-rule ratio a
    real audit would use (selection rate of the lowest-rate group divided by
    the highest), applied to whichever available, non-protected segment is
    requested. It exists so the *mechanism* is built and tested; pointing it
    at true protected characteristics requires the consent, disclosure, and
    legal review described in DECISIONS.md D-05, which has not happened.
    """
    if segment_by not in ("source", "experience_band"):
        raise ValueError("segment_by must be 'source' or 'experience_band'")

    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT source, status, current_stage, profile_snapshot FROM applications "
            f"WHERE org_id = {p}",
            (org_id,),
        )
        rows = [_row_to_dict(r) for r in cur.fetchall()]

    def _segment_key(row: dict) -> str:
        if segment_by == "source":
            return row["source"]
        snapshot = row["profile_snapshot"]
        years = json.loads(snapshot).get("years_experience") if isinstance(snapshot, str) else None
        if years is None:
            return "unknown"
        if years < 2:
            return "0-2 years"
        if years < 5:
            return "2-5 years"
        if years < 10:
            return "5-10 years"
        return "10+ years"

    def _is_selected(row: dict) -> bool:
        return row["current_stage"] in ("OFFER", "HIRED")

    segments: dict[str, dict] = {}
    for row in rows:
        key = _segment_key(row)
        bucket = segments.setdefault(key, {"total": 0, "selected": 0})
        bucket["total"] += 1
        if _is_selected(row):
            bucket["selected"] += 1

    rates = {
        key: round(v["selected"] / v["total"], 3) if v["total"] else 0.0
        for key, v in segments.items()
    }
    non_zero_rates = list(rates.values())
    adverse_impact_ratio = (
        round(min(non_zero_rates) / max(rates.values()), 3)
        if rates and max(rates.values()) > 0
        else None
    )

    return {
        "segment_by": segment_by,
        "segments": {
            key: {**segments[key], "selection_rate": rates[key]} for key in segments
        },
        # Conventionally, a ratio below 0.8 flags a segment selected at less
        # than 80% the rate of the most-selected segment ("four-fifths rule").
        "adverse_impact_ratio": adverse_impact_ratio,
        "flag_adverse_impact": adverse_impact_ratio is not None and adverse_impact_ratio < 0.8,
        "note": (
            "General disparate-impact calculator over available, non-protected "
            "fields. Not a substitute for a compliant EEO bias audit — see "
            "DECISIONS.md D-05."
        ),
    }


def _parse_ts(value) -> Optional[datetime]:
    """Application/event timestamps round-trip as either datetimes (Postgres
    driver) or ISO strings (SQLite) — normalize once so callers never branch."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def get_analytics_overview(org_id: int, days: int = 30) -> dict:
    """One dashboard-shaped read: volume trend, stage mix, source mix,
    campaign/posting leaderboards, and time-to-hire — all derived from
    applications + application_events already on file, no new tables.

    Aggregation happens in Python rather than SQL date-trunc so the same
    code path works unchanged against both SQLite and Postgres.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT a.id, a.posting_id, a.source, a.status, a.current_stage, "
            f"a.created_at, jp.title AS posting_title, jp.campaign_id, "
            f"jp.status AS posting_status, c.name AS campaign_name "
            f"FROM applications a "
            f"JOIN job_postings jp ON jp.id = a.posting_id "
            f"JOIN campaigns c ON c.id = jp.campaign_id "
            f"WHERE a.org_id = {p}",
            (org_id,),
        )
        applications = [_row_to_dict(r) for r in cur.fetchall()]

        cur.execute(
            f"SELECT ae.application_id, ae.created_at "
            f"FROM application_events ae "
            f"JOIN applications a ON a.id = ae.application_id "
            f"WHERE a.org_id = {p} AND ae.to_stage = 'HIRED' "
            f"ORDER BY ae.created_at ASC",
            (org_id,),
        )
        hired_at_by_application: dict[int, datetime] = {}
        for row in cur.fetchall():
            row = _row_to_dict(row)
            app_id = row["application_id"]
            if app_id not in hired_at_by_application:
                ts = _parse_ts(row["created_at"])
                if ts is not None:
                    hired_at_by_application[app_id] = ts

        cur.execute(
            f"SELECT COUNT(*) AS c FROM job_postings "
            f"WHERE org_id = {p} AND status = 'PUBLISHED' AND deleted_at IS NULL",
            (org_id,),
        )
        open_postings = _row_to_dict(cur.fetchone())["c"]

    today = datetime.now(timezone.utc).date()
    window_start = today - timedelta(days=days - 1)

    apps_by_day: dict = {}
    hires_by_day: dict = {}
    stage_counts: dict[str, int] = {}
    source_counts: dict[str, dict] = {}
    campaign_counts: dict[int, dict] = {}
    posting_counts: dict[int, dict] = {}
    time_to_hire_days: list[float] = []

    for app in applications:
        stage = app["current_stage"]
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

        source = app["source"] or "DIRECT"
        bucket = source_counts.setdefault(source, {"source": source, "applications": 0, "hired": 0})
        bucket["applications"] += 1

        campaign_id = app["campaign_id"]
        cbucket = campaign_counts.setdefault(
            campaign_id,
            {"campaign_id": campaign_id, "name": app["campaign_name"], "applications": 0, "hired": 0, "postings": set()},
        )
        cbucket["applications"] += 1
        cbucket["postings"].add(app["posting_id"])

        posting_id = app["posting_id"]
        pbucket = posting_counts.setdefault(
            posting_id,
            {"posting_id": posting_id, "title": app["posting_title"], "applications": 0, "hired": 0},
        )
        pbucket["applications"] += 1

        applied_ts = _parse_ts(app["created_at"])
        if applied_ts is not None and applied_ts.date() >= window_start:
            day_key = applied_ts.date().isoformat()
            apps_by_day[day_key] = apps_by_day.get(day_key, 0) + 1

        if stage == "HIRED":
            bucket["hired"] += 1
            cbucket["hired"] += 1
            pbucket["hired"] += 1
            hired_ts = hired_at_by_application.get(app["id"])
            if hired_ts is not None:
                if hired_ts.date() >= window_start:
                    day_key = hired_ts.date().isoformat()
                    hires_by_day[day_key] = hires_by_day.get(day_key, 0) + 1
                if applied_ts is not None:
                    time_to_hire_days.append((hired_ts - applied_ts).total_seconds() / 86400)

    trend = []
    for offset in range(days):
        day = window_start + timedelta(days=offset)
        key = day.isoformat()
        trend.append({
            "date": key,
            "applications": apps_by_day.get(key, 0),
            "hires": hires_by_day.get(key, 0),
        })

    campaign_performance = sorted(
        (
            {**v, "postings": len(v["postings"])}
            for v in campaign_counts.values()
        ),
        key=lambda row: row["applications"],
        reverse=True,
    )
    top_postings = sorted(
        posting_counts.values(), key=lambda row: row["applications"], reverse=True,
    )[:8]

    total = len(applications)
    hired_total = stage_counts.get("HIRED", 0)
    rejected_total = stage_counts.get("REJECTED", 0)
    withdrawn_total = stage_counts.get("WITHDRAWN", 0)
    active_total = total - hired_total - rejected_total - withdrawn_total

    return {
        "totals": {
            "applications": total,
            "active": active_total,
            "hired": hired_total,
            "rejected": rejected_total,
            "withdrawn": withdrawn_total,
            "open_postings": open_postings,
            "avg_time_to_hire_days": (
                round(sum(time_to_hire_days) / len(time_to_hire_days), 1)
                if time_to_hire_days else None
            ),
            "conversion_rate": round(hired_total / total, 3) if total else None,
        },
        "trend": trend,
        "stage_distribution": [
            {"stage": stage, "count": stage_counts.get(stage, 0)}
            for stage in (
                "APPLIED", "SCREENING", "PENDING_REVIEW", "TECHNICAL", "BEHAVIORAL",
                "INTERVIEW", "OFFER", "HIRED", "REJECTED", "WITHDRAWN",
            )
            if stage_counts.get(stage, 0) > 0
        ],
        "source_breakdown": sorted(
            source_counts.values(), key=lambda row: row["applications"], reverse=True,
        ),
        "campaign_performance": campaign_performance,
        "top_postings": top_postings,
    }

