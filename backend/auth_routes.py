"""
Identity, organization, and membership endpoints.

Deliberate behaviours worth knowing about:

* Login returns an identical error and takes comparable time whether the email
  is unknown or the password is wrong. Distinguishing them turns the login form
  into an account-enumeration oracle.
* Creating an organization makes the creator its ORG_OWNER in the same
  transaction-ish sequence. An org with no owner is unreachable and would need
  manual repair.
* Every state change here writes a Tier-1 audit event, because identity and
  access changes are exactly what an investigation needs to reconstruct.
"""

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request

import audit
import database as db
import security
import notifications
from authz import Actor, assert_tenant, current_actor, requires
from models import (
    ActorResponse,
    AddMemberRequest,
    CreateOrganizationRequest,
    LoginRequest,
    AcceptInvitationRequest,
    MembershipSummary,
    OrganizationResponse,
    RegisterRequest,
    SetMemberRoleRequest,
    TokenResponse,
)
from rbac import ORG_SCOPED_ROLES, Capability, SystemRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["identity"])
org_router = APIRouter(prefix="/orgs", tags=["organizations"])

_INVALID_CREDENTIALS = "Invalid email or password."
_NOT_FOUND = "Not found."


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ── Authentication ───────────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, request: Request):
    """Create an account and return an access token.

    New accounts have no organization membership — they begin as candidates.
    Becoming a recruiter happens by creating an org or accepting an invitation.
    """
    password_hash = security.hash_password(req.password)
    try:
        user_id = await _db(
            db.create_user,
            email=str(req.email),
            password_hash=password_hash,
            full_name=req.full_name,
        )
    except db.DuplicateEmailError:
        # Registration inherently reveals whether an email is taken. Mitigating
        # that properly requires an email-confirmation flow that always returns
        # success; that is a Phase 1 concern, noted rather than faked here.
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    audit.record(
        audit.Action.USER_REGISTERED,
        tier=audit.AuditTier.SECURITY,
        actor_user_id=user_id,
        actor_ip=_client_ip(request),
        resource_type="user",
        resource_id=user_id,
    )

    token = security.create_access_token(user_id)
    return TokenResponse(
        access_token=token,
        expires_in=int(security.ACCESS_TOKEN_TTL.total_seconds()),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """Exchange credentials for an access token."""
    ip = _client_ip(request)
    user = await _db(db.get_user_by_email, str(req.email))

    # Verify against a dummy hash when the user is absent so that response time
    # does not reveal whether the account exists.
    stored_hash = user["password_hash"] if user else security.hash_password("timing-equalizer")
    password_ok = await _db(security.verify_password, req.password, stored_hash)

    if user is None or not password_ok or user.get("status") != "ACTIVE":
        audit.record(
            audit.Action.USER_LOGIN_FAILED,
            tier=audit.AuditTier.SECURITY,
            actor_user_id=user["id"] if user else None,
            actor_ip=ip,
            outcome="DENIED",
            detail={"email_attempted": db.normalize_email(str(req.email))},
        )
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)

    await _db(db.touch_user_login, user["id"])
    audit.record(
        audit.Action.USER_LOGIN_SUCCEEDED,
        tier=audit.AuditTier.SECURITY,
        actor_user_id=user["id"],
        actor_ip=ip,
        resource_type="user",
        resource_id=user["id"],
    )

    token = security.create_access_token(user["id"])
    return TokenResponse(
        access_token=token,
        expires_in=int(security.ACCESS_TOKEN_TTL.total_seconds()),
    )


