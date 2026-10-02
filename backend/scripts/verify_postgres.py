"""Verify the local PostgreSQL contract, RLS policies, and concurrent job claims.

Usage (PowerShell):
  $env:DATABASE_URL = 'postgresql://...'
  python backend/scripts/verify_postgres.py

The script creates and removes synthetic rows. It never prints the connection
string or credentials.
"""

from __future__ import annotations

import concurrent.futures
import os
import sys
import uuid

import psycopg2
from psycopg2 import sql

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SET_CURRENT_ORG_SQL = "SELECT set_config('evalia.current_org_id', %s, false)"
SET_CURRENT_USER_SQL = "SELECT set_config('evalia.current_user_id', %s, false)"
CLEAR_CURRENT_ORG_SQL = "SELECT set_config('evalia.current_org_id', '', false)"
CLEAR_CURRENT_USER_SQL = "SELECT set_config('evalia.current_user_id', '', false)"
SET_WORKER_SQL = "SELECT set_config('evalia.is_worker', 'true', false)"
CLEAR_WORKER_SQL = "SELECT set_config('evalia.is_worker', 'false', false)"
RESET_ROLE_SQL = "RESET ROLE"
SELECT_AI_INTERVIEWS_SQL = (
    "SELECT id FROM application_ai_interviews WHERE id IN (%s, %s) ORDER BY id"
)
SELECT_NOTIFICATION_SQL = "SELECT id FROM user_notifications WHERE id = %s"


def _set_probe_role(cur, probe_role: str) -> None:
    cur.execute(sql.SQL("SET ROLE {} ").format(sql.Identifier(probe_role)))


def _reset_probe_role(cur) -> None:
    cur.execute(RESET_ROLE_SQL)


def _verify_organization_rls(cur, probe_role: str, fixture: dict[str, int]) -> None:
    _set_probe_role(cur, probe_role)
    cur.execute(SET_CURRENT_ORG_SQL, (str(fixture["org_a"]),))
    cur.execute(
        "SELECT id FROM campaigns WHERE id IN (%s, %s) ORDER BY id",
        (fixture["campaign_a"], fixture["campaign_b"]),
    )
    visible_campaigns_a = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT id FROM applications WHERE id IN (%s, %s) ORDER BY id",
        (fixture["application_a"], fixture["application_b"]),
    )
    visible_applications_a = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT interview_id FROM interview_scorecards WHERE interview_id IN (%s, %s) ORDER BY interview_id",
        (fixture["human_interview_a"], fixture["human_interview_b"]),
    )
    visible_scorecards_a = [row[0] for row in cur.fetchall()]

    cur.execute(SET_CURRENT_ORG_SQL, (str(fixture["org_b"]),))
    cur.execute(
        "SELECT id FROM campaigns WHERE id IN (%s, %s) ORDER BY id",
        (fixture["campaign_a"], fixture["campaign_b"]),
    )
    visible_campaigns_b = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT id FROM applications WHERE id IN (%s, %s) ORDER BY id",
        (fixture["application_a"], fixture["application_b"]),
    )
    visible_applications_b = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT interview_id FROM interview_scorecards WHERE interview_id IN (%s, %s) ORDER BY interview_id",
        (fixture["human_interview_a"], fixture["human_interview_b"]),
    )
    visible_scorecards_b = [row[0] for row in cur.fetchall()]
    _reset_probe_role(cur)

    assert visible_campaigns_a == [fixture["campaign_a"]], f"RLS org A campaign leak: {visible_campaigns_a}"
    assert visible_campaigns_b == [fixture["campaign_b"]], f"RLS org B campaign leak: {visible_campaigns_b}"
    assert visible_applications_a == [fixture["application_a"]], f"Application RLS org A leak: {visible_applications_a}"
    assert visible_applications_b == [fixture["application_b"]], f"Application RLS org B leak: {visible_applications_b}"
    assert visible_scorecards_a == [fixture["human_interview_a"]], f"Scorecard RLS org A leak: {visible_scorecards_a}"
    assert visible_scorecards_b == [fixture["human_interview_b"]], f"Scorecard RLS org B leak: {visible_scorecards_b}"
    print("Organization application/scorecard RLS: PASS")


