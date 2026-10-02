"""PostgreSQL row-level security policies for tenant and user-owned data.

Application authorization remains the first check. These policies are defense
in depth for a non-superuser application role; the local development `postgres`
superuser bypasses RLS by PostgreSQL design, so the verification script creates
a non-owner role and exercises the policies explicitly.
"""


def _policy(cur, table: str, expression: str, *, check_expression: str | None = None) -> None:
    policy = f"evalia_rls_{table.replace('-', '_')}"
    cur.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    cur.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    cur.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
    check = check_expression or expression
    cur.execute(f"CREATE POLICY {policy} ON {table} USING ({expression}) WITH CHECK ({check})")


def apply_policies(cur) -> None:
    """Install idempotent policies on tables with a stable tenant/user boundary."""
    org = "NULLIF(current_setting('evalia.current_org_id', true), '')::bigint"
    user = "NULLIF(current_setting('evalia.current_user_id', true), '')::bigint"
    worker = "COALESCE(current_setting('evalia.is_worker', true), 'false') = 'true'"

    for table in ("campaigns", "referrals", "interview_scorecards"):
        _policy(cur, table, f"org_id = {org}")
    _policy(cur, "interviewer_profiles", f"org_id = {org}")
    _policy(
        cur,
        "interviews",
        f"org_id = {org} OR id IN (SELECT interview_id FROM interview_participants WHERE user_id = {user})",
    )
    # Public job discovery must work for candidates without an active org. A
    # published posting is readable, but creating/updating postings remains
    # tenant-scoped through WITH CHECK.
    _policy(cur, "job_postings", f"org_id = {org} OR status = 'PUBLISHED'", check_expression=f"org_id = {org}")
    _policy(cur, "applications", f"org_id = {org} OR candidate_user_id = {user}")
    _policy(
        cur,
        "application_events",
        f"org_id = {org} OR application_id IN "
        f"(SELECT id FROM applications WHERE candidate_user_id = {user})",
    )
    _policy(
        cur,
        "application_answers",
        f"application_id IN (SELECT id FROM applications "
        f"WHERE org_id = {org} OR candidate_user_id = {user})",
    )
    for table in ("application_ai_interviews", "application_ai_interview_turns"):
        _policy(cur, table, f"org_id = {org} OR candidate_user_id = {user}")
    _policy(cur, "application_interview_reports", f"org_id = {org}")
    _policy(
        cur,
        "posting_evaluation_criteria",
        f"org_id = {org} OR EXISTS (SELECT 1 FROM job_postings jp "
        f"WHERE jp.id = posting_evaluation_criteria.posting_id AND jp.status = 'PUBLISHED')",
        check_expression=f"org_id = {org}",
    )

    _policy(
        cur,
        "organizations",
        f"id = {org} OR EXISTS (SELECT 1 FROM job_postings jp WHERE jp.org_id = organizations.id AND jp.status = 'PUBLISHED')",
        check_expression=f"id = {org}",
    )
    _policy(cur, "org_memberships", f"org_id = {org} OR user_id = {user}")
    _policy(cur, "campaign_members", f"campaign_id IN (SELECT id FROM campaigns WHERE org_id = {org}) OR user_id = {user}")
    _policy(
        cur,
        "user_notifications",
        f"user_id = {user} OR ({worker} AND org_id = {org} AND org_id IS NOT NULL)",
        check_expression=f"user_id = {user} OR ({worker} AND org_id = {org})",
    )

    _policy(cur, "candidate_profiles", f"user_id = {user}")
    for table in ("work_experiences", "education_entries", "skill_claims", "job_preferences", "answer_vault_entries"):
        _policy(cur, table, f"profile_id IN (SELECT id FROM candidate_profiles WHERE user_id = {user})")

    for table in ("prep_roadmaps", "prep_submissions", "prep_code_submissions", "prep_goals", "prep_gamification", "prep_xp_events"):
        _policy(cur, table, f"user_id = {user}")
    _policy(cur, "prep_roadmap_nodes", f"roadmap_id IN (SELECT id FROM prep_roadmaps WHERE user_id = {user})")


def protected_tables() -> tuple[str, ...]:
    return (
        "organizations", "org_memberships", "campaigns", "campaign_members",
        "job_postings", "applications", "application_answers", "application_events", "interviews", "referrals",
        "application_ai_interviews", "application_ai_interview_turns",
        "application_interview_reports", "posting_evaluation_criteria",
        "interviewer_profiles",
        "interview_scorecards",
        "user_notifications",
        "candidate_profiles", "work_experiences", "education_entries", "skill_claims",
        "job_preferences", "answer_vault_entries", "prep_roadmaps", "prep_roadmap_nodes",
        "prep_submissions", "prep_code_submissions", "prep_goals", "prep_gamification", "prep_xp_events",
    )
