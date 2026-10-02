"""
Request-time authorization: who is acting, in which tenant, with what powers.

Provides FastAPI dependencies that resolve a bearer token into an ``Actor``
and enforce the three-layer check described in docs/PRODUCT_BLUEPRINT.md §2.2:

    1. TENANT    org match                  -> 404 (not 403; see below)
    2. ROLE      capability grant           -> 403
    3. RESOURCE  assignment to the object   -> 403

Cross-tenant access returns **404, not 403**, deliberately. A 403 confirms
that a resource exists, which lets a competitor enumerate another company's
campaign or candidate IDs. Denying existence is the correct response to a
request for something the caller has no right to know about.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from app.config import database as db
from app.shared import audit, security
from app.shared.rbac import Capability, SystemRole, capabilities_for_role
from app.shared.security import TokenError, decode_access_token

logger = logging.getLogger(__name__)

# Generic denial message. Never leaks which of the three layers rejected the
# request, or whether the resource exists.
_NOT_FOUND = "Not found."
_FORBIDDEN = "You do not have permission to perform this action."


@dataclass(frozen=True)
class Actor:
    """The authenticated principal behind a request."""

    user_id: int
    email: str
    full_name: str
    is_platform_admin: bool
    auth_version: int = 0
    email_verified_at: Optional[datetime | str] = None
    org_id: Optional[int] = None
    role: Optional[str] = None
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    impersonated_by: Optional[int] = None
    ip: Optional[str] = None

    def has(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def can_access_org(self, org_id: Optional[int]) -> bool:
        """Tenant boundary check.

        Platform admins are NOT granted implicit cross-tenant data access here.
        Reaching another org's records requires an explicit, audited
        impersonation session that sets `org_id` on the Actor.
        """
        if org_id is None:
            return True
        return self.org_id == org_id


async def _load_actor(token: str, org_id: Optional[int], ip: Optional[str]) -> Actor:
    import asyncio

    try:
        user_id, impersonated_by, token_auth_version = security.decode_access_token_details(token)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = await asyncio.to_thread(db.get_user, user_id)
    if user is None or user.get("status") != "ACTIVE":
        raise HTTPException(status_code=401, detail="Account is not active.")
    if int(user.get("auth_version", 0)) != token_auth_version:
        raise HTTPException(status_code=401, detail="Session is no longer valid.")

    is_admin = bool(user.get("is_platform_admin"))

    # No org requested: the actor operates in their personal (candidate) scope.
    if org_id is None:
        role = SystemRole.PLATFORM_ADMIN if is_admin else SystemRole.CANDIDATE
        capabilities = await asyncio.to_thread(db.get_role_capabilities, str(role))
        return Actor(
            user_id=user["id"],
            email=user["email"],
            full_name=user.get("full_name", ""),
            is_platform_admin=is_admin,
            auth_version=int(user.get("auth_version", 0)),
            email_verified_at=user.get("email_verified_at"),
            org_id=None,
            role=str(role),
            capabilities=capabilities or capabilities_for_role(str(role)),
            impersonated_by=impersonated_by,
            ip=ip,
        )

    membership = await asyncio.to_thread(db.get_membership, user_id, org_id)
    if membership is None:
        # Deny existence rather than confirming the org is real.
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    capabilities = await asyncio.to_thread(
        db.get_role_capabilities, membership["role_name"]
    )
    return Actor(
        user_id=user["id"],
        email=user["email"],
        full_name=user.get("full_name", ""),
        is_platform_admin=is_admin,
        auth_version=int(user.get("auth_version", 0)),
        email_verified_at=user.get("email_verified_at"),
        org_id=org_id,
        role=membership["role_name"],
        capabilities=capabilities or capabilities_for_role(membership["role_name"]),
        impersonated_by=impersonated_by,
        ip=ip,
    )


def _bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    return token.strip()


async def current_actor(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[int] = Header(default=None, alias="X-Org-Id"),
) -> Actor:
    """Resolve the caller.

    The active organization is selected per-request via the `X-Org-Id` header
    rather than baked into the token, so a user who belongs to several orgs can
    switch context without re-authenticating, and a revoked membership takes
    effect on the very next request.
    """
    token = _bearer_token(authorization)
    client_ip = request.client.host if request.client else None
    actor = await _load_actor(token, x_org_id, client_ip)
    db.set_request_db_context(
        user_id=actor.user_id,
        org_id=actor.org_id,
        is_platform_admin=actor.is_platform_admin,
    )
    return actor


async def optional_actor(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[int] = Header(default=None, alias="X-Org-Id"),
) -> Optional[Actor]:
    """Resolve the caller if credentials are present, else None.

    Used by endpoints that must keep working unauthenticated during the
    transition to a fully authenticated product.
    """
    if not authorization:
        return None
    try:
        return await current_actor(request, authorization, x_org_id)
    except HTTPException:
        return None


def requires(*capabilities: Capability):
    """Dependency factory enforcing that the actor holds every listed capability.

    Denials are audited: an authorization failure is security-relevant
    information, and a burst of them is a meaningful attack signal.
    """

    def _dependency(actor: Actor = Depends(current_actor)) -> Actor:
        missing = [c for c in capabilities if not actor.has(c)]
        if missing:
            audit.record_from_actor(
                actor,
                audit.Action.AUTHZ_DENIED,
                tier=audit.AuditTier.SECURITY,
                outcome="DENIED",
                actor_ip=actor.ip,
                detail={"missing_capabilities": [str(c) for c in missing]},
            )
            raise HTTPException(status_code=403, detail=_FORBIDDEN)
        return actor

    return _dependency


def require_org_context(actor: Actor = Depends(current_actor)) -> Actor:
    """Require that the caller has selected an organization via X-Org-Id."""
    if actor.org_id is None:
        raise HTTPException(
            status_code=400,
            detail="This endpoint requires an organization context. Send an X-Org-Id header.",
        )
    return actor


def assert_tenant(actor: Actor, resource_org_id: Optional[int]) -> None:
    """Enforce the tenant boundary on a loaded resource.

    Call this immediately after loading any org-scoped row, before returning
    any part of it. Raises 404 so the caller cannot distinguish "does not
    exist" from "belongs to someone else".
    """
    if not actor.can_access_org(resource_org_id):
        audit.record_from_actor(
            actor,
            audit.Action.AUTHZ_DENIED,
            tier=audit.AuditTier.SECURITY,
            outcome="DENIED",
            actor_ip=actor.ip,
            detail={"reason": "cross_tenant", "resource_org_id": resource_org_id},
        )
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
