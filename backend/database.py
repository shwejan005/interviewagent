"""
Database Module — PostgreSQL (primary) / SQLite (fallback) persistence.

When the DATABASE_URL environment variable is set, connects to PostgreSQL
using a thread-safe connection pool (psycopg2). Otherwise, falls back to
local SQLite for frictionless development.

All public function signatures are unchanged — routes.py and main.py
continue to call the same API regardless of the active backend.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ── Dialect detection ────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Render/Heroku sometimes issue postgres:// instead of postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = bool(DATABASE_URL)

# ── SQLite backend ──────────────────────────────────────────────────

if not USE_POSTGRES:
    import sqlite3

    _SQLITE_PATH = os.path.join(os.path.dirname(__file__), "evalia.db")

    def _sqlite_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    _IntegrityError = sqlite3.IntegrityError

# ── PostgreSQL backend ──────────────────────────────────────────────

if USE_POSTGRES:
    import psycopg2
    import psycopg2.pool
    import psycopg2.extras

    _IntegrityError = psycopg2.IntegrityError

    _pg_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

    def _init_pg_pool() -> psycopg2.pool.ThreadedConnectionPool:
        global _pg_pool
        if _pg_pool is None:
            _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=DATABASE_URL,
            )
            logger.info("PostgreSQL connection pool created (min=2, max=10).")
        return _pg_pool

    def _close_pg_pool() -> None:
        global _pg_pool
        if _pg_pool is not None:
            _pg_pool.closeall()
            _pg_pool = None
            logger.info("PostgreSQL connection pool closed.")


# ── Unified connection context manager ──────────────────────────────

@contextmanager
def _get_conn():
    """
    Yield a (connection, cursor) pair.

    For PostgreSQL: pulls from pool, uses RealDictCursor, auto-commits on
    success, rolls back on error, and returns the conn to the pool.

    For SQLite: opens a plain connection with Row factory.
    """
    if USE_POSTGRES:
        pool = _init_pg_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            yield conn, cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            pool.putconn(conn)
    else:
        conn = _sqlite_conn()
        try:
            yield conn, conn.cursor()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ── Helpers ─────────────────────────────────────────────────────────

def _ph(name: str = "") -> str:
    """Return the parameter placeholder for the active dialect."""
    return "%s" if USE_POSTGRES else "?"


def _row_to_dict(row) -> dict:
    """Convert a row (sqlite3.Row or RealDictRow) to a plain dict."""
    if row is None:
        return None
    if USE_POSTGRES:
        return dict(row)
    return dict(row)


def _now_sql() -> str:
    """Default-timestamp expression for each dialect."""
    return "CURRENT_TIMESTAMP" if USE_POSTGRES else "datetime('now')"


class DuplicateVerdictError(Exception):
    """Raised when a canonical verdict already exists for this evaluation/round.

    A failed agent execution is recorded with decision='INVALID_OUTPUT' and does
    not count as canonical, so retries after a failure are still allowed. This
    exception surfaces a genuine race between two concurrent successful
    submissions for the same round.
    """


# Evaluation columns safe to return outside the agent-execution path — excludes
# resume_text, which is personal candidate data only needed internally to run agents.
_EVALUATION_SUMMARY_COLUMNS = (
    "id, candidate_name, role, status, current_round, "
    "overall_score, final_decision, created_at, updated_at"
)


# ── Schema ──────────────────────────────────────────────────────────

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id SERIAL PRIMARY KEY,
    candidate_name TEXT DEFAULT '',
    resume_text TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    current_round INTEGER NOT NULL DEFAULT 1,
    overall_score DOUBLE PRECISION,
    final_decision TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_verdicts (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    agent_type TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    verdict_json TEXT NOT NULL,
    verdict_text TEXT NOT NULL DEFAULT '',
    score DOUBLE PRECISION,
    decision TEXT,
    confidence DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interview_questions (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    questions_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interview_answers (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_verdicts_eval ON agent_verdicts(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_questions_eval ON interview_questions(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_answers_eval ON interview_answers(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status);

-- Only one canonical (successfully validated) verdict per evaluation/round.
-- Failed agent executions are recorded with decision='INVALID_OUTPUT' and are
-- exempt, so a retry after a failure is never blocked by this constraint.
CREATE UNIQUE INDEX IF NOT EXISTS uq_verdicts_canonical
    ON agent_verdicts (evaluation_id, round_number)
    WHERE decision <> 'INVALID_OUTPUT';

CREATE TABLE IF NOT EXISTS background_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    idempotency_key TEXT,
    CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'DEAD')),
    CHECK (attempts >= 0 AND max_attempts > 0)
);

CREATE INDEX IF NOT EXISTS idx_background_jobs_claim
    ON background_jobs(status, available_at, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_background_jobs_idempotency
    ON background_jobs(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
"""

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_name TEXT DEFAULT '',
    resume_text TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    current_round INTEGER NOT NULL DEFAULT 1,
    overall_score REAL,
    final_decision TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL,
    agent_type TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    verdict_json TEXT NOT NULL,
    verdict_text TEXT NOT NULL DEFAULT '',
    score REAL,
    decision TEXT,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS interview_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    questions_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS interview_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    answer_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (evaluation_id) REFERENCES evaluations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verdicts_eval ON agent_verdicts(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_questions_eval ON interview_questions(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_answers_eval ON interview_answers(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_status ON evaluations(status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_verdicts_canonical
    ON agent_verdicts (evaluation_id, round_number)
    WHERE decision <> 'INVALID_OUTPUT';

CREATE TABLE IF NOT EXISTS background_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TEXT NOT NULL DEFAULT (datetime('now')),
    locked_at TEXT,
    locked_by TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    idempotency_key TEXT,
    CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'DEAD')),
    CHECK (attempts >= 0 AND max_attempts > 0)
);

CREATE INDEX IF NOT EXISTS idx_background_jobs_claim
    ON background_jobs(status, available_at, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_background_jobs_idempotency
    ON background_jobs(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
"""


# ── Identity, tenancy & audit schema ────────────────────────────────
#
# Added in the platform foundation phase. Kept in separate DDL constants from
# the original interview-pipeline schema above so the two can be reasoned
# about (and if ever necessary, migrated) independently.

_PG_IDENTITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    plan TEXT NOT NULL DEFAULT 'trial',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    email_verified_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    is_system BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_capabilities (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    capability TEXT NOT NULL,
    PRIMARY KEY (role_id, capability)
);

CREATE TABLE IF NOT EXISTS org_memberships (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS invitations (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email_normalized TEXT NOT NULL,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    token_hash TEXT NOT NULL UNIQUE,
    invited_by INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'PENDING',
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tier INTEGER NOT NULL,
    action TEXT NOT NULL,
    actor_user_id INTEGER,
    actor_org_id INTEGER,
    actor_role TEXT,
    actor_ip TEXT,
    impersonated_by INTEGER,
    resource_type TEXT,
    resource_id TEXT,
    resource_org_id INTEGER,
    outcome TEXT NOT NULL DEFAULT 'SUCCESS',
    detail TEXT NOT NULL DEFAULT '{}',
    request_id TEXT,
    prev_hash TEXT,
    hash TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_user_org
    ON org_memberships (org_id, user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_membership_user ON org_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_events(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_events(actor_org_id);
"""

_SQLITE_IDENTITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    plan TEXT NOT NULL DEFAULT 'trial',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    is_platform_admin INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    email_verified_at TEXT,
    last_login_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    is_system INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS role_capabilities (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    capability TEXT NOT NULL,
    PRIMARY KEY (role_id, capability)
);

CREATE TABLE IF NOT EXISTS org_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS invitations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email_normalized TEXT NOT NULL,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    token_hash TEXT NOT NULL UNIQUE,
    invited_by INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'PENDING',
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    tier INTEGER NOT NULL,
    action TEXT NOT NULL,
    actor_user_id INTEGER,
    actor_org_id INTEGER,
    actor_role TEXT,
    actor_ip TEXT,
    impersonated_by INTEGER,
    resource_type TEXT,
    resource_id TEXT,
    resource_org_id INTEGER,
    outcome TEXT NOT NULL DEFAULT 'SUCCESS',
    detail TEXT NOT NULL DEFAULT '{}',
    request_id TEXT,
    prev_hash TEXT,
    hash TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_user_org
    ON org_memberships (org_id, user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_membership_user ON org_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_events(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_events(actor_org_id);
"""


# Additive columns retrofitted onto the pre-existing evaluations table.
# Nullable by necessity: rows created before ownership existed cannot be
# retroactively attributed, and inventing an owner for them would corrupt the
# audit story. Unowned rows are treated as legacy and excluded from tenant
# queries rather than leaked into an arbitrary org.
_EVALUATION_TENANCY_COLUMNS = (
    ("org_id", "INTEGER"),
    ("owner_user_id", "INTEGER"),
)

# Additive columns introduced after the initial hiring schema. These are
# nullable or have safe defaults so existing local databases can be upgraded
# in place without rewriting candidate data.
_HIRING_ADDITIVE_COLUMNS = (
    (
        "candidate_profiles",
        "is_discoverable",
        "BOOLEAN NOT NULL DEFAULT FALSE" if USE_POSTGRES else "INTEGER NOT NULL DEFAULT 0",
    ),
    ("campaigns", "department", "TEXT NOT NULL DEFAULT ''"),
    ("campaigns", "hiring_manager", "TEXT NOT NULL DEFAULT ''"),
    ("campaigns", "priority", "TEXT NOT NULL DEFAULT 'MEDIUM'"),
    ("campaigns", "target_hires", "INTEGER"),
    ("campaigns", "target_close_date", "TIMESTAMPTZ" if USE_POSTGRES else "TEXT"),
)


# ── Initialization ──────────────────────────────────────────────────

def _existing_columns(cur, table: str) -> set[str]:
    """Return the current column names of a table, for additive migrations."""
    if USE_POSTGRES:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {r["column_name"] for r in cur.fetchall()}
    cur.execute(f"PRAGMA table_info({table})")
    return {r["name"] for r in cur.fetchall()}


def _apply_additive_columns(cur) -> None:
    """Add tenancy columns to `evaluations` if an older database predates them.

    Kept deliberately narrow: this is not a migration framework, and it only
    handles the additive, nullable, no-backfill case. Anything requiring a
    backfill or a type change needs a real migration tool (see DECISIONS.md).
    """
    present = _existing_columns(cur, "evaluations")
    for column, coltype in _EVALUATION_TENANCY_COLUMNS:
        if column not in present:
            cur.execute(f"ALTER TABLE evaluations ADD COLUMN {column} {coltype}")
            logger.info("Added column evaluations.%s", column)


def _apply_hiring_additive_columns(cur) -> None:
    """Add safe, additive columns introduced by later hiring features."""
    for table, column, coltype in _HIRING_ADDITIVE_COLUMNS:
        present = _existing_columns(cur, table)
        if column not in present:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            logger.info("Added column %s.%s", table, column)


def _seed_roles(cur) -> None:
    """Insert system roles and their capabilities, idempotently.

    Capabilities are re-synced on every startup so that a code change to
    SYSTEM_ROLES takes effect without a manual migration step.
    """
    from rbac import SYSTEM_ROLES

    p = _ph()
    for role, capabilities in SYSTEM_ROLES.items():
        cur.execute(f"SELECT id FROM roles WHERE name = {p}", (role.value,))
        row = cur.fetchone()
        if row is None:
            if USE_POSTGRES:
                cur.execute(
                    f"INSERT INTO roles (name, is_system) VALUES ({p}, TRUE) RETURNING id",
                    (role.value,),
                )
                role_id = cur.fetchone()["id"]
            else:
                cur.execute(
                    f"INSERT INTO roles (name, is_system) VALUES ({p}, 1)",
                    (role.value,),
                )
                role_id = cur.lastrowid
        else:
            role_id = row["id"]

        cur.execute(f"DELETE FROM role_capabilities WHERE role_id = {p}", (role_id,))
        for capability in sorted(capabilities):
            cur.execute(
                f"INSERT INTO role_capabilities (role_id, capability) VALUES ({p}, {p})",
                (role_id, str(capability)),
            )


def init_db() -> None:
    """Initialize database schema. Safe to call multiple times."""
    import hiring_schema

    if USE_POSTGRES:
        with _get_conn() as (conn, cur):
            cur.execute(_PG_SCHEMA)
            cur.execute(_PG_IDENTITY_SCHEMA)
            cur.execute(hiring_schema.SCHEMA_PG)
            _apply_additive_columns(cur)
            _apply_hiring_additive_columns(cur)
            _seed_roles(cur)
        logger.info("PostgreSQL database initialized (DATABASE_URL detected).")
    else:
        conn = _sqlite_conn()
        try:
            conn.executescript(_SQLITE_SCHEMA)
            conn.executescript(_SQLITE_IDENTITY_SCHEMA)
            conn.executescript(hiring_schema.SCHEMA_SQLITE)
            cur = conn.cursor()
            _apply_additive_columns(cur)
            _apply_hiring_additive_columns(cur)
            _seed_roles(cur)
            conn.commit()
            logger.info(
                "SQLite database initialized (no DATABASE_URL set — "
                "using local file at %s).",
                _SQLITE_PATH,
            )
        finally:
            conn.close()



# ── Durable background jobs ────────────────────────────────────────

def enqueue_job(
    job_type: str,
    payload: dict,
    *,
    max_attempts: int = 3,
    idempotency_key: Optional[str] = None,
) -> int:
    """Persist a job and return its ID.

    An idempotency key makes admission safe to retry after a lost HTTP
    response. The unique partial index guarantees this property across
    processes, not just within one worker.
    """
    if not job_type.strip():
        raise ValueError("job_type cannot be empty")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    p = _ph()
    serialized_payload = json.dumps(payload, separators=(",", ":"))
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"""INSERT INTO background_jobs
                    (job_type, payload, max_attempts, idempotency_key)
                    VALUES ({p}, {p}, {p}, {p})
                    ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                    DO NOTHING RETURNING id""",
                (job_type.strip(), serialized_payload, max_attempts, idempotency_key),
            )
            row = cur.fetchone()
            if row is not None:
                return int(row["id"])
        else:
            try:
                cur.execute(
                    f"""INSERT INTO background_jobs
                        (job_type, payload, max_attempts, idempotency_key)
                        VALUES ({p}, {p}, {p}, {p})""",
                    (job_type.strip(), serialized_payload, max_attempts, idempotency_key),
                )
                return int(cur.lastrowid)
            except _IntegrityError:
                if idempotency_key is None:
                    raise

        if idempotency_key is None:
            raise RuntimeError("Job insert did not return an ID")
        cur.execute(
            f"SELECT id FROM background_jobs WHERE idempotency_key = {p}",
            (idempotency_key,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Idempotent job lookup failed after insert conflict")
        return int(row["id"])


def get_job(job_id: int) -> Optional[dict]:
    """Return one durable job, including its decoded payload."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT * FROM background_jobs WHERE id = {p}", (job_id,))
        row = _row_to_dict(cur.fetchone())
    if row is None:
        return None
    row["payload"] = json.loads(row["payload"])
    return row


def get_job_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
    """Return the job associated with an idempotency key, if present."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM background_jobs WHERE idempotency_key = {p}",
            (idempotency_key,),
        )
        row = _row_to_dict(cur.fetchone())
    if row is None:
        return None
    row["payload"] = json.loads(row["payload"])
    return row


def claim_job(job_id: int, worker_id: str, *, lease_seconds: int = 300) -> Optional[dict]:
    """Claim one known job, including a previously expired lease."""
    if not worker_id.strip():
        raise ValueError("worker_id cannot be empty")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1")

    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = 'DEAD', updated_at = CURRENT_TIMESTAMP,
                        last_error = COALESCE(last_error, 'lease expired after max attempts')
                    WHERE id = {p} AND status = 'RUNNING'
                      AND locked_at <= CURRENT_TIMESTAMP - ({p} * INTERVAL '1 second')
                      AND attempts >= max_attempts""",
                (job_id, lease_seconds),
            )
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = 'RUNNING', attempts = attempts + 1,
                        locked_at = CURRENT_TIMESTAMP, locked_by = {p},
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = {p}
                      AND attempts < max_attempts
                      AND ((status = 'PENDING' AND available_at <= CURRENT_TIMESTAMP)
                        OR (status = 'RUNNING' AND locked_at <= CURRENT_TIMESTAMP - ({p} * INTERVAL '1 second')))
                    RETURNING *""",
                (worker_id.strip(), job_id, lease_seconds),
            )
            row = _row_to_dict(cur.fetchone())
        else:
            conn.execute("BEGIN IMMEDIATE")
            stale_after = f"-{lease_seconds} seconds"
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = 'DEAD', updated_at = datetime('now'),
                        last_error = COALESCE(last_error, 'lease expired after max attempts')
                    WHERE id = {p} AND status = 'RUNNING'
                      AND locked_at <= datetime('now', {p})
                      AND attempts >= max_attempts""",
                (job_id, stale_after),
            )
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = 'RUNNING', attempts = attempts + 1,
                        locked_at = datetime('now'), locked_by = {p},
                        updated_at = datetime('now')
                    WHERE id = {p}
                      AND attempts < max_attempts
                      AND ((status = 'PENDING' AND available_at <= datetime('now'))
                        OR (status = 'RUNNING' AND locked_at <= datetime('now', {p})))""",
                (worker_id.strip(), job_id, stale_after),
            )
            if cur.rowcount != 1:
                return None
            cur.execute(f"SELECT * FROM background_jobs WHERE id = {p}", (job_id,))
            row = _row_to_dict(cur.fetchone())

    if row is None:
        return None
    row["payload"] = json.loads(row["payload"])
    return row


def claim_next_job(worker_id: str, *, lease_seconds: int = 300) -> Optional[dict]:
    """Atomically claim the next ready job or reclaim an expired lease."""
    if not worker_id.strip():
        raise ValueError("worker_id cannot be empty")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1")

    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = 'DEAD', updated_at = CURRENT_TIMESTAMP,
                        last_error = COALESCE(last_error, 'lease expired after max attempts')
                    WHERE status = 'RUNNING'
                      AND locked_at <= CURRENT_TIMESTAMP - ({p} * INTERVAL '1 second')
                      AND attempts >= max_attempts""",
                (lease_seconds,),
            )
            cur.execute(
                f"""WITH candidate AS (
                    SELECT id FROM background_jobs
                    WHERE ((status = 'PENDING' AND available_at <= CURRENT_TIMESTAMP)
                       OR (status = 'RUNNING' AND locked_at <= CURRENT_TIMESTAMP - ({p} * INTERVAL '1 second')))
                      AND attempts < max_attempts
                    ORDER BY available_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE background_jobs AS job
                SET status = 'RUNNING', attempts = job.attempts + 1,
                    locked_at = CURRENT_TIMESTAMP, locked_by = {p},
                    updated_at = CURRENT_TIMESTAMP
                FROM candidate
                WHERE job.id = candidate.id
                RETURNING job.*""",
                (lease_seconds, worker_id.strip()),
            )
            row = _row_to_dict(cur.fetchone())
        else:
            conn.execute("BEGIN IMMEDIATE")
            stale_after = f"-{lease_seconds} seconds"
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = 'DEAD', updated_at = datetime('now'),
                        last_error = COALESCE(last_error, 'lease expired after max attempts')
                    WHERE status = 'RUNNING'
                      AND locked_at <= datetime('now', {p})
                      AND attempts >= max_attempts""",
                (stale_after,),
            )
            cur.execute(
                f"""SELECT id FROM background_jobs
                    WHERE ((status = 'PENDING' AND available_at <= datetime('now'))
                       OR (status = 'RUNNING' AND locked_at <= datetime('now', {p})))
                      AND attempts < max_attempts
                    ORDER BY available_at, id LIMIT 1""",
                (stale_after,),
            )
            candidate = cur.fetchone()
            if candidate is None:
                return None
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = 'RUNNING', attempts = attempts + 1,
                        locked_at = datetime('now'), locked_by = {p},
                        updated_at = datetime('now')
                    WHERE id = {p}""",
                (worker_id.strip(), candidate["id"]),
            )
            cur.execute(f"SELECT * FROM background_jobs WHERE id = {p}", (candidate["id"],))
            row = _row_to_dict(cur.fetchone())

    if row is None:
        return None
    row["payload"] = json.loads(row["payload"])
    return row


