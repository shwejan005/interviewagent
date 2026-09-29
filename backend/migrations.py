"""Small, reviewable schema migrations shared by SQLite and PostgreSQL."""

from collections.abc import Callable
from typing import Any


Migration = Callable[[Any, bool], None]


def _existing_columns(cur, table: str, use_postgres: bool) -> set[str]:
    if use_postgres:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {row["column_name"] for row in cur.fetchall()}
    cur.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cur.fetchall()}


def _add_columns(cur, table: str, columns: tuple[tuple[str, str, str], ...], use_postgres: bool) -> None:
    present = _existing_columns(cur, table, use_postgres)
    for name, postgres_type, sqlite_type in columns:
        if name not in present:
            column_type = postgres_type if use_postgres else sqlite_type
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def _migration_001_baseline(cur, use_postgres: bool) -> None:
    """Mark databases created before the ledger as the initial schema."""


def _migration_002_execution_metadata(cur, use_postgres: bool) -> None:
    _add_columns(
        cur,
        "agent_verdicts",
        (
            ("attempt_id", "TEXT", "TEXT"),
            ("model_name", "TEXT", "TEXT"),
            ("prompt_version", "TEXT", "TEXT"),
            ("rubric_version", "TEXT", "TEXT"),
            ("usage_json", "TEXT", "TEXT"),
            ("error_type", "TEXT", "TEXT"),
            ("started_at", "TIMESTAMPTZ", "TEXT"),
            ("completed_at", "TIMESTAMPTZ", "TEXT"),
            ("deployment_provenance", "TEXT", "TEXT"),
        ),
        use_postgres,
    )
    _add_columns(
        cur,
        "background_jobs",
        (
            ("tenant_key", "TEXT", "TEXT"),
            ("cancellation_requested", "BOOLEAN NOT NULL DEFAULT FALSE", "INTEGER NOT NULL DEFAULT 0"),
        ),
        use_postgres,
    )


def _migration_003_cancellable_jobs(cur, use_postgres: bool) -> None:
    if use_postgres:
        cur.execute(
            """DO $$
            DECLARE constraint_name TEXT;
            BEGIN
                FOR constraint_name IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'background_jobs'::regclass
                      AND contype = 'c'
                      AND pg_get_constraintdef(oid) ILIKE '%status%'
                      AND pg_get_constraintdef(oid) ILIKE '%DEAD%'
                LOOP
                    EXECUTE format(
                        'ALTER TABLE background_jobs DROP CONSTRAINT %I',
                        constraint_name
                    );
                END LOOP;
            END $$;"""
        )
        cur.execute(
            "ALTER TABLE background_jobs ADD CONSTRAINT background_jobs_status_check "
            "CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'DEAD', 'CANCELLED'))"
        )
        return

    cur.execute(
        """CREATE TABLE background_jobs_migrated (
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
            tenant_key TEXT,
            cancellation_requested INTEGER NOT NULL DEFAULT 0,
            CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'DEAD', 'CANCELLED')),
            CHECK (attempts >= 0 AND max_attempts > 0)
        )"""
    )
    cur.execute(
        """INSERT INTO background_jobs_migrated
            (id, job_type, payload, status, attempts, max_attempts, available_at,
             locked_at, locked_by, last_error, created_at, updated_at, completed_at,
             idempotency_key, tenant_key, cancellation_requested)
            SELECT id, job_type, payload, status, attempts, max_attempts, available_at,
                   locked_at, locked_by, last_error, created_at, updated_at, completed_at,
                   idempotency_key, tenant_key, cancellation_requested
            FROM background_jobs"""
    )
    cur.execute("DROP TABLE background_jobs")
    cur.execute("ALTER TABLE background_jobs_migrated RENAME TO background_jobs")
    cur.execute(
        "CREATE INDEX idx_background_jobs_claim ON background_jobs(status, available_at, id)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX uq_background_jobs_idempotency "
        "ON background_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL"
    )


MIGRATIONS: tuple[tuple[int, Migration], ...] = (
    (1, _migration_001_baseline),
    (2, _migration_002_execution_metadata),
    (3, _migration_003_cancellable_jobs),
)


def apply_migrations(cur, *, use_postgres: bool) -> int:
    """Apply each unapplied migration exactly once and return its version."""
    placeholder = "%s" if use_postgres else "?"
    cur.execute("SELECT version FROM schema_migrations ORDER BY version")
    applied = {int(row["version"]) for row in cur.fetchall()}

    for version, migration in MIGRATIONS:
        if version in applied:
            continue
        migration(cur, use_postgres)
        cur.execute(
            f"INSERT INTO schema_migrations (version) VALUES ({placeholder})",
            (version,),
        )

    return MIGRATIONS[-1][0]