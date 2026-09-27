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
"""


# ── Initialization ──────────────────────────────────────────────────

def init_db() -> None:
    """Initialize database schema. Safe to call multiple times."""
    if USE_POSTGRES:
        with _get_conn() as (conn, cur):
            cur.execute(_PG_SCHEMA)
        logger.info("PostgreSQL database initialized (DATABASE_URL detected).")
    else:
        conn = _sqlite_conn()
        try:
            conn.executescript(_SQLITE_SCHEMA)
            conn.commit()
            logger.info(
                "SQLite database initialized (no DATABASE_URL set — "
                "using local file at %s).",
                _SQLITE_PATH,
            )
        finally:
            conn.close()


# ── Evaluation CRUD ────────────────────────────────────────────────

def create_evaluation(resume_text: str, role: str, candidate_name: str = "") -> int:
    """Create a new evaluation and return its ID."""
    p = _ph()
    with _get_conn() as (conn, cur):
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role) "
                f"VALUES ({p}, {p}, {p}) RETURNING id",
                (candidate_name, resume_text, role),
            )
            eval_id = cur.fetchone()["id"]
        else:
            cur.execute(
                f"INSERT INTO evaluations (candidate_name, resume_text, role) "
                f"VALUES ({p}, {p}, {p})",
                (candidate_name, resume_text, role),
            )
            eval_id = cur.lastrowid
    logger.info("Created evaluation %s for role '%s'", eval_id, role)
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