def complete_job(job_id: int, worker_id: str) -> bool:
    """Mark a job complete only when it is still owned by this worker."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"""UPDATE background_jobs
                SET status = 'COMPLETED', completed_at = {_now_sql()},
                    updated_at = {_now_sql()}, locked_at = NULL, locked_by = NULL
                WHERE id = {p} AND status = 'RUNNING' AND locked_by = {p}""",
            (job_id, worker_id),
        )
        return cur.rowcount == 1


def fail_job(
    job_id: int,
    worker_id: str,
    error: str,
    *,
    retry_delay_seconds: int = 60,
) -> Optional[str]:
    """Record a failure and either retry later or move the job to DEAD."""
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")

    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"""UPDATE background_jobs
                    SET status = CASE WHEN attempts >= max_attempts THEN 'DEAD' ELSE 'PENDING' END,
                        available_at = CURRENT_TIMESTAMP + ({p} * INTERVAL '1 second'),
                        last_error = {p}, updated_at = CURRENT_TIMESTAMP,
                        locked_at = NULL, locked_by = NULL
                    WHERE id = {p} AND status = 'RUNNING' AND locked_by = {p}
                    RETURNING status""",
                (retry_delay_seconds, error[:4000], job_id, worker_id),
            )
            row = cur.fetchone()
            return row["status"] if row else None

        cur.execute(
            f"""UPDATE background_jobs
                SET status = CASE WHEN attempts >= max_attempts THEN 'DEAD' ELSE 'PENDING' END,
                    available_at = datetime('now', {p}), last_error = {p},
                    updated_at = datetime('now'), locked_at = NULL, locked_by = NULL
                WHERE id = {p} AND status = 'RUNNING' AND locked_by = {p}""",
            (f"+{retry_delay_seconds} seconds", error[:4000], job_id, worker_id),
        )
        if cur.rowcount != 1:
            return None
        cur.execute(f"SELECT status FROM background_jobs WHERE id = {p}", (job_id,))
        row = cur.fetchone()
        return row["status"] if row else None


# ── Evaluation CRUD ────────────────────────────────────────────────

def create_evaluation(
    resume_text: str,
    role: str,
    candidate_name: str = "",
    org_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
) -> int:
    """Create a new evaluation and return its ID.

    org_id and owner_user_id are nullable to preserve the pre-identity
    behaviour: an unauthenticated caller still gets a working evaluation, it is
    simply unowned. Unowned rows are excluded from tenant-scoped listings
    rather than being attributed to an arbitrary organization.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
                f"VALUES ({p}, {p}, {p}, {p}, {p}) RETURNING id",
                (candidate_name, resume_text, role, org_id, owner_user_id),
            )
            eval_id = cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role, org_id, owner_user_id) "
                f"VALUES ({p}, {p}, {p}, {p}, {p})",
                (candidate_name, resume_text, role, org_id, owner_user_id),
            )
            eval_id = cur.lastrowid
    logger.info("Created evaluation %s for role '%s' (org=%s)", eval_id, role, org_id)
    return eval_id



