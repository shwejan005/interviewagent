"""Persistent user-scoped notification inbox schema."""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS user_notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    href TEXT NOT NULL DEFAULT '/notifications',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_user_notifications_unread
    ON user_notifications(user_id, read_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_org
    ON user_notifications(org_id, created_at DESC);
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS user_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    href TEXT NOT NULL DEFAULT '/notifications',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_notifications_unread
    ON user_notifications(user_id, read_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_org
    ON user_notifications(org_id, created_at DESC);
"""
