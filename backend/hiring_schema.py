"""
DDL for the hiring domain: candidate profiles, campaigns, postings, applications.

Kept separate from database.py purely to stop that module growing without
bound; it contains constants only and imports nothing, so there is no cycle
with the data-access modules that consume it.

Portability notes:
  * JSON-ish columns are TEXT in both dialects and serialized in Python.
    Postgres JSONB would be better for querying, but matching behaviour across
    both backends matters more while SQLite is the test substrate.
  * Dates are TEXT (ISO-8601) in SQLite, native types in Postgres.
  * Every tenant-scoped table carries org_id, indexed, so Row-Level Security
    can be layered on later without a data migration (see DECISIONS.md D-01).
"""

# ── Candidate profile vault ─────────────────────────────────────────

_PROFILE_PG = """
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    headline TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    work_authorization TEXT NOT NULL DEFAULT '',
    years_experience DOUBLE PRECISION,
    open_to_work BOOLEAN NOT NULL DEFAULT TRUE,
    -- Opt-in, defaults closed. Being "open to work" and being willing to have
    -- a stranger's recruiter search surface your profile are different
    -- decisions; conflating them would make passive candidates searchable
    -- without ever having agreed to it.
    is_discoverable BOOLEAN NOT NULL DEFAULT FALSE,
    resume_text TEXT NOT NULL DEFAULT '',
    -- Consent and retention are captured from day one. Retrofitting consent
    -- onto data already collected without it is not legally possible.
    data_consent_at TIMESTAMPTZ,
    data_consent_version TEXT,
    retention_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS work_experiences (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL,
    end_date TEXT,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS education_entries (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    institution TEXT NOT NULL,
    degree TEXT NOT NULL DEFAULT '',
    field TEXT NOT NULL DEFAULT '',
    start_year INTEGER,
    end_year INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skill_claims (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    skill_normalized TEXT NOT NULL,
    years DOUBLE PRECISION,
    -- Verified means demonstrated in-platform, not self-asserted. Kept
    -- separate from the claim so the two can never be conflated in matching.
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_preferences (
    profile_id INTEGER PRIMARY KEY REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    desired_roles TEXT NOT NULL DEFAULT '[]',
    locations TEXT NOT NULL DEFAULT '[]',
    remote_preference TEXT NOT NULL DEFAULT 'ANY',
    min_salary DOUBLE PRECISION,
    max_salary DOUBLE PRECISION,
    currency TEXT NOT NULL DEFAULT 'INR',
    notice_period_days INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS answer_vault_entries (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    question_key TEXT NOT NULL,
    question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_entry ON answer_vault_entries (profile_id, question_key);
CREATE INDEX IF NOT EXISTS idx_experience_profile ON work_experiences(profile_id);
CREATE INDEX IF NOT EXISTS idx_education_profile ON education_entries(profile_id);
CREATE INDEX IF NOT EXISTS idx_skill_profile ON skill_claims(profile_id);
CREATE INDEX IF NOT EXISTS idx_skill_normalized ON skill_claims(skill_normalized);
"""

_PROFILE_SQLITE = """
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    headline TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    work_authorization TEXT NOT NULL DEFAULT '',
    years_experience REAL,
    open_to_work INTEGER NOT NULL DEFAULT 1,
    is_discoverable INTEGER NOT NULL DEFAULT 0,
    resume_text TEXT NOT NULL DEFAULT '',
    data_consent_at TEXT,
    data_consent_version TEXT,
    retention_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS work_experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL,
    end_date TEXT,
    is_current INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS education_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    institution TEXT NOT NULL,
    degree TEXT NOT NULL DEFAULT '',
    field TEXT NOT NULL DEFAULT '',
    start_year INTEGER,
    end_year INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS skill_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    skill_normalized TEXT NOT NULL,
    years REAL,
    verified INTEGER NOT NULL DEFAULT 0,
    verified_source TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS job_preferences (
    profile_id INTEGER PRIMARY KEY REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    desired_roles TEXT NOT NULL DEFAULT '[]',
    locations TEXT NOT NULL DEFAULT '[]',
    remote_preference TEXT NOT NULL DEFAULT 'ANY',
    min_salary REAL,
    max_salary REAL,
    currency TEXT NOT NULL DEFAULT 'INR',
    notice_period_days INTEGER,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS answer_vault_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    question_key TEXT NOT NULL,
    question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_vault_entry ON answer_vault_entries (profile_id, question_key);
CREATE INDEX IF NOT EXISTS idx_experience_profile ON work_experiences(profile_id);
CREATE INDEX IF NOT EXISTS idx_education_profile ON education_entries(profile_id);
CREATE INDEX IF NOT EXISTS idx_skill_profile ON skill_claims(profile_id);
CREATE INDEX IF NOT EXISTS idx_skill_normalized ON skill_claims(skill_normalized);
"""