@router.get("/me", response_model=ActorResponse)
async def me(actor: Actor = Depends(current_actor)):
    """Return the caller's identity, active org context, and capabilities.

    The frontend uses `capabilities` to decide which controls to render. That
    is a UX affordance only — every capability is re-checked server-side.
    """
    memberships = await _db(db.list_memberships, actor.user_id)
    return ActorResponse(
        user_id=actor.user_id,
        email=actor.email,
        full_name=actor.full_name,
        is_platform_admin=actor.is_platform_admin,
        active_org_id=actor.org_id,
        active_role=actor.role,
        capabilities=sorted(str(c) for c in actor.capabilities),
        memberships=[
            MembershipSummary(
                org_id=m["org_id"],
                org_name=m["org_name"],
                org_slug=m["org_slug"],
                role_name=m["role_name"],
            )
            for m in memberships
        ],
    )


# ── Organizations ────────────────────────────────────────────────────


@org_router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    req: CreateOrganizationRequest,
    request: Request,
    actor: Actor = Depends(current_actor),
):
    """Create an organization; the caller becomes its owner."""
    try:
        org_id = await _db(db.create_organization, name=req.name, slug=req.slug)
    except db.DuplicateSlugError:
        raise HTTPException(status_code=409, detail="That organization slug is already taken.")

    # An organization without an owner cannot be administered, so this must not
    # be left to a second request that might never arrive.
    await _db(db.create_membership, org_id, actor.user_id, str(SystemRole.ORG_OWNER))

    audit.record_from_actor(
        actor,
        audit.Action.ORG_CREATED,
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="organization",
        resource_id=org_id,
        resource_org_id=org_id,
        detail={"name": req.name, "slug": req.slug},
    )

    org = await _db(db.get_organization, org_id)
    return OrganizationResponse(**{k: org[k] for k in ("id", "name", "slug", "plan", "status")})


@org_router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: int,
    actor: Actor = Depends(requires(Capability.ORG_SETTINGS_READ)),
):
    assert_tenant(actor, org_id)
    org = await _db(db.get_organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return OrganizationResponse(**{k: org[k] for k in ("id", "name", "slug", "plan", "status")})


# ── Membership ───────────────────────────────────────────────────────


@org_router.get("/{org_id}/members")
async def list_members(
    org_id: int,
    actor: Actor = Depends(requires(Capability.ORG_SETTINGS_READ)),
):
    assert_tenant(actor, org_id)
    return {"members": await _db(db.list_org_members, org_id)}


@org_router.post("/{org_id}/members", status_code=201)
async def add_member(
    org_id: int,
    req: AddMemberRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.ORG_MEMBER_INVITE)),
):
    """Add an existing user to the organization.

    Adding a not-yet-registered user is an invitation flow (tokenised email),
    which is Phase 1 work; this endpoint intentionally handles only the
    already-registered case rather than half-implementing invitations.
    """
    assert_tenant(actor, org_id)
    _validate_org_role(req.role)

    user = await _db(db.get_user_by_email, str(req.email))
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="No registered user with that email. Invitations are not yet supported.",
        )

    if await _db(db.get_membership, user["id"], org_id) is not None:
        raise HTTPException(status_code=409, detail="That user is already a member.")

    membership_id = await _db(db.create_membership, org_id, user["id"], req.role)

    audit.record_from_actor(
        actor,
        audit.Action.ORG_MEMBER_ADDED,
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="org_membership",
        resource_id=membership_id,
        resource_org_id=org_id,
        detail={"target_user_id": user["id"], "role": req.role},
    )
    return {"membership_id": membership_id, "user_id": user["id"], "role": req.role}


@org_router.post("/{org_id}/invitations", status_code=201)
async def invite_member(
    org_id: int,
    req: AddMemberRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.ORG_MEMBER_INVITE)),
):
    """Invite an unregistered or existing user with a single-use token."""
    assert_tenant(actor, org_id)
    _validate_org_role(req.role)
    try:
        invitation = await _db(
            db.create_invitation, org_id, str(req.email), req.role, actor.user_id
        )
    except db.DuplicateInvitationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    organization = await _db(db.get_organization, org_id)
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    invite_url = f"{frontend_url}/invite?token={invitation['token']}"
    delivery = await asyncio.to_thread(
        notifications.send_organization_invitation_email,
        str(req.email), organization["name"], req.role, invite_url,
    )
    audit.record_from_actor(
        actor,
        audit.Action.ORG_MEMBER_INVITED,
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="organization_invitation",
        resource_id=invitation["id"],
        resource_org_id=org_id,
        detail={"email": str(req.email), "role": req.role},
    )
    return {
        **{key: invitation[key] for key in ("id", "org_id", "email_normalized", "role_name", "expires_at", "created_at")},
        "invite_url": invite_url,
        "email_delivery": delivery,
    }


