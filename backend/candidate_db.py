"""
Candidate profile vault: data access.

The vault is the "fill it once" store. Its whole purpose is that a candidate
never re-enters the same information, so every read here is optimized for
assembling a complete application payload in one call
(:func:`get_full_profile`).

Connection helpers are reused from database.py rather than reimplemented, so
the dual SQLite/Postgres support and the transaction semantics stay in exactly
one place.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from database import _get_conn, _ph, _row_to_dict, USE_POSTGRES

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: bool):
    """SQLite has no native boolean; Postgres wants a real one."""
    return value if USE_POSTGRES else int(bool(value))


def normalize_skill(skill: str) -> str:
    """Casefold and collapse whitespace so 'Node JS' and 'node  js' match.

    Deliberately conservative: it does not attempt synonym resolution
    ('Postgres' vs 'PostgreSQL'). That belongs in the matching engine with a
    curated alias table, not in a storage-layer helper where it would silently
    rewrite what the candidate actually claimed.
    """
    return " ".join(skill.strip().casefold().split())


# ── Profile ──────────────────────────────────────────────────────────


def create_profile(user_id: int, **fields) -> int:
    """Create a candidate profile for a user."""
    allowed = {
        "headline", "summary", "location", "phone",
        "work_authorization", "years_experience", "resume_text",
    }
    data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    columns = ["user_id", *data.keys()]
    values = [user_id, *data.values()]
    p = _ph()
    placeholders = ", ".join([p] * len(columns))

    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO candidate_profiles ({', '.join(columns)}) "
                f"VALUES ({placeholders}) RETURNING id",
                tuple(values),
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO candidate_profiles ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values),
        )
        return cur.lastrowid


def get_profile_by_user(user_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM candidate_profiles WHERE user_id = {p} AND deleted_at IS NULL",
            (user_id,),
        )
        return _row_to_dict(cur.fetchone())


def get_profile(profile_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM candidate_profiles WHERE id = {p} AND deleted_at IS NULL",
            (profile_id,),
        )
        return _row_to_dict(cur.fetchone())


def update_profile(profile_id: int, **fields) -> None:
    allowed = {
        "headline", "summary", "location", "phone", "work_authorization",
        "years_experience", "open_to_work", "resume_text",
        "data_consent_at", "data_consent_version", "retention_until",
    }
    data = {k: v for k, v in fields.items() if k in allowed}
    if not data:
        return
    if "open_to_work" in data:
        data["open_to_work"] = _bool(data["open_to_work"])
    data["updated_at"] = _now()

    p = _ph()
    clause = ", ".join(f"{k} = {p}" for k in data)
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE candidate_profiles SET {clause} WHERE id = {p}",
            (*data.values(), profile_id),
        )


def record_consent(profile_id: int, version: str) -> None:
    """Stamp data-processing consent.

    Captured from day one even though enforcement is per-market configuration,
    because consent cannot be retroactively obtained for data already held.
    """
    update_profile(profile_id, data_consent_at=_now(), data_consent_version=version)


# ── Work experience ──────────────────────────────────────────────────


def add_experience(profile_id: int, **fields) -> int:
    p = _ph()
    columns = [
        "profile_id", "company", "title", "location",
        "start_date", "end_date", "is_current", "description",
    ]
    values = (
        profile_id,
        fields.get("company", ""),
        fields.get("title", ""),
        fields.get("location", ""),
        fields.get("start_date", ""),
        fields.get("end_date"),
        _bool(fields.get("is_current", False)),
        fields.get("description", ""),
    )
    placeholders = ", ".join([p] * len(columns))
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO work_experiences ({', '.join(columns)}) "
                f"VALUES ({placeholders}) RETURNING id",
                values,
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO work_experiences ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return cur.lastrowid


def list_experiences(profile_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM work_experiences WHERE profile_id = {p} "
            f"ORDER BY is_current DESC, start_date DESC",
            (profile_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def delete_experience(profile_id: int, experience_id: int) -> bool:
    """Delete scoped by profile_id so one candidate cannot delete another's row."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"DELETE FROM work_experiences WHERE id = {p} AND profile_id = {p}",
            (experience_id, profile_id),
        )
        return cur.rowcount > 0


# ── Education ────────────────────────────────────────────────────────


def add_education(profile_id: int, **fields) -> int:
    p = _ph()
    columns = ["profile_id", "institution", "degree", "field", "start_year", "end_year"]
    values = (
        profile_id,
        fields.get("institution", ""),
        fields.get("degree", ""),
        fields.get("field", ""),
        fields.get("start_year"),
        fields.get("end_year"),
    )
    placeholders = ", ".join([p] * len(columns))
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO education_entries ({', '.join(columns)}) "
                f"VALUES ({placeholders}) RETURNING id",
                values,
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO education_entries ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return cur.lastrowid