def _verify_ai_interview_rls(cur, probe_role: str, fixture: dict[str, int]) -> None:
    _set_probe_role(cur, probe_role)
    cur.execute(SET_CURRENT_ORG_SQL, (str(fixture["org_a"]),))
    cur.execute(CLEAR_CURRENT_USER_SQL)
    cur.execute(CLEAR_WORKER_SQL)
    cur.execute(SELECT_AI_INTERVIEWS_SQL, (fixture["interview_a"], fixture["interview_b"]))
    visible_org_interviews = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT id FROM application_ai_interview_turns WHERE id IN (%s, %s) ORDER BY id",
        (fixture["turn_a"], fixture["turn_b"]),
    )
    visible_org_turns = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT application_id FROM application_interview_reports WHERE application_id IN (%s, %s) ORDER BY application_id",
        (fixture["application_a"], fixture["application_b"]),
    )
    visible_org_reports = [row[0] for row in cur.fetchall()]

    cur.execute(CLEAR_CURRENT_ORG_SQL)
    cur.execute(SET_CURRENT_USER_SQL, (str(fixture["user_a"]),))
    cur.execute(SELECT_AI_INTERVIEWS_SQL, (fixture["interview_a"], fixture["interview_b"]))
    visible_candidate_a_interviews = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT id FROM application_ai_interview_turns WHERE id IN (%s, %s) ORDER BY id",
        (fixture["turn_a"], fixture["turn_b"]),
    )
    visible_candidate_a_turns = [row[0] for row in cur.fetchall()]
    cur.execute(
        "SELECT application_id FROM application_interview_reports WHERE application_id IN (%s, %s)",
        (fixture["application_a"], fixture["application_b"]),
    )
    visible_candidate_reports = cur.fetchall()
    cur.execute(
        "UPDATE application_ai_interview_turns SET draft_answer_text = 'unauthorized probe' WHERE id = %s",
        (fixture["turn_b"],),
    )
    cross_candidate_update_count = cur.rowcount

    cur.execute(SET_CURRENT_USER_SQL, (str(fixture["user_b"]),))
    cur.execute(SELECT_AI_INTERVIEWS_SQL, (fixture["interview_a"], fixture["interview_b"]))
    visible_candidate_b_interviews = [row[0] for row in cur.fetchall()]

    cur.execute(SET_CURRENT_ORG_SQL, (str(fixture["org_a"]),))
    cur.execute(CLEAR_CURRENT_USER_SQL)
    cur.execute(SET_WORKER_SQL)
    cur.execute(
        "SELECT application_id FROM application_interview_reports WHERE application_id IN (%s, %s) ORDER BY application_id",
        (fixture["application_a"], fixture["application_b"]),
    )
    visible_worker_reports = [row[0] for row in cur.fetchall()]
    cur.execute(
        "UPDATE application_ai_interview_turns SET assessment_json = '{\"worker_probe\":true}' WHERE id = %s",
        (fixture["turn_a"],),
    )
    worker_can_update_own_tenant_turn = cur.rowcount == 1
    _reset_probe_role(cur)

    assert visible_org_interviews == [fixture["interview_a"]], "AI interview RLS leaked across organizations"
    assert visible_org_turns == [fixture["turn_a"]], "Interview turn RLS leaked across organizations"
    assert visible_org_reports == [fixture["application_a"]], "Interview report RLS leaked across organizations"
    assert visible_candidate_a_interviews == [fixture["interview_a"]], "Candidate AI-interview RLS exposed another user's session"
    assert visible_candidate_a_turns == [fixture["turn_a"]], "Candidate AI-turn RLS exposed another user's transcript"
    assert visible_candidate_reports == [], "Candidate context unexpectedly exposed recruiter reports"
    assert cross_candidate_update_count == 0, "Candidate context updated another user's interview turn"
    assert visible_candidate_b_interviews == [fixture["interview_b"]], "Second candidate could not read their own AI-interview session"
    assert visible_worker_reports == [fixture["application_a"]], "Worker context leaked reports across organizations"
    assert worker_can_update_own_tenant_turn, "Worker context could not write an AI-interview turn in its organization"
    print("AI interview session/turn/report RLS: PASS")