def get_evaluation(eval_id: int) -> Optional[dict]:
    """Get a single evaluation by ID, including resume_text.

    Internal use only (e.g. loading agent context) — never return this
    directly from a public list/detail endpoint. Use get_evaluation_public
    for anything client-facing.
    """
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT * FROM evaluations WHERE id = {p}", (eval_id,))
        row = cur.fetchone()
        return _row_to_dict(row)


def get_evaluation_public(eval_id: int) -> Optional[dict]:
    """Get a single evaluation by ID, projected to exclude resume_text."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT {_EVALUATION_SUMMARY_COLUMNS} FROM evaluations WHERE id = {p}",
            (eval_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row)


def list_evaluations(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List evaluations with optional status filter (excludes resume_text)."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if status:
            cur.execute(
                f"SELECT {_EVALUATION_SUMMARY_COLUMNS} FROM evaluations WHERE status = {p} "
                f"ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
                (status, limit, offset),
            )
        else:
            cur.execute(
                f"SELECT {_EVALUATION_SUMMARY_COLUMNS} FROM evaluations "
                f"ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
                (limit, offset),
            )
        rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]


def count_evaluations(status: Optional[str] = None) -> int:
    """Count total evaluations."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if status:
            cur.execute(
                f"SELECT COUNT(*) as c FROM evaluations WHERE status = {p}",
                (status,),
            )
        else:
            cur.execute("SELECT COUNT(*) as c FROM evaluations")
        row = cur.fetchone()
        if USE_POSTGRES:
            return row["c"]
        return row["c"]


