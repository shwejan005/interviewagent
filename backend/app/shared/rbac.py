"""
Capability-based access control.

Business logic must never branch on a role *name* (``if role == "recruiter"``).
It branches on a capability (``require(actor, Capability.CAMPAIGN_CREATE)``),
because role names change, get split, and eventually become customer-defined,
while capabilities are stable contracts.

Roles are seeded into the database from ``SYSTEM_ROLES`` below rather than
being hardcoded at the call site, so custom per-organization roles become
possible later without touching any handler.

Authorization is checked in three layers, in this order:

    1. TENANT    does the actor's org match the resource's org?
    2. ROLE      does the actor's role grant this capability?
    3. RESOURCE  is the actor assigned to this specific object?

Layer 1 is the hard boundary and is enforced even for platform admins unless
they are explicitly acting through an audited impersonation session.
"""

from enum import StrEnum


class Capability(StrEnum):
    """Every distinct action the system can authorize.

    Naming convention: ``<resource>:<action>[:<scope>]`` where an absent scope
    means "as permitted by tenant and resource assignment".
    """

    # ── Organization & membership ────────────────────────────────────
    ORG_SETTINGS_READ = "org:settings:read"
    ORG_SETTINGS_WRITE = "org:settings:write"
    ORG_MEMBER_INVITE = "org:member:invite"
    ORG_MEMBER_REMOVE = "org:member:remove"
    ORG_MEMBER_ROLE_SET = "org:member:role:set"
    ORG_DELETE = "org:delete"

    # ── Campaigns & postings ─────────────────────────────────────────
    CAMPAIGN_CREATE = "campaign:create"
    CAMPAIGN_READ_ASSIGNED = "campaign:read:assigned"
    CAMPAIGN_READ_ORG = "campaign:read:org"
    CAMPAIGN_UPDATE = "campaign:update"
    CAMPAIGN_DELETE = "campaign:delete"
    POSTING_PUBLISH = "posting:publish"

    # ── Applications ─────────────────────────────────────────────────
    APPLICATION_READ = "application:read"
    APPLICATION_ADVANCE = "application:advance"
    APPLICATION_REJECT = "application:reject"
    APPLICATION_EXPORT = "application:export"

    # ── Interviews ───────────────────────────────────────────────────
    INTERVIEW_SCHEDULE = "interview:schedule"
    INTERVIEW_CONDUCT = "interview:conduct"
    INTERVIEW_READ_ASSIGNED = "interview:read:assigned"

    # ── Candidates & sourcing ────────────────────────────────────────
    CANDIDATE_SEARCH = "candidate:search"
    CANDIDATE_REFER = "candidate:refer"

    # ── Candidate's own data ─────────────────────────────────────────
    PROFILE_READ_OWN = "profile:read:own"
    PROFILE_WRITE_OWN = "profile:write:own"
    APPLICATION_SUBMIT = "application:submit"
    APPLICATION_READ_OWN = "application:read:own"

    # ── Evaluations (the existing agent pipeline) ────────────────────
    EVALUATION_CREATE = "evaluation:create"
    EVALUATION_READ = "evaluation:read"

    # ── Platform administration ──────────────────────────────────────
    AUDIT_READ = "audit:read"
    ADMIN_TENANT_MANAGE = "admin:tenant:manage"
    ADMIN_USER_MANAGE = "admin:user:manage"
    ADMIN_IMPERSONATE = "admin:impersonate"


class SystemRole(StrEnum):
    """Built-in roles seeded on database initialization."""

    PLATFORM_ADMIN = "platform_admin"
    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    RECRUITER = "recruiter"
    HIRING_MANAGER = "hiring_manager"
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


# Roles that act inside an organization. A membership row is required to hold
# one of these; CANDIDATE and PLATFORM_ADMIN exist outside any single org.
ORG_SCOPED_ROLES = frozenset(
    {
        SystemRole.ORG_OWNER,
        SystemRole.ORG_ADMIN,
        SystemRole.RECRUITER,
        SystemRole.HIRING_MANAGER,
        SystemRole.INTERVIEWER,
    }
)


_RECRUITER_CAPABILITIES = frozenset(
    {
        Capability.CAMPAIGN_CREATE,
        Capability.CAMPAIGN_READ_ASSIGNED,
        Capability.CAMPAIGN_UPDATE,
        Capability.POSTING_PUBLISH,
        Capability.APPLICATION_READ,
        Capability.APPLICATION_ADVANCE,
        Capability.APPLICATION_REJECT,
        Capability.INTERVIEW_SCHEDULE,
        Capability.INTERVIEW_CONDUCT,
        Capability.INTERVIEW_READ_ASSIGNED,
        Capability.CANDIDATE_SEARCH,
        Capability.CANDIDATE_REFER,
        Capability.EVALUATION_CREATE,
        Capability.EVALUATION_READ,
    }
)

_HIRING_MANAGER_CAPABILITIES = _RECRUITER_CAPABILITIES | {
    Capability.CAMPAIGN_READ_ORG,
    Capability.APPLICATION_EXPORT,
    Capability.INTERVIEW_CONDUCT,
}

_ORG_ADMIN_CAPABILITIES = _HIRING_MANAGER_CAPABILITIES | {
    Capability.ORG_SETTINGS_READ,
    Capability.ORG_SETTINGS_WRITE,
    Capability.ORG_MEMBER_INVITE,
    Capability.ORG_MEMBER_REMOVE,
    Capability.ORG_MEMBER_ROLE_SET,
    Capability.CAMPAIGN_DELETE,
    Capability.AUDIT_READ,
}

SYSTEM_ROLES: dict[SystemRole, frozenset[Capability]] = {
    # Platform admins get every capability. Tenant isolation still applies:
    # reaching another org's data requires an audited impersonation session.
    SystemRole.PLATFORM_ADMIN: frozenset(Capability),
    SystemRole.ORG_OWNER: _ORG_ADMIN_CAPABILITIES | {Capability.ORG_DELETE},
    SystemRole.ORG_ADMIN: _ORG_ADMIN_CAPABILITIES,
    SystemRole.HIRING_MANAGER: _HIRING_MANAGER_CAPABILITIES,
    SystemRole.RECRUITER: _RECRUITER_CAPABILITIES,
    SystemRole.INTERVIEWER: frozenset(
        {
            Capability.INTERVIEW_CONDUCT,
            Capability.INTERVIEW_READ_ASSIGNED,
            # Deliberately narrow: an interviewer sees the applications tied to
            # interviews they are assigned to, never the wider candidate pool.
            Capability.APPLICATION_READ,
        }
    ),
    SystemRole.CANDIDATE: frozenset(
        {
            Capability.PROFILE_READ_OWN,
            Capability.PROFILE_WRITE_OWN,
            Capability.APPLICATION_SUBMIT,
            Capability.APPLICATION_READ_OWN,
            Capability.EVALUATION_CREATE,
            Capability.EVALUATION_READ,
        }
    ),
}


def capabilities_for_role(role: str) -> frozenset[Capability]:
    """Return the capability set for a system role name, or empty if unknown."""
    try:
        return SYSTEM_ROLES[SystemRole(role)]
    except ValueError:
        return frozenset()


def role_has_capability(role: str, capability: Capability) -> bool:
    return capability in capabilities_for_role(role)