def _verify_notification_rls(cur, probe_role: str, fixture: dict[str, int]) -> tuple[int, int]:
    _set_probe_role(cur, probe_role)
    cur.execute(CLEAR_CURRENT_ORG_SQL)
    cur.execute(SET_CURRENT_USER_SQL, (str(fixture["user_a"]),))
    cur.execute(CLEAR_WORKER_SQL)
    cur.execute(
        "INSERT INTO user_notifications (user_id, notification_type, title, dedupe_key) "
        "VALUES (%s, 'RLS_PROBE', 'Owner-only notification', %s) RETURNING id",
        (fixture["user_a"], f"rls-notification-{uuid.uuid4().hex}"),
    )
    owner_notification_id = cur.fetchone()[0]
    cur.execute(SELECT_NOTIFICATION_SQL, (owner_notification_id,))
    owner_can_read = [row[0] for row in cur.fetchall()] == [owner_notification_id]
    cur.execute(SET_CURRENT_USER_SQL, (str(fixture["user_b"]),))
    cur.execute(SELECT_NOTIFICATION_SQL, (owner_notification_id,))
    peer_cannot_read = cur.fetchall() == []

    cur.execute(SET_CURRENT_ORG_SQL, (str(fixture["org_a"]),))
    cur.execute(CLEAR_CURRENT_USER_SQL)
    cur.execute(SET_WORKER_SQL)
    worker_key = f"rls-worker-notification-{uuid.uuid4().hex}"
    cur.execute(
        "INSERT INTO user_notifications (user_id, org_id, notification_type, title, dedupe_key) "
        "VALUES (%s, %s, 'RLS_WORKER_PROBE', 'Worker-created notification', %s) RETURNING id",
        (fixture["user_a"], fixture["org_a"], worker_key),
    )
    worker_notification_id = cur.fetchone()[0]
    cur.execute(SELECT_NOTIFICATION_SQL, (worker_notification_id,))
    worker_can_read = [row[0] for row in cur.fetchall()] == [worker_notification_id]
    cur.execute(CLEAR_WORKER_SQL)
    cur.execute(CLEAR_CURRENT_ORG_SQL)
    cur.execute(SET_CURRENT_USER_SQL, (str(fixture["user_a"]),))
    cur.execute(SELECT_NOTIFICATION_SQL, (worker_notification_id,))
    owner_can_read_worker_notice = [row[0] for row in cur.fetchall()] == [worker_notification_id]
    cur.execute(SET_CURRENT_USER_SQL, (str(fixture["user_b"]),))
    cur.execute(SELECT_NOTIFICATION_SQL, (worker_notification_id,))
    peer_cannot_read_worker_notice = cur.fetchall() == []
    _reset_probe_role(cur)

    assert owner_can_read, "Notification owner could not read their notification"
    assert peer_cannot_read, "Notification RLS leaked a user's inbox to another user"
    assert worker_can_read, "Tenant worker context could not access the org notification"
    assert owner_can_read_worker_notice, "Notification owner could not access their worker-created notification"
    assert peer_cannot_read_worker_notice, "Tenant worker context exposed another user's notification"
    print("Notification owner/worker RLS: PASS")
    return owner_notification_id, worker_notification_id


def _verify_policy_coverage(cur) -> None:
    cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = current_schema() AND policyname LIKE 'evalia_rls_%'")
    policy_count = cur.fetchone()[0]
    assert policy_count >= 10, f"Expected RLS policies, found {policy_count}"
    print(f"RLS policy coverage: PASS ({policy_count} policies)")


