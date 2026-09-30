"""DDL for the candidate resume vault (extracted text + parse audit trail).

Only extracted text is persisted, never the raw file bytes: this keeps the
storage surface identical to the existing `candidate_profiles.resume_text`
column and avoids taking on an object-storage dependency for something that
is not needed yet (see docs/GAP_ANALYSIS.md for that boundary).
"""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS resume_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    parsed_by TEXT NOT NULL DEFAULT 'heuristic',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_resume_documents_user ON resume_documents(user_id, created_at);
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS resume_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    parsed_by TEXT NOT NULL DEFAULT 'heuristic',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_resume_documents_user ON resume_documents(user_id, created_at);
"""