def update_evaluation(eval_id: int, **kwargs) -> None:
    """Update evaluation fields."""
    allowed = {"status", "current_round", "overall_score", "final_decision", "candidate_name"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    p = _ph()
    set_clause = ", ".join(f"{k} = {p}" for k in fields)
    values = list(fields.values()) + [eval_id]
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE evaluations SET {set_clause} WHERE id = {p}",
            values,
        )


# ── Agent Verdicts ─────────────────────────────────────────────────

def save_verdict(
    evaluation_id: int,
    agent_type: str,
    round_number: int,
    verdict_json: dict,
    verdict_text: str = "",
    score: Optional[float] = None,
    decision: Optional[str] = None,
    confidence: Optional[float] = None,
) -> int:
    """Save an agent verdict.

    Raises DuplicateVerdictError if a canonical verdict already exists for
    this evaluation/round (see uq_verdicts_canonical in the schema).
    """
    p = _ph()
    try:
        with _get_conn() as (conn, cur):
            if USE_POSTGRES:
                cur.execute(
                    f"""INSERT INTO agent_verdicts
                       (evaluation_id, agent_type, round_number, verdict_json,
                        verdict_text, score, decision, confidence)
                       VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
                       RETURNING id""",
                    (
                        evaluation_id, agent_type, round_number,
                        json.dumps(verdict_json), verdict_text,
                        score, decision, confidence,
                    ),
                )
                return cur.fetchone()["id"]
            else:
                cur.execute(
                    f"""INSERT INTO agent_verdicts
                       (evaluation_id, agent_type, round_number, verdict_json,
                        verdict_text, score, decision, confidence)
                       VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})""",
                    (
                        evaluation_id, agent_type, round_number,
                        json.dumps(verdict_json), verdict_text,
                        score, decision, confidence,
                    ),
                )
                return cur.lastrowid
    except _IntegrityError as e:
        raise DuplicateVerdictError(
            f"A canonical verdict already exists for evaluation {evaluation_id} round {round_number}"
        ) from e