def list_education(profile_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM education_entries WHERE profile_id = {p} ORDER BY end_year DESC",
            (profile_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


# ── Skills ───────────────────────────────────────────────────────────


def set_skills(profile_id: int, skills: list[dict]) -> None:
    """Replace the claimed-skill set.

    Verified skills are preserved across a replace: they were earned by
    demonstrated performance, and a profile edit must not be able to silently
    fabricate or destroy that signal.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT skill_normalized, verified, verified_source FROM skill_claims "
            f"WHERE profile_id = {p} AND verified = {'TRUE' if USE_POSTGRES else '1'}",
            (profile_id,),
        )
        verified = {
            r["skill_normalized"]: r["verified_source"] for r in cur.fetchall()
        }

        cur.execute(f"DELETE FROM skill_claims WHERE profile_id = {p}", (profile_id,))
        for entry in skills:
            name = (entry.get("skill") or "").strip()
            if not name:
                continue
            normalized = normalize_skill(name)
            was_verified = normalized in verified
            cur.execute(
                f"INSERT INTO skill_claims "
                f"(profile_id, skill, skill_normalized, years, verified, verified_source) "
                f"VALUES ({p}, {p}, {p}, {p}, {p}, {p})",
                (
                    profile_id, name, normalized, entry.get("years"),
                    _bool(was_verified), verified.get(normalized),
                ),
            )


def list_skills(profile_id: int) -> list[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM skill_claims WHERE profile_id = {p} ORDER BY skill",
            (profile_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def mark_skill_verified(profile_id: int, skill: str, source: str) -> bool:
    """Flag a skill as demonstrated in-platform (e.g. by a passed assessment)."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE skill_claims SET verified = {'TRUE' if USE_POSTGRES else '1'}, "
            f"verified_source = {p} WHERE profile_id = {p} AND skill_normalized = {p}",
            (source, profile_id, normalize_skill(skill)),
        )
        return cur.rowcount > 0


# ── Preferences ──────────────────────────────────────────────────────


def set_preferences(profile_id: int, **fields) -> None:
    """Upsert job preferences."""
    payload = {
        "desired_roles": json.dumps(fields.get("desired_roles", [])),
        "locations": json.dumps(fields.get("locations", [])),
        "remote_preference": fields.get("remote_preference", "ANY"),
        "min_salary": fields.get("min_salary"),
        "max_salary": fields.get("max_salary"),
        "currency": fields.get("currency", "INR"),
        "notice_period_days": fields.get("notice_period_days"),
        "updated_at": _now(),
    }
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT profile_id FROM job_preferences WHERE profile_id = {p}", (profile_id,))
        if cur.fetchone() is None:
            columns = ["profile_id", *payload.keys()]
            placeholders = ", ".join([p] * len(columns))
            cur.execute(
                f"INSERT INTO job_preferences ({', '.join(columns)}) VALUES ({placeholders})",
                (profile_id, *payload.values()),
            )
        else:
            clause = ", ".join(f"{k} = {p}" for k in payload)
            cur.execute(
                f"UPDATE job_preferences SET {clause} WHERE profile_id = {p}",
                (*payload.values(), profile_id),
            )


def get_preferences(profile_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT * FROM job_preferences WHERE profile_id = {p}", (profile_id,))
        row = _row_to_dict(cur.fetchone())
    if row:
        row["desired_roles"] = json.loads(row["desired_roles"])
        row["locations"] = json.loads(row["locations"])
    return row


# ── Answer vault ─────────────────────────────────────────────────────


def upsert_vault_answer(profile_id: int, question_key: str, answer_text: str,
                        question_text: str = "") -> None:
    """Store or update a reusable answer.

    This is what makes "fill it once" real: every new question asked during an
    application is captured here so the next application can pre-fill it.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT id FROM answer_vault_entries WHERE profile_id = {p} AND question_key = {p}",
            (profile_id, question_key),
        )
        if cur.fetchone() is None:
            cur.execute(
                f"INSERT INTO answer_vault_entries "
                f"(profile_id, question_key, question_text, answer_text) "
                f"VALUES ({p}, {p}, {p}, {p})",
                (profile_id, question_key, question_text, answer_text),
            )
        else:
            cur.execute(
                f"UPDATE answer_vault_entries SET answer_text = {p}, question_text = {p}, "
                f"updated_at = {p} WHERE profile_id = {p} AND question_key = {p}",
                (answer_text, question_text, _now(), profile_id, question_key),
            )


def get_vault_answers(profile_id: int) -> dict[str, str]:
    """All vault answers as a question_key -> answer_text mapping."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT question_key, answer_text FROM answer_vault_entries WHERE profile_id = {p}",
            (profile_id,),
        )
        return {r["question_key"]: r["answer_text"] for r in cur.fetchall()}


# ── Composite read ───────────────────────────────────────────────────


def get_full_profile(user_id: int) -> Optional[dict]:
    """Assemble the complete vault for a user in one call."""
    profile = get_profile_by_user(user_id)
    if profile is None:
        return None
    profile_id = profile["id"]
    return {
        **profile,
        "experiences": list_experiences(profile_id),
        "education": list_education(profile_id),
        "skills": list_skills(profile_id),
        "preferences": get_preferences(profile_id),
        "vault_answers": get_vault_answers(profile_id),
    }


def build_application_snapshot(user_id: int) -> dict:
    """Immutable profile copy stored on an application at submission time.

    Excludes the raw resume text: an application record is read by recruiters
    routinely, and the full resume is separately access-controlled.
    """
    full = get_full_profile(user_id)
    if full is None:
        return {}
    return {
        "headline": full["headline"],
        "summary": full["summary"],
        "location": full["location"],
        "years_experience": full["years_experience"],
        "work_authorization": full["work_authorization"],
        "experiences": [
            {k: e[k] for k in ("company", "title", "start_date", "end_date", "is_current", "description")}
            for e in full["experiences"]
        ],
        "education": [
            {k: e[k] for k in ("institution", "degree", "field", "end_year")}
            for e in full["education"]
        ],
        "skills": [{"skill": s["skill"], "years": s["years"], "verified": bool(s["verified"])}
                   for s in full["skills"]],
        "snapshot_taken_at": _now(),
    }
