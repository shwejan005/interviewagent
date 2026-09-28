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
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from database import _get_conn, _ph, _row_to_dict, USE_POSTGRES, _IntegrityError

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
        ApplicationStage.SCREENING, ApplicationStage.PENDING_REVIEW,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.SCREENING: frozenset({
        ApplicationStage.TECHNICAL, ApplicationStage.PENDING_REVIEW,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    }),
    ApplicationStage.PENDING_REVIEW: frozenset({
        # A human can override an adverse automated recommendation in either
        # direction — that is the entire point of the stage existing.
        ApplicationStage.SCREENING, ApplicationStage.TECHNICAL,
        ApplicationStage.BEHAVIORAL, ApplicationStage.INTERVIEW,
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


def can_transition(from_stage: str, to_stage: str) -> bool:
    try:
        source = ApplicationStage(from_stage)
        target = ApplicationStage(to_stage)
    except ValueError:
        return False
    return target in _ALLOWED_TRANSITIONS.get(source, frozenset())


# ── Campaigns ────────────────────────────────────────────────────────


def create_campaign(org_id: int, name: str, description: str = "",
                    created_by: Optional[int] = None) -> int:
    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO campaigns (org_id, name, description, created_by) "
                f"VALUES ({p}, {p}, {p}, {p}) RETURNING id",
                (org_id, name, description, created_by),
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO campaigns (org_id, name, description, created_by) "
            f"VALUES ({p}, {p}, {p}, {p})",
            (org_id, name, description, created_by),
        )
        return cur.lastrowid


def get_campaign(campaign_id: int, org_id: int) -> Optional[dict]:
    """Always org-scoped — a campaign cannot be read across tenants."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM campaigns WHERE id = {p} AND org_id = {p} AND deleted_at IS NULL",
            (campaign_id, org_id),
        )
        return _row_to_dict(cur.fetchone())


def list_campaigns(org_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM campaigns WHERE org_id = {p} AND deleted_at IS NULL "
            f"ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
            (org_id, limit, offset),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def update_campaign(campaign_id: int, org_id: int, **fields) -> bool:
    allowed = {"name", "description", "status"}
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
                  status: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    """Recruiter-facing listing, always org-scoped."""
    p = _ph()
    clauses = [f"org_id = {p}", "deleted_at IS NULL"]
    params: list = [org_id]
    if campaign_id is not None:
        clauses.append(f"campaign_id = {p}")
        params.append(campaign_id)
    if status is not None:
        clauses.append(f"status = {p}")
        params.append(status)
    params.extend([limit, offset])
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM job_postings WHERE {' AND '.join(clauses)} "
            f"ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
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
                       source: str = "DIRECT") -> int:
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
        return application_id
    except _IntegrityError as exc:
        raise DuplicateApplicationError(
            "You have already applied to this posting."
        ) from exc


def get_application(application_id: int, org_id: Optional[int] = None) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        if org_id is None:
            cur.execute(f"SELECT * FROM applications WHERE id = {p}", (application_id,))
        else:
            cur.execute(
                f"SELECT * FROM applications WHERE id = {p} AND org_id = {p}",
                (application_id, org_id),
            )
        row = _row_to_dict(cur.fetchone())
    if row and isinstance(row.get("profile_snapshot"), str):
        row["profile_snapshot"] = json.loads(row["profile_snapshot"])
    return row


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
            f"SELECT a.*, u.full_name AS candidate_name, u.email AS candidate_email "
            f"FROM applications a JOIN users u ON u.id = a.candidate_user_id "
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
            f"p.location, p.remote_policy, o.name AS org_name "
            f"FROM applications a "
            f"JOIN job_postings p ON p.id = a.posting_id "
            f"JOIN organizations o ON o.id = a.org_id "
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
        cur.execute(
            f"SELECT current_stage FROM applications WHERE id = {p} AND org_id = {p}",
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
        return True


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