def get_verdicts(evaluation_id: int) -> list[dict]:
    """Get all verdicts for an evaluation, ordered by round (includes failed/INVALID_OUTPUT rows for audit)."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM agent_verdicts WHERE evaluation_id = {p} ORDER BY round_number, id",
            (evaluation_id,),
        )
        result = []
        for r in cur.fetchall():
            d = _row_to_dict(r)
            d["verdict_json"] = json.loads(d["verdict_json"])
            result.append(d)
        return result


def get_verdict_summaries(evaluation_ids: list[int]) -> dict[int, list[dict]]:
    """Batch-fetch lightweight verdict summaries for multiple evaluations.

    Replaces one query per evaluation (N+1) with a single IN-list query.
    """
    if not evaluation_ids:
        return {}
    p = _ph()
    placeholders = ", ".join([p] * len(evaluation_ids))
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT evaluation_id, agent_type, round_number, decision, score "
            f"FROM agent_verdicts WHERE evaluation_id IN ({placeholders}) "
            f"ORDER BY evaluation_id, round_number, id",
            tuple(evaluation_ids),
        )
        rows = [_row_to_dict(r) for r in cur.fetchall()]
    grouped: dict[int, list[dict]] = {eid: [] for eid in evaluation_ids}
    for r in rows:
        grouped.setdefault(r["evaluation_id"], []).append(r)
    return grouped


def get_verdict_by_round(evaluation_id: int, round_number: int) -> Optional[dict]:
    """Get the canonical (non-INVALID_OUTPUT) verdict for a specific round, if any."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM agent_verdicts WHERE evaluation_id = {p} AND round_number = {p} "
            f"AND decision <> 'INVALID_OUTPUT' ORDER BY id DESC LIMIT 1",
            (evaluation_id, round_number),
        )
        row = cur.fetchone()
        if row:
            d = _row_to_dict(row)
            d["verdict_json"] = json.loads(d["verdict_json"])
            return d
        return None


