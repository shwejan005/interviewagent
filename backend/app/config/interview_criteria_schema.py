"""DDL for per-posting evaluation criteria and generated application reports."""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS posting_evaluation_criteria (
    posting_id INTEGER PRIMARY KEY REFERENCES job_postings(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    competencies_json TEXT NOT NULL DEFAULT '[]',
    custom_questions_json TEXT NOT NULL DEFAULT '[]',
    pass_threshold DOUBLE PRECISION NOT NULL DEFAULT 6.0,
    interview_settings_json TEXT NOT NULL DEFAULT '{}',
    rubric_version TEXT NOT NULL DEFAULT 'posting-v1',
    updated_by INTEGER REFERENCES users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS application_interview_reports (
    application_id INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    posting_id INTEGER NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    competency_scores_json TEXT NOT NULL DEFAULT '[]',
    overall_weighted_score DOUBLE PRECISION,
    recommendation TEXT NOT NULL DEFAULT '',
    rubric_version TEXT NOT NULL DEFAULT 'posting-v1',
    interview_details_json TEXT NOT NULL DEFAULT '{}',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reports_org ON application_interview_reports(org_id, generated_at);
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS posting_evaluation_criteria (
    posting_id INTEGER PRIMARY KEY REFERENCES job_postings(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    competencies_json TEXT NOT NULL DEFAULT '[]',
    custom_questions_json TEXT NOT NULL DEFAULT '[]',
    pass_threshold REAL NOT NULL DEFAULT 6.0,
    interview_settings_json TEXT NOT NULL DEFAULT '{}',
    rubric_version TEXT NOT NULL DEFAULT 'posting-v1',
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS application_interview_reports (
    application_id INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
    evaluation_id INTEGER NOT NULL REFERENCES evaluations(id) ON DELETE CASCADE,
    posting_id INTEGER NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    competency_scores_json TEXT NOT NULL DEFAULT '[]',
    overall_weighted_score REAL,
    recommendation TEXT NOT NULL DEFAULT '',
    rubric_version TEXT NOT NULL DEFAULT 'posting-v1',
    interview_details_json TEXT NOT NULL DEFAULT '{}',
    generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reports_org ON application_interview_reports(org_id, generated_at);
"""