@org_router.get("/{org_id}/invitations")
async def get_invitations(
    org_id: int,
    include_completed: bool = False,
    actor: Actor = Depends(requires(Capability.ORG_SETTINGS_READ)),
):
    assert_tenant(actor, org_id)
    return {"invitations": await _db(db.list_invitations, org_id, include_completed=include_completed)}


@router.post("/invitations/accept")
async def accept_invitation(
    req: AcceptInvitationRequest,
    request: Request,
    actor: Actor = Depends(current_actor),
):
    try:
        result = await _db(db.accept_invitation, req.token, actor.user_id)
    except db.InvalidInvitationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except db.InvitationEmailMismatchError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    audit.record_from_actor(
        actor,
        "org.member.invitation_accepted",
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="organization",
        resource_id=result["org_id"],
        resource_org_id=result["org_id"],
        detail={"invitation_id": result["invitation_id"], "role": result["role"]},
    )
    return result


@org_router.patch("/{org_id}/members/{user_id}")
async def set_member_role(
    org_id: int,
    user_id: int,
    req: SetMemberRoleRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.ORG_MEMBER_ROLE_SET)),
):
    assert_tenant(actor, org_id)
    _validate_org_role(req.role)

    existing = await _db(db.get_membership, user_id, org_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    _guard_last_owner(existing, org_id, changing_to=req.role)

    await _db(db.set_membership_role, org_id, user_id, req.role)
    audit.record_from_actor(
        actor,
        audit.Action.ORG_MEMBER_ROLE_CHANGED,
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="org_membership",
        resource_id=existing["id"],
        resource_org_id=org_id,
        detail={"target_user_id": user_id, "from": existing["role_name"], "to": req.role},
    )
    return {"user_id": user_id, "role": req.role}


@org_router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_member(
    org_id: int,
    user_id: int,
    request: Request,
    actor: Actor = Depends(requires(Capability.ORG_MEMBER_REMOVE)),
):
    assert_tenant(actor, org_id)
    existing = await _db(db.get_membership, user_id, org_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    _guard_last_owner(existing, org_id, changing_to=None)

    await _db(db.remove_membership, org_id, user_id)
    audit.record_from_actor(
        actor,
        audit.Action.ORG_MEMBER_REMOVED,
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="org_membership",
        resource_id=existing["id"],
        resource_org_id=org_id,
        detail={"target_user_id": user_id, "previous_role": existing["role_name"]},
    )


def _validate_org_role(role: str) -> None:
    if role not in {str(r) for r in ORG_SCOPED_ROLES}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Choose from: {sorted(str(r) for r in ORG_SCOPED_ROLES)}",
        )


def _guard_last_owner(membership, org_id, changing_to) -> None:
    """Refuse to leave an organization with no owner.

    Checked synchronously against current members rather than trusting the
    caller, because an org stranded without an owner requires manual
    intervention to recover.
    """
    if membership["role_name"] != str(SystemRole.ORG_OWNER):
        return
    if changing_to == str(SystemRole.ORG_OWNER):
        return

    members = db.list_org_members(org_id)
    owners = [m for m in members if m["role_name"] == str(SystemRole.ORG_OWNER)]
    if len(owners) <= 1:
        raise HTTPException(
            status_code=409,
            detail="Cannot remove or demote the only owner. Promote another owner first.",
        )
