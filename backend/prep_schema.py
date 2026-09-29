"""Schema for the safe, text-first interview preparation domain."""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS prep_topics (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'FOUNDATION',
    prerequisites TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prep_problems (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES prep_topics(id) ON DELETE CASCADE,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    difficulty TEXT NOT NULL DEFAULT 'EASY',
    estimated_minutes INTEGER NOT NULL DEFAULT 30,
    expected_concepts TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prep_roadmaps (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    target_role TEXT NOT NULL,
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prep_roadmap_nodes (
    id SERIAL PRIMARY KEY,
    roadmap_id INTEGER NOT NULL REFERENCES prep_roadmaps(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES prep_topics(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'TODO',
    completed_at TIMESTAMPTZ,
    UNIQUE (roadmap_id, topic_id),
    UNIQUE (roadmap_id, position)
);

CREATE TABLE IF NOT EXISTS prep_submissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id INTEGER NOT NULL REFERENCES prep_problems(id) ON DELETE CASCADE,
    answer_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SUBMITTED',
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    reviewer_note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prep_gamification (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    xp INTEGER NOT NULL DEFAULT 0,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_activity_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prep_xp_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    points INTEGER NOT NULL,
    reference_type TEXT,
    reference_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prep_problems_topic ON prep_problems(topic_id);
CREATE INDEX IF NOT EXISTS idx_prep_roadmaps_user ON prep_roadmaps(user_id);
CREATE INDEX IF NOT EXISTS idx_prep_nodes_roadmap ON prep_roadmap_nodes(roadmap_id, position);
CREATE INDEX IF NOT EXISTS idx_prep_submissions_user ON prep_submissions(user_id, created_at);
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS prep_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'FOUNDATION',
    prerequisites TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prep_problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES prep_topics(id) ON DELETE CASCADE,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    difficulty TEXT NOT NULL DEFAULT 'EASY',
    estimated_minutes INTEGER NOT NULL DEFAULT 30,
    expected_concepts TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prep_roadmaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    target_role TEXT NOT NULL,
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prep_roadmap_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roadmap_id INTEGER NOT NULL REFERENCES prep_roadmaps(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES prep_topics(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'TODO',
    completed_at TEXT,
    UNIQUE (roadmap_id, topic_id),
    UNIQUE (roadmap_id, position)
);

CREATE TABLE IF NOT EXISTS prep_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    problem_id INTEGER NOT NULL REFERENCES prep_problems(id) ON DELETE CASCADE,
    answer_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SUBMITTED',
    verified INTEGER NOT NULL DEFAULT 0,
    reviewer_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prep_gamification (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    xp INTEGER NOT NULL DEFAULT 0,
    streak_days INTEGER NOT NULL DEFAULT 0,
    last_activity_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prep_xp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    points INTEGER NOT NULL,
    reference_type TEXT,
    reference_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_prep_problems_topic ON prep_problems(topic_id);
CREATE INDEX IF NOT EXISTS idx_prep_roadmaps_user ON prep_roadmaps(user_id);
CREATE INDEX IF NOT EXISTS idx_prep_nodes_roadmap ON prep_roadmap_nodes(roadmap_id, position);
CREATE INDEX IF NOT EXISTS idx_prep_submissions_user ON prep_submissions(user_id, created_at);
"""
