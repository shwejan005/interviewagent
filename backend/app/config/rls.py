"""PostgreSQL row-level security policies for tenant and user-owned data.

Application authorization remains the first check. These policies are defense
in depth for a non-superuser application role; the local development `postgres`
superuser bypasses RLS by PostgreSQL design, so the verification script creates
a non-owner role and exercises the policies explicitly.
"""


def _policy(cur, table: str, expression: str) -> None:
    policy = f"evalia_rls_{table.replace('-', '_')}"
    cur.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    cur.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    cur.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
    cur.execute(f"CREATE POLICY {policy} ON {table} USING ({expression}) WITH CHECK ({expression})")


def apply_policies(cur) -> None:
    """Install idempotent policies on tables with a stable tenant/user boundary."""
    org = "NULLIF(current_setting('evalia.current_org_id', true), '')::bigint"
    user = "NULLIF(current_setting('evalia.current_user_id', true), '')::bigint"

    for table in ("campaigns", "job_postings", "applications", "application_events", "interviews", "referrals"):
        _policy(cur, table, f"org_id = {org}")

    _policy(cur, "organizations", f"id = {org}")
    _policy(cur, "org_memberships", f"org_id = {org} OR user_id = {user}")
    _policy(cur, "campaign_members", f"campaign_id IN (SELECT id FROM campaigns WHERE org_id = {org}) OR user_id = {user}")

    _policy(cur, "candidate_profiles", f"user_id = {user}")
    for table in ("work_experiences", "education_entries", "skill_claims", "job_preferences", "answer_vault_entries"):
        _policy(cur, table, f"profile_id IN (SELECT id FROM candidate_profiles WHERE user_id = {user})")

    for table in ("prep_roadmaps", "prep_submissions", "prep_code_submissions", "prep_goals", "prep_gamification", "prep_xp_events"):
        _policy(cur, table, f"user_id = {user}")
    _policy(cur, "prep_roadmap_nodes", f"roadmap_id IN (SELECT id FROM prep_roadmaps WHERE user_id = {user})")


def protected_tables() -> tuple[str, ...]:
    return (
        "organizations", "org_memberships", "campaigns", "campaign_members",
        "job_postings", "applications", "application_events", "interviews", "referrals",
        "candidate_profiles", "work_experiences", "education_entries", "skill_claims",
        "job_preferences", "answer_vault_entries", "prep_roadmaps", "prep_roadmap_nodes",
        "prep_submissions", "prep_code_submissions", "prep_goals", "prep_gamification", "prep_xp_events",
    )