def _create_probe_fixtures(cur, fixture: dict[str, int]) -> dict[str, int]:
    cur.execute(
        "INSERT INTO organizations (name, slug) VALUES (%s, %s) RETURNING id",
        ("RLS Probe A", f"rls-a-{uuid.uuid4().hex[:8]}"),
    )
    fixture["org_a"] = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO organizations (name, slug) VALUES (%s, %s) RETURNING id",
        ("RLS Probe B", f"rls-b-{uuid.uuid4().hex[:8]}"),
    )
    fixture["org_b"] = cur.fetchone()[0]
    cur.execute("INSERT INTO campaigns (org_id, name) VALUES (%s, %s) RETURNING id", (fixture["org_a"], "Campaign A"))
    fixture["campaign_a"] = cur.fetchone()[0]
    cur.execute("INSERT INTO campaigns (org_id, name) VALUES (%s, %s) RETURNING id", (fixture["org_b"], "Campaign B"))
    fixture["campaign_b"] = cur.fetchone()[0]

    user_a_email = f"rls-a-{uuid.uuid4().hex}@example.invalid"
    user_b_email = f"rls-b-{uuid.uuid4().hex}@example.invalid"
    cur.execute(
        "INSERT INTO users (email, email_normalized, password_hash) VALUES (%s, %s, 'probe') RETURNING id",
        (user_a_email, user_a_email),
    )
    fixture["user_a"] = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO users (email, email_normalized, password_hash) VALUES (%s, %s, 'probe') RETURNING id",
        (user_b_email, user_b_email),
    )
    fixture["user_b"] = cur.fetchone()[0]

    for suffix in ("a", "b"):
        cur.execute(
            "INSERT INTO job_postings (org_id, campaign_id, title, status) "
            "VALUES (%s, %s, %s, 'DRAFT') RETURNING id",
            (fixture[f"org_{suffix}"], fixture[f"campaign_{suffix}"], f"Synthetic RLS Probe {suffix.upper()}"),
        )
        fixture[f"posting_{suffix}"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO applications (org_id, posting_id, candidate_user_id) "
            "VALUES (%s, %s, %s) RETURNING id",
            (fixture[f"org_{suffix}"], fixture[f"posting_{suffix}"], fixture[f"user_{suffix}"]),
        )
        fixture[f"application_{suffix}"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO application_ai_interviews "
            "(application_id, org_id, candidate_user_id, rubric_version, status, phase) "
            "VALUES (%s, %s, %s, 'probe-v1', 'INTERVIEW_IN_PROGRESS', 'TECHNICAL') RETURNING id",
            (fixture[f"application_{suffix}"], fixture[f"org_{suffix}"], fixture[f"user_{suffix}"]),
        )
        fixture[f"interview_{suffix}"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO application_ai_interview_turns "
            "(interview_id, application_id, org_id, candidate_user_id, sequence_no, phase, question_text, answer_text) "
            "VALUES (%s, %s, %s, %s, 1, 'TECHNICAL', %s, %s) RETURNING id",
            (
                fixture[f"interview_{suffix}"], fixture[f"application_{suffix}"],
                fixture[f"org_{suffix}"], fixture[f"user_{suffix}"],
                f"Synthetic question {suffix.upper()}", f"Synthetic answer {suffix.upper()}",
            ),
        )
        fixture[f"turn_{suffix}"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
            "VALUES (%s, %s, 'Synthetic role', %s, %s) RETURNING id",
            (f"Synthetic {suffix.upper()}", f"Synthetic resume {suffix.upper()}", fixture[f"org_{suffix}"], fixture[f"user_{suffix}"]),
        )
        fixture[f"evaluation_{suffix}"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO application_interview_reports "
            "(application_id, evaluation_id, posting_id, org_id, recommendation, rubric_version) "
            "VALUES (%s, %s, %s, %s, 'HUMAN_REVIEW_REQUIRED', 'probe-v1')",
            (
                fixture[f"application_{suffix}"], fixture[f"evaluation_{suffix}"],
                fixture[f"posting_{suffix}"], fixture[f"org_{suffix}"],
            ),
        )
        cur.execute(
            "INSERT INTO interviews (org_id, application_id, title, scheduled_start, scheduled_end) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '1 hour') RETURNING id",
            (fixture[f"org_{suffix}"], fixture[f"application_{suffix}"], f"Synthetic panel {suffix.upper()}"),
        )
        fixture[f"human_interview_{suffix}"] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO interview_participants (interview_id, user_id, participant_role) "
            "VALUES (%s, %s, 'INTERVIEWER')",
            (fixture[f"human_interview_{suffix}"], fixture[f"user_{suffix}"]),
        )
        recommendation = "ADVANCE" if suffix == "a" else "HOLD"
        cur.execute(
            "INSERT INTO interview_scorecards (org_id, interview_id, interviewer_user_id, recommendation) "
            "VALUES (%s, %s, %s, %s)",
            (fixture[f"org_{suffix}"], fixture[f"human_interview_{suffix}"], fixture[f"user_{suffix}"], recommendation),
        )
    return fixture


