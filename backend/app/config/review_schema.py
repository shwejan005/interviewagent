"""Schema for reviewer actions, rubric versions, and benchmark cases."""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS rubric_versions (
    id SERIAL PRIMARY KEY,
    role TEXT NOT NULL,
    version TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (role, version)
);

CREATE TABLE IF NOT EXISTS review_actions (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    actor_user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL CHECK (action IN ('APPROVE', 'CORRECT', 'ESCALATE')),
    note TEXT NOT NULL DEFAULT '',
    correction_json TEXT NOT NULL DEFAULT '{}',
    rubric_version TEXT NOT NULL DEFAULT 'backend-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS benchmark_cases (
    case_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    input_json TEXT NOT NULL,
    expected_rules_json TEXT NOT NULL DEFAULT '[]',
    split TEXT NOT NULL DEFAULT 'development',
    provenance TEXT NOT NULL DEFAULT 'synthetic',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES benchmark_cases(case_id),
    harness_version TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    report_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_review_actions_evaluation ON review_actions(evaluation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_case ON benchmark_runs(case_id, created_at);
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS rubric_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    version TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (role, version)
);

CREATE TABLE IF NOT EXISTS review_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    actor_user_id INTEGER NOT NULL REFERENCES users(id),
    action TEXT NOT NULL CHECK (action IN ('APPROVE', 'CORRECT', 'ESCALATE')),
    note TEXT NOT NULL DEFAULT '',
    correction_json TEXT NOT NULL DEFAULT '{}',
    rubric_version TEXT NOT NULL DEFAULT 'backend-v1',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS benchmark_cases (
    case_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    input_json TEXT NOT NULL,
    expected_rules_json TEXT NOT NULL DEFAULT '[]',
    split TEXT NOT NULL DEFAULT 'development',
    provenance TEXT NOT NULL DEFAULT 'synthetic',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES benchmark_cases(case_id),
    harness_version TEXT NOT NULL,
    passed INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_review_actions_evaluation ON review_actions(evaluation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_case ON benchmark_runs(case_id, created_at);
"""