# ── Questions & Answers ────────────────────────────────────────────

def save_questions(evaluation_id: int, round_number: int, questions_text: str) -> int:
    """Save interview questions for a round."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO interview_questions (evaluation_id, round_number, questions_text) "
                f"VALUES ({p}, {p}, {p}) RETURNING id",
                (evaluation_id, round_number, questions_text),
            )
            return cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO interview_questions (evaluation_id, round_number, questions_text) "
                f"VALUES ({p}, {p}, {p})",
                (evaluation_id, round_number, questions_text),
            )
            return cur.lastrowid


def get_questions(evaluation_id: int, round_number: int) -> Optional[str]:
    """Get questions for a specific round."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT questions_text FROM interview_questions "
            f"WHERE evaluation_id = {p} AND round_number = {p}",
            (evaluation_id, round_number),
        )
        row = cur.fetchone()
        if row is None:
            return None
        if USE_POSTGRES:
            return row["questions_text"]
        return row["questions_text"]


def save_answer(evaluation_id: int, round_number: int, answer_text: str) -> int:
    """Save candidate answer for a round."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO interview_answers (evaluation_id, round_number, answer_text) "
                f"VALUES ({p}, {p}, {p}) RETURNING id",
                (evaluation_id, round_number, answer_text),
            )
            return cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO interview_answers (evaluation_id, round_number, answer_text) "
                f"VALUES ({p}, {p}, {p})",
                (evaluation_id, round_number, answer_text),
            )
            return cur.lastrowid


def get_answer(evaluation_id: int, round_number: int) -> Optional[str]:
    """Get answer for a specific round."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT answer_text FROM interview_answers "
            f"WHERE evaluation_id = {p} AND round_number = {p}",
            (evaluation_id, round_number),
        )
        row = cur.fetchone()
        if row is None:
            return None
        if USE_POSTGRES:
            return row["answer_text"]
        return row["answer_text"]


# ── Dashboard Stats ────────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    """Get aggregated statistics for the dashboard."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute("SELECT COUNT(*) as c FROM evaluations")
        total = cur.fetchone()["c"]

        cur.execute(f"SELECT COUNT(*) as c FROM evaluations WHERE status = {p}", ("COMPLETE",))
        completed = cur.fetchone()["c"]

        cur.execute(f"SELECT COUNT(*) as c FROM evaluations WHERE status = {p}", ("IN_PROGRESS",))
        in_progress = cur.fetchone()["c"]

        cur.execute(f"SELECT COUNT(*) as c FROM evaluations WHERE status = {p}", ("REJECTED",))
        rejected = cur.fetchone()["c"]

        cur.execute(f"SELECT COUNT(*) as c FROM evaluations WHERE final_decision = {p}", ("HIRE",))
        hired = cur.fetchone()["c"]

        cur.execute(
            "SELECT AVG(overall_score) as avg FROM evaluations WHERE overall_score IS NOT NULL"
        )
        avg_score = cur.fetchone()["avg"]

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "rejected": rejected,
        "hired": hired,
        "hire_rate": round(hired / completed * 100, 1) if completed > 0 else 0,
        "avg_score": round(avg_score, 1) if avg_score else 0,
    }


# ── Identity: users ────────────────────────────────────────────────

class DuplicateEmailError(Exception):
    """Raised when registering an email that already exists."""


def normalize_email(email: str) -> str:
    """Casefold and trim for uniqueness comparison.

    Deliberately does NOT strip dots or plus-addressing: those are
    provider-specific conventions, and treating `a.b@gmail.com` and
    `ab@gmail.com` as the same identity is wrong for most other providers.
    """
    return email.strip().casefold()


_USER_PUBLIC_COLUMNS = (
    "id, email, full_name, is_platform_admin, status, "
    "email_verified_at, last_login_at, created_at, updated_at"
)


def create_user(
    email: str,
    password_hash: str,
    full_name: str = "",
    is_platform_admin: bool = False,
) -> int:
    """Create a user. Raises DuplicateEmailError if the email is taken."""
    p = _ph()
    normalized = normalize_email(email)
    admin_flag = True if is_platform_admin else False
    if not USE_POSTGRES:
        admin_flag = 1 if is_platform_admin else 0
    try:
        with _get_conn() as (conn, cur):
            if USE_POSTGRES:
                cur.execute(
                    f"INSERT INTO users (email, email_normalized, password_hash, "
                    f"full_name, is_platform_admin) VALUES ({p}, {p}, {p}, {p}, {p}) "
                    f"RETURNING id",
                    (email.strip(), normalized, password_hash, full_name.strip(), admin_flag),
                )
                return cur.fetchone()["id"]
            cur.execute(
                f"INSERT INTO users (email, email_normalized, password_hash, "
                f"full_name, is_platform_admin) VALUES ({p}, {p}, {p}, {p}, {p})",
                (email.strip(), normalized, password_hash, full_name.strip(), admin_flag),
            )
            return cur.lastrowid
    except _IntegrityError as exc:
        raise DuplicateEmailError(f"An account already exists for {email}.") from exc


def get_user_by_email(email: str) -> Optional[dict]:
    """Full user row including password_hash. Authentication use only."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM users WHERE email_normalized = {p} AND deleted_at IS NULL",
            (normalize_email(email),),
        )
        return _row_to_dict(cur.fetchone())


def get_user(user_id: int) -> Optional[dict]:
    """User row without the password hash."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT {_USER_PUBLIC_COLUMNS} FROM users "
            f"WHERE id = {p} AND deleted_at IS NULL",
            (user_id,),
        )
        return _row_to_dict(cur.fetchone())


def touch_user_login(user_id: int) -> None:
    p = _ph()
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as (conn, cur):
        cur.execute(f"UPDATE users SET last_login_at = {p} WHERE id = {p}", (now, user_id))


# ── Identity: organizations & membership ───────────────────────────

class DuplicateSlugError(Exception):
    """Raised when an organization slug is already taken."""


def create_organization(name: str, slug: str, plan: str = "trial") -> int:
    p = _ph()
    try:
        with _get_conn() as (conn, cur):
            if USE_POSTGRES:
                cur.execute(
                    f"INSERT INTO organizations (name, slug, plan) "
                    f"VALUES ({p}, {p}, {p}) RETURNING id",
                    (name.strip(), slug.strip().casefold(), plan),
                )
                return cur.fetchone()["id"]
            cur.execute(
                f"INSERT INTO organizations (name, slug, plan) VALUES ({p}, {p}, {p})",
                (name.strip(), slug.strip().casefold(), plan),
            )
            return cur.lastrowid
    except _IntegrityError as exc:
        raise DuplicateSlugError(f"An organization already uses the slug '{slug}'.") from exc


def get_organization(org_id: int) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM organizations WHERE id = {p} AND deleted_at IS NULL",
            (org_id,),
        )
        return _row_to_dict(cur.fetchone())


def get_role_by_name(name: str) -> Optional[dict]:
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT * FROM roles WHERE name = {p}", (name,))
        return _row_to_dict(cur.fetchone())


def list_organizations(limit: int = 50, offset: int = 0) -> dict:
    """Cross-tenant organization listing. Platform-admin surfaces only."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute("SELECT COUNT(*) AS c FROM organizations WHERE deleted_at IS NULL")
        total = cur.fetchone()["c"]
        cur.execute(
            f"SELECT id, name, slug, plan, status, created_at FROM organizations "
            f"WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT {p} OFFSET {p}",
            (limit, offset),
        )
        return {
            "organizations": [_row_to_dict(r) for r in cur.fetchall()],
            "total": total,
            "limit": limit,
            "offset": offset,
        }



def create_membership(org_id: int, user_id: int, role_name: str) -> int:
    """Attach a user to an organization with a role."""
    role = get_role_by_name(role_name)
    if role is None:
        raise ValueError(f"Unknown role: {role_name}")
    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO org_memberships (org_id, user_id, role_id) "
                f"VALUES ({p}, {p}, {p}) RETURNING id",
                (org_id, user_id, role["id"]),
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO org_memberships (org_id, user_id, role_id) VALUES ({p}, {p}, {p})",
            (org_id, user_id, role["id"]),
        )
        return cur.lastrowid


def get_membership(user_id: int, org_id: int) -> Optional[dict]:
    """Active membership joining the role name, or None."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT m.id, m.org_id, m.user_id, m.status, r.name AS role_name "
            f"FROM org_memberships m JOIN roles r ON r.id = m.role_id "
            f"WHERE m.user_id = {p} AND m.org_id = {p} "
            f"AND m.deleted_at IS NULL AND m.status = 'ACTIVE'",
            (user_id, org_id),
        )
        return _row_to_dict(cur.fetchone())