# ── Campaigns, postings, applications ───────────────────────────────

_HIRING_PG = """
CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS campaign_members (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    member_role TEXT NOT NULL DEFAULT 'RECRUITER',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (campaign_id, user_id)
);

CREATE TABLE IF NOT EXISTS job_postings (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    employment_type TEXT NOT NULL DEFAULT 'FULL_TIME',
    remote_policy TEXT NOT NULL DEFAULT 'ONSITE',
    min_experience DOUBLE PRECISION,
    max_experience DOUBLE PRECISION,
    salary_min DOUBLE PRECISION,
    salary_max DOUBLE PRECISION,
    currency TEXT NOT NULL DEFAULT 'INR',
    required_skills TEXT NOT NULL DEFAULT '[]',
    screening_questions TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    -- Defaults to FALSE deliberately: an automated employment decision is a
    -- regulated act. Orgs opt in explicitly and auditably. See DECISIONS.md D-10.
    auto_reject_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    posting_id INTEGER NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES candidate_profiles(id) ON DELETE SET NULL,
    -- Immutable copy of the profile as it was at submission. A candidate
    -- editing their profile later must not silently rewrite what a recruiter
    -- actually assessed.
    profile_snapshot TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'APPLIED',
    current_stage TEXT NOT NULL DEFAULT 'APPLIED',
    evaluation_id INTEGER REFERENCES evaluations(id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'DIRECT',
    withdrawn_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS application_answers (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    question_key TEXT NOT NULL,
    question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS application_events (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_stage TEXT,
    to_stage TEXT,
    actor_user_id INTEGER REFERENCES users(id),
    is_automated BOOLEAN NOT NULL DEFAULT FALSE,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interviews (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'Interview',
    scheduled_start TIMESTAMPTZ NOT NULL,
    scheduled_end TIMESTAMPTZ NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    meeting_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (scheduled_end > scheduled_start),
    CHECK (status IN ('SCHEDULED', 'CANCELLED', 'COMPLETED'))
);

CREATE TABLE IF NOT EXISTS interview_participants (
    id SERIAL PRIMARY KEY,
    interview_id INTEGER NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    participant_role TEXT NOT NULL,
    UNIQUE (interview_id, user_id)
);

CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    posting_id INTEGER NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    referred_by_user_id INTEGER NOT NULL REFERENCES users(id),
    -- Nullable: a recruiter may refer someone who has not registered yet.
    -- The referral becomes actionable once that email registers (Phase 4:
    -- invitations for non-users follow the same pattern).
    candidate_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    candidate_email TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    resulting_application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMPTZ
);

-- One live referral per candidate per posting from any recruiter at the org,
-- so repeatedly referring the same person does not spam their inbox.
CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_candidate_posting
    ON referrals (posting_id, candidate_email) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_referral_candidate ON referrals(candidate_user_id);
CREATE INDEX IF NOT EXISTS idx_referral_org ON referrals(org_id);

-- One live application per candidate per posting. Withdrawn applications are
-- excluded so a candidate who withdrew can genuinely re-apply.
CREATE UNIQUE INDEX IF NOT EXISTS uq_application_candidate_posting
    ON applications (posting_id, candidate_user_id) WHERE withdrawn_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_campaign_org ON campaigns(org_id);
CREATE INDEX IF NOT EXISTS idx_campaign_member_user ON campaign_members(user_id);
CREATE INDEX IF NOT EXISTS idx_posting_org ON job_postings(org_id);
CREATE INDEX IF NOT EXISTS idx_posting_campaign ON job_postings(campaign_id);
CREATE INDEX IF NOT EXISTS idx_posting_status ON job_postings(status);
CREATE INDEX IF NOT EXISTS idx_application_org ON applications(org_id);
CREATE INDEX IF NOT EXISTS idx_application_posting ON applications(posting_id);
CREATE INDEX IF NOT EXISTS idx_application_candidate ON applications(candidate_user_id);
CREATE INDEX IF NOT EXISTS idx_appevent_application ON application_events(application_id);
CREATE INDEX IF NOT EXISTS idx_interviews_org_start ON interviews(org_id, scheduled_start);
CREATE INDEX IF NOT EXISTS idx_interviews_application ON interviews(application_id);
CREATE INDEX IF NOT EXISTS idx_interview_participant_user ON interview_participants(user_id);
"""