def _verify_job_claim(db) -> int:
    db.set_request_db_context(user_id=None, org_id=None)
    job_key = f"postgres-concurrency:{uuid.uuid4().hex}"
    job_id = db.enqueue_job("postgres_probe", {"probe": True}, idempotency_key=job_key, max_attempts=3)

    def claim(worker: str):
        return db.claim_job(job_id, worker, lease_seconds=60)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("postgres-worker-a", "postgres-worker-b")))
    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1, f"Expected one atomic claim, got {len(claimed)}"
    print("Concurrent job claim: PASS (exactly one winner)")
    return job_id


def _cleanup_probe_side(cur, fixture: dict[str, int], suffix: str) -> None:
    human_interview_id = fixture.get(f"human_interview_{suffix}")
    if human_interview_id:
        cur.execute("DELETE FROM interviews WHERE id = %s", (human_interview_id,))
    application_id = fixture.get(f"application_{suffix}")
    if application_id:
        cur.execute("DELETE FROM applications WHERE id = %s", (application_id,))
    posting_id = fixture.get(f"posting_{suffix}")
    if posting_id:
        cur.execute("DELETE FROM job_postings WHERE id = %s", (posting_id,))
    evaluation_id = fixture.get(f"evaluation_{suffix}")
    if evaluation_id:
        cur.execute("DELETE FROM evaluations WHERE id = %s", (evaluation_id,))
    campaign_id = fixture.get(f"campaign_{suffix}")
    if campaign_id:
        cur.execute("DELETE FROM campaigns WHERE id = %s", (campaign_id,))
    user_id = fixture.get(f"user_{suffix}")
    if user_id:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    org_id = fixture.get(f"org_{suffix}")
    if org_id:
        cur.execute("DELETE FROM organizations WHERE id = %s", (org_id,))


def _cleanup_probe_fixtures(cur, fixture: dict[str, int], job_id: int | None) -> None:
    if job_id:
        cur.execute("DELETE FROM background_jobs WHERE id = %s", (job_id,))
    for suffix in ("a", "b"):
        _cleanup_probe_side(cur, fixture, suffix)
    notification_ids = [
        fixture[key]
        for key in ("notification_a", "worker_notification_id")
        if fixture.get(key)
    ]
    if notification_ids:
        cur.execute("DELETE FROM user_notifications WHERE id = ANY(%s)", (notification_ids,))


def main() -> int:
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is required; no database connection string was printed or stored.")

    from app.config import database as db

    db.init_db()
    if not db.USE_POSTGRES:
        raise SystemExit("DATABASE_URL did not select PostgreSQL.")

    probe_role = f"evalia_rls_probe_{os.getpid()}"
    job_id = None
    fixture: dict[str, int] = {}
    probe_role_created = False
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(probe_role)))
            probe_role_created = True
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {} ").format(sql.Identifier(probe_role)))
            cur.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {} ").format(
                    sql.Identifier(probe_role)
                )
            )
            cur.execute(
                sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {} ").format(
                    sql.Identifier(probe_role)
                )
            )
            _create_probe_fixtures(cur, fixture)
            conn.commit()
            fixture["notification_a"], fixture["worker_notification_id"] = _verify_notification_rls(cur, probe_role, fixture)
            _verify_organization_rls(cur, probe_role, fixture)
            _verify_ai_interview_rls(cur, probe_role, fixture)
            _verify_policy_coverage(cur)

        job_id = _verify_job_claim(db)
    finally:
        db.clear_request_db_context()
        conn.rollback()
        with conn, conn.cursor() as cur:
            _cleanup_probe_fixtures(cur, fixture, job_id)
            if probe_role_created:
                cur.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {} ").format(sql.Identifier(probe_role)))
                cur.execute(
                    sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {} ").format(
                        sql.Identifier(probe_role)
                    )
                )
                cur.execute(
                    sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {} ").format(
                        sql.Identifier(probe_role)
                    )
                )
                cur.execute(sql.SQL("DROP ROLE IF EXISTS {} ").format(sql.Identifier(probe_role)))
        conn.close()

    print("PostgreSQL verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
