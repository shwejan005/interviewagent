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
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import database as db
from app.evaluation.dto import (
    ActorResponse,
    AddMemberRequest,
    AccountEmailRequest,
    AccountTokenRequest,
    CreateOrganizationRequest,
    LoginRequest,
    AcceptInvitationRequest,
    InterviewProfileRequest,
    MembershipSummary,
    OrganizationResponse,
    RegisterRequest,
    RegistrationResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SetMemberRoleRequest,
    TokenResponse,
)
from app.shared import audit, notifications, security
from app.shared.authz import Actor, assert_tenant, current_actor, requires
from app.shared.rbac import ORG_SCOPED_ROLES, Capability, SystemRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["identity"])
org_router = APIRouter(prefix="/orgs", tags=["organizations"])

_INVALID_CREDENTIALS = "Invalid email or password."
_NOT_FOUND = "Not found."
_GENERIC_REGISTER_MESSAGE = (
    "If an account can be created, next steps will be sent to that email address. "
    "If verification is disabled, you can sign in now."
)
_GENERIC_ACCOUNT_MESSAGE = "If an eligible account exists, instructions will be sent to that email address."


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ── Authentication ───────────────────────────────────────────────────


@router.post("/register", response_model=RegistrationResponse, status_code=202)
async def register(req: RegisterRequest, request: Request, background_tasks: BackgroundTasks):
    """Create an account without revealing whether the email was registered.

    New accounts have no organization membership — they begin as candidates.
    Becoming a recruiter happens by creating an org or accepting an invitation.
    """
    verification_required = notifications.email_verification_required()
    if verification_required and not notifications.smtp_configured():
        raise HTTPException(status_code=503, detail="Email verification is not configured.")

    password_hash = await _db(security.hash_password, req.password)
    user_id = None
    try:
        user_id = await _db(
            db.create_user,
            email=str(req.email),
            password_hash=password_hash,
            full_name=req.full_name,
        )
    except db.DuplicateEmailError:
        # Same response for existing and new addresses; never issue a session
        # or reset an existing user's password through registration.
        pass

    if user_id is not None:
        audit.record(
            audit.Action.USER_REGISTERED,
            tier=audit.AuditTier.SECURITY,
            actor_user_id=user_id,
            actor_ip=_client_ip(request),
            resource_type="user",
            resource_id=user_id,
        )
        if verification_required:
            await _issue_account_token(
                user_id,
                str(req.email),
                "EMAIL_VERIFY",
                timedelta(hours=48),
                background_tasks,
            )
        else:
            await _db(db.mark_user_email_verified, user_id)

    return RegistrationResponse(
        message=_GENERIC_REGISTER_MESSAGE,
        verification_required=verification_required,
    )


async def _issue_account_token(
    user_id: int,
    email: str,
    purpose: str,
    ttl: timedelta,
    background_tasks: BackgroundTasks,
) -> bool:
    token = security.generate_account_token()
    expires_at = (datetime.now(timezone.utc) + ttl).isoformat()
    created = await _db(
        db.create_account_token,
        user_id,
        purpose,
        security.hash_account_token(token),
        expires_at,
    )
    if not created:
        return False
    sender = (
        notifications.send_email_verification_email
        if purpose == "EMAIL_VERIFY"
        else notifications.send_password_reset_email
    )
    background_tasks.add_task(_deliver_account_email, sender, email, token)
    return True


def _deliver_account_email(sender, email: str, token: str) -> None:
    try:
        delivery = sender(email, token)
        if delivery not in {"sent", "not_configured"}:
            logger.warning("Account email delivery was not successful: %s", delivery)
    except Exception:
        logger.exception("Account email delivery failed")


@router.post("/email-verification/resend", response_model=RegistrationResponse, status_code=202)
async def resend_email_verification(req: AccountEmailRequest, background_tasks: BackgroundTasks):
    """Resend a verification link without confirming account existence."""
    user = await _db(db.get_account_recovery_user, str(req.email))
    if user is not None and not user.get("email_verified_at"):
        await _issue_account_token(
            int(user["id"]),
            user["email"],
            "EMAIL_VERIFY",
            timedelta(hours=48),
            background_tasks,
        )
    return RegistrationResponse(message=_GENERIC_ACCOUNT_MESSAGE)


@router.post("/verify-email", response_model=RegistrationResponse)
async def verify_email(req: AccountTokenRequest, request: Request):
    user_id = await _db(
        db.consume_account_token,
        security.hash_account_token(req.token),
        "EMAIL_VERIFY",
    )
    if user_id is None:
        raise HTTPException(status_code=400, detail="This verification link is invalid or expired.")
    audit.record(
        "user.email_verified",
        tier=audit.AuditTier.SECURITY,
        actor_user_id=user_id,
        actor_ip=_client_ip(request),
        resource_type="user",
        resource_id=user_id,
    )
    return RegistrationResponse(message="Email verified. You can now sign in.")