_HIRING_SQLITE = """
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS campaign_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    member_role TEXT NOT NULL DEFAULT 'RECRUITER',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (campaign_id, user_id)
);

CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    employment_type TEXT NOT NULL DEFAULT 'FULL_TIME',
    remote_policy TEXT NOT NULL DEFAULT 'ONSITE',
    min_experience REAL,
    max_experience REAL,
    salary_min REAL,
    salary_max REAL,
    currency TEXT NOT NULL DEFAULT 'INR',
    required_skills TEXT NOT NULL DEFAULT '[]',
    screening_questions TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    auto_reject_enabled INTEGER NOT NULL DEFAULT 0,
    published_at TEXT,
    closed_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    posting_id INTEGER NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    candidate_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES candidate_profiles(id) ON DELETE SET NULL,
    profile_snapshot TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'APPLIED',
    current_stage TEXT NOT NULL DEFAULT 'APPLIED',
    evaluation_id INTEGER REFERENCES evaluations(id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'DIRECT',
    withdrawn_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS application_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    question_key TEXT NOT NULL,
    question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS application_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    from_stage TEXT,
    to_stage TEXT,
    actor_user_id INTEGER REFERENCES users(id),
    is_automated INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS interviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'Interview',
    scheduled_start TEXT NOT NULL,
    scheduled_end TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    meeting_url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (scheduled_end > scheduled_start),
    CHECK (status IN ('SCHEDULED', 'CANCELLED', 'COMPLETED'))
);

CREATE TABLE IF NOT EXISTS interview_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id INTEGER NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    participant_role TEXT NOT NULL,
    UNIQUE (interview_id, user_id)
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    posting_id INTEGER NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    referred_by_user_id INTEGER NOT NULL REFERENCES users(id),
    candidate_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    candidate_email TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    resulting_application_id INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    responded_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_candidate_posting
    ON referrals (posting_id, candidate_email) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_referral_candidate ON referrals(candidate_user_id);
CREATE INDEX IF NOT EXISTS idx_referral_org ON referrals(org_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_application_candidate_posting
    ON applications (posting_id, candidate_user_id) WHERE withdrawn_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_campaign_org ON campaigns(org_id);
CREATE INDEX IF NOT EXISTS idx_campaign_member_user ON campaign_members(user_id);
CREATE INDEX IF NOT EXISTS idx_posting_org ON job_postings(org_id);
CREATE INDEX IF NOT EXISTS idx_posting_campaign ON job_postings(campaign_id);
CREATE INDEX IF NOT EXISTS idx_posting_status ON job_postings(status);
CREATE INDEX IF NOT EXISTS idx_application_org ON applications(org_id);
CREATE INDEX IF NOT EXISTS idx_application_posting ON applications(posting_id);
CREATE INDEX IF NOT EXISTS idx_application_candidate ON applications(candidate_user_id);
CREATE INDEX IF NOT EXISTS idx_appevent_application ON application_events(application_id);
CREATE INDEX IF NOT EXISTS idx_interviews_org_start ON interviews(org_id, scheduled_start);
CREATE INDEX IF NOT EXISTS idx_interviews_application ON interviews(application_id);
CREATE INDEX IF NOT EXISTS idx_interview_participant_user ON interview_participants(user_id);
"""


SCHEMA_PG = _PROFILE_PG + _HIRING_PG
SCHEMA_SQLITE = _PROFILE_SQLITE + _HIRING_SQLITE
