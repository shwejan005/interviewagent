"""Durable application-linked AI interview state and turn history."""

SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS application_ai_interviews (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    evaluation_id INTEGER REFERENCES evaluations(id) ON DELETE SET NULL,
    rubric_version TEXT NOT NULL,
    policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    screening_input_json TEXT NOT NULL DEFAULT '{}',
    screening_result_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'SCREENING_QUEUED',
    phase TEXT NOT NULL DEFAULT 'SCREENING',
    technical_questions_json TEXT NOT NULL DEFAULT '[]',
    behavioral_questions_json TEXT NOT NULL DEFAULT '[]',
    current_question_id INTEGER,
    next_turn_sequence INTEGER NOT NULL DEFAULT 1,
    phase_question_index INTEGER NOT NULL DEFAULT 0,
    follow_ups_for_question INTEGER NOT NULL DEFAULT 0,
    consent_version TEXT,
    consent_at TIMESTAMPTZ,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (application_id, attempt_no),
    CHECK (attempt_no > 0),
    CHECK (phase IN ('SCREENING', 'TECHNICAL', 'BEHAVIORAL', 'COMPLETE')),
    CHECK (phase_question_index >= 0),
    CHECK (next_turn_sequence > 0),
    CHECK (follow_ups_for_question >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_application_ai_interview_active
    ON application_ai_interviews(application_id)
    WHERE status NOT IN ('CANCELLED', 'EXPIRED');
CREATE INDEX IF NOT EXISTS idx_application_ai_interviews_org_status
    ON application_ai_interviews(org_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_application_ai_interviews_candidate
    ON application_ai_interviews(candidate_user_id, status, updated_at);

CREATE TABLE IF NOT EXISTS application_ai_interview_turns (
    id SERIAL PRIMARY KEY,
    interview_id INTEGER NOT NULL REFERENCES application_ai_interviews(id) ON DELETE CASCADE,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    phase TEXT NOT NULL,
    question_type TEXT NOT NULL DEFAULT 'CORE',
    competency_key TEXT NOT NULL DEFAULT '',
    difficulty INTEGER NOT NULL DEFAULT 2,
    question_text TEXT NOT NULL,
    answer_text TEXT,
    state TEXT NOT NULL DEFAULT 'ASKED',
    assessment_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    answered_at TIMESTAMPTZ,
    UNIQUE (interview_id, sequence_no),
    CHECK (sequence_no > 0),
    CHECK (phase IN ('TECHNICAL', 'BEHAVIORAL')),
    CHECK (question_type IN ('CORE', 'FOLLOW_UP')),
    CHECK (difficulty BETWEEN 1 AND 3),
    CHECK (state IN ('ASKED', 'ANSWER_QUEUED', 'ASSESSED'))
);
CREATE INDEX IF NOT EXISTS idx_ai_interview_turns_app_sequence
    ON application_ai_interview_turns(application_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_ai_interview_turns_run_sequence
    ON application_ai_interview_turns(interview_id, sequence_no);
"""

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS application_ai_interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    evaluation_id INTEGER REFERENCES evaluations(id) ON DELETE SET NULL,
    rubric_version TEXT NOT NULL,
    policy_snapshot_json TEXT NOT NULL DEFAULT '{}',
    screening_input_json TEXT NOT NULL DEFAULT '{}',
    screening_result_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'SCREENING_QUEUED',
    phase TEXT NOT NULL DEFAULT 'SCREENING',
    technical_questions_json TEXT NOT NULL DEFAULT '[]',
    behavioral_questions_json TEXT NOT NULL DEFAULT '[]',
    current_question_id INTEGER,
    next_turn_sequence INTEGER NOT NULL DEFAULT 1,
    phase_question_index INTEGER NOT NULL DEFAULT 0,
    follow_ups_for_question INTEGER NOT NULL DEFAULT 0,
    consent_version TEXT,
    consent_at TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    UNIQUE (application_id, attempt_no),
    CHECK (attempt_no > 0),
    CHECK (phase IN ('SCREENING', 'TECHNICAL', 'BEHAVIORAL', 'COMPLETE')),
    CHECK (phase_question_index >= 0),
    CHECK (next_turn_sequence > 0),
    CHECK (follow_ups_for_question >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_application_ai_interview_active
    ON application_ai_interviews(application_id)
    WHERE status NOT IN ('CANCELLED', 'EXPIRED');
CREATE INDEX IF NOT EXISTS idx_application_ai_interviews_org_status
    ON application_ai_interviews(org_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_application_ai_interviews_candidate
    ON application_ai_interviews(candidate_user_id, status, updated_at);

CREATE TABLE IF NOT EXISTS application_ai_interview_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id INTEGER NOT NULL REFERENCES application_ai_interviews(id) ON DELETE CASCADE,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL,
    phase TEXT NOT NULL,
    question_type TEXT NOT NULL DEFAULT 'CORE',
    competency_key TEXT NOT NULL DEFAULT '',
    difficulty INTEGER NOT NULL DEFAULT 2,
    question_text TEXT NOT NULL,
    answer_text TEXT,
    state TEXT NOT NULL DEFAULT 'ASKED',
    assessment_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    answered_at TEXT,
    UNIQUE (interview_id, sequence_no),
    CHECK (sequence_no > 0),
    CHECK (phase IN ('TECHNICAL', 'BEHAVIORAL')),
    CHECK (question_type IN ('CORE', 'FOLLOW_UP')),
    CHECK (difficulty BETWEEN 1 AND 3),
    CHECK (state IN ('ASKED', 'ANSWER_QUEUED', 'ASSESSED'))
);
CREATE INDEX IF NOT EXISTS idx_ai_interview_turns_app_sequence
    ON application_ai_interview_turns(application_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_ai_interview_turns_run_sequence
    ON application_ai_interview_turns(interview_id, sequence_no);
"""