@router.post("/password-reset/request", response_model=RegistrationResponse, status_code=202)
async def request_password_reset(req: PasswordResetRequest, background_tasks: BackgroundTasks):
    """Send a time-limited reset link, if the address belongs to an active user."""
    user = await _db(db.get_account_recovery_user, str(req.email))
    if user is not None:
        await _issue_account_token(
            int(user["id"]),
            user["email"],
            "PASSWORD_RESET",
            timedelta(hours=1),
            background_tasks,
        )
    return RegistrationResponse(message=_GENERIC_ACCOUNT_MESSAGE)


@router.post("/password-reset/confirm", response_model=RegistrationResponse)
async def confirm_password_reset(req: PasswordResetConfirmRequest, request: Request):
    password_hash = await _db(security.hash_password, req.new_password)
    user_id = await _db(
        db.consume_account_token,
        security.hash_account_token(req.token),
        "PASSWORD_RESET",
        password_hash=password_hash,
    )
    if user_id is None:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or expired.")
    audit.record(
        "user.password_reset",
        tier=audit.AuditTier.SECURITY,
        actor_user_id=user_id,
        actor_ip=_client_ip(request),
        resource_type="user",
        resource_id=user_id,
    )
    return RegistrationResponse(message="Password updated. Sign in with your new password.")


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

    token = security.create_access_token(user["id"], auth_version=int(user.get("auth_version", 0)))
    return TokenResponse(
        access_token=token,
        expires_in=int(security.ACCESS_TOKEN_TTL.total_seconds()),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(actor: Actor = Depends(current_actor)):
    """Issue a fresh normal session token while the current one is valid."""
    if actor.impersonated_by is not None:
        raise HTTPException(
            status_code=403,
            detail="Impersonation sessions cannot be extended.",
        )

    token = security.create_access_token(actor.user_id, auth_version=actor.auth_version)
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
        email_verified_at=actor.email_verified_at,
        email_verification_required=notifications.email_verification_required(),
        impersonated_by=actor.impersonated_by,
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


@router.get("/me/export")
async def export_my_data(actor: Actor = Depends(current_actor)):
    """Return the authenticated user's portable data export."""
    return await _db(db.export_user_data, actor.user_id)


@router.delete("/me", status_code=204)
async def delete_my_account(request: Request, actor: Actor = Depends(current_actor)):
    """Anonymize the account and remove candidate-owned data."""
    owners = await _db(db.active_owner_memberships, actor.user_id)
    if owners:
        raise HTTPException(
            status_code=409,
            detail="Transfer organization ownership before deleting this account.",
        )
    audit.record_from_actor(
        actor,
        "user.data_deleted",
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="user",
        resource_id=actor.user_id,
        detail={"organizations_owned": 0},
    )
    await _db(db.anonymize_user_data, actor.user_id)


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


@org_router.get("/{org_id}/team")
async def list_interview_team(
    org_id: int,
    actor: Actor = Depends(requires(Capability.INTERVIEW_SCHEDULE)),
):
    """Return the minimal member directory needed for interviewer assignment."""
    assert_tenant(actor, org_id)
    return {"members": await _db(db.list_org_members, org_id)}


@org_router.put("/{org_id}/members/{user_id}/interview-profile")
async def update_interview_profile(
    org_id: int,
    user_id: int,
    req: InterviewProfileRequest,
    actor: Actor = Depends(current_actor),
):
    assert_tenant(actor, org_id)
    if actor.user_id != user_id and not actor.has(Capability.ORG_MEMBER_ROLE_SET):
        raise HTTPException(status_code=403, detail="You can only update your own interview profile.")
    membership = await _db(db.get_membership, user_id, org_id)
    if membership is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    skills = list(dict.fromkeys(skill.strip() for skill in req.interview_skills if skill.strip()))
    try:
        profile = await _db(
            db.upsert_interviewer_profile,
            org_id,
            user_id,
            job_title=req.job_title,
            interview_skills=skills,
            timezone_name=req.timezone,
            weekly_capacity=req.weekly_capacity,
            available_for_interviews=req.available_for_interviews,
            updated_by=actor.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    audit.record_from_actor(
        actor,
        "organization.interview_profile_updated",
        resource_type="org_membership",
        resource_id=int(membership["id"]),
        resource_org_id=org_id,
        detail={"target_user_id": user_id, "skills_count": len(skills), "available": req.available_for_interviews},
    )
    return {"member": profile}


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