def list_memberships(user_id: int) -> list[dict]:
    """All active memberships for a user, with org and role names."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT m.id, m.org_id, m.status, r.name AS role_name, "
            f"o.name AS org_name, o.slug AS org_slug "
            f"FROM org_memberships m "
            f"JOIN roles r ON r.id = m.role_id "
            f"JOIN organizations o ON o.id = m.org_id "
            f"WHERE m.user_id = {p} AND m.deleted_at IS NULL "
            f"AND m.status = 'ACTIVE' AND o.deleted_at IS NULL "
            f"ORDER BY o.name",
            (user_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def list_org_members(org_id: int) -> list[dict]:
    """All active members of an organization."""
    p = _ph()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT m.id, m.user_id, m.status, r.name AS role_name, "
            f"u.email, u.full_name "
            f"FROM org_memberships m "
            f"JOIN roles r ON r.id = m.role_id "
            f"JOIN users u ON u.id = m.user_id "
            f"WHERE m.org_id = {p} AND m.deleted_at IS NULL "
            f"AND m.status = 'ACTIVE' AND u.deleted_at IS NULL "
            f"ORDER BY u.full_name, u.email",
            (org_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def set_membership_role(org_id: int, user_id: int, role_name: str) -> bool:
    """Change a member's role. Returns False if no active membership exists."""
    role = get_role_by_name(role_name)
    if role is None:
        raise ValueError(f"Unknown role: {role_name}")
    p = _ph()
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE org_memberships SET role_id = {p}, updated_at = {p} "
            f"WHERE org_id = {p} AND user_id = {p} AND deleted_at IS NULL",
            (role["id"], now, org_id, user_id),
        )
        return cur.rowcount > 0


def remove_membership(org_id: int, user_id: int) -> bool:
    """Soft-delete a membership, preserving the audit trail."""
    p = _ph()
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE org_memberships SET deleted_at = {p}, status = 'REMOVED' "
            f"WHERE org_id = {p} AND user_id = {p} AND deleted_at IS NULL",
            (now, org_id, user_id),
        )
        return cur.rowcount > 0


# ── Audit trail ────────────────────────────────────────────────────

def get_last_audit_hash() -> Optional[str]:
    """Most recent event hash, for chaining the next one."""
    with _get_conn() as (conn, cur):
        cur.execute("SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return row["hash"] if row else None


def insert_audit_event(event: dict) -> int:
    """Append one audit event. Caller supplies prev_hash and hash."""
    p = _ph()
    columns = (
        "tier", "action", "actor_user_id", "actor_org_id", "actor_role",
        "actor_ip", "impersonated_by", "resource_type", "resource_id",
        "resource_org_id", "outcome", "detail", "request_id", "prev_hash", "hash",
    )
    values = tuple(event.get(c) for c in columns)
    placeholders = ", ".join([p] * len(columns))
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO audit_events ({', '.join(columns)}) "
                f"VALUES ({placeholders}) RETURNING id",
                values,
            )
            return cur.fetchone()["id"]
        cur.execute(
            f"INSERT INTO audit_events ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        return cur.lastrowid


def list_audit_events(
    org_id: Optional[int] = None,
    actor_user_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Query the audit log. org_id scopes to one tenant; None means platform-wide."""
    p = _ph()
    clauses, params = [], []
    if org_id is not None:
        clauses.append(f"(actor_org_id = {p} OR resource_org_id = {p})")
        params.extend([org_id, org_id])
    if actor_user_id is not None:
        clauses.append(f"actor_user_id = {p}")
        params.append(actor_user_id)
    if action is not None:
        clauses.append(f"action = {p}")
        params.append(action)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    with _get_conn() as (conn, cur):
        cur.execute(
            f"SELECT * FROM audit_events {where} "
            f"ORDER BY id DESC LIMIT {p} OFFSET {p}",
            tuple(params),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]


def verify_audit_chain(limit: int = 1000) -> dict:
    """Walk the hash chain and report the first break, if any.

    Detects silent edits and deletions. Does not protect against an attacker
    who can rewrite every subsequent row — see docs/SECURITY.md.
    """
    from audit import compute_event_hash

    with _get_conn() as (conn, cur):
        cur.execute(f"SELECT * FROM audit_events ORDER BY id ASC LIMIT {_ph()}", (limit,))
        rows = [_row_to_dict(r) for r in cur.fetchall()]

    expected_prev = None
    for row in rows:
        if row["prev_hash"] != expected_prev:
            return {"valid": False, "broken_at_id": row["id"], "reason": "prev_hash mismatch"}
        if compute_event_hash(row, row["prev_hash"]) != row["hash"]:
            return {"valid": False, "broken_at_id": row["id"], "reason": "content hash mismatch"}
        expected_prev = row["hash"]

    return {"valid": True, "events_checked": len(rows)}

