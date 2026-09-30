"""
Platform administration endpoints.

Everything here is restricted to platform admins and audited at Tier 1.

Impersonation is the highest-privilege operation in the product, so the
controls around it are enforced in code rather than left to policy:

  * a written reason is mandatory and stored on the audit event
  * the issued token is short-lived and separate from the admin's own session
  * both the grant and the resulting token carry `impersonated_by`, so every
    downstream action is attributable to the real human, not just the target
  * the frontend is expected to render a persistent banner off the
    `impersonated_by` field returned by /auth/me
"""

import asyncio
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import database as db
from app.shared import audit, security
from app.shared.authz import Actor, requires
from app.shared.rbac import Capability

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# Impersonation sessions are deliberately far shorter than normal sessions.
IMPERSONATION_TTL = timedelta(minutes=30)


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


class ImpersonateRequest(BaseModel):
    user_id: int
    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Why this impersonation is necessary. Stored permanently in the audit log.",
    )


@router.get("/audit")
async def search_audit_log(
    actor: Actor = Depends(requires(Capability.AUDIT_READ)),
    org_id: int | None = Query(default=None),
    actor_user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Search the audit log.

    Non-platform-admins are forcibly scoped to their own organization,
    regardless of the org_id they ask for — an org admin holds AUDIT_READ for
    their tenant only.
    """
    if not actor.is_platform_admin:
        org_id = actor.org_id
        if org_id is None:
            raise HTTPException(
                status_code=400,
                detail="Select an organization context to read its audit log.",
            )

    events = await _db(
        db.list_audit_events,
        org_id=org_id,
        actor_user_id=actor_user_id,
        action=action,
        limit=limit,
        offset=offset,
    )
    return {"events": events, "limit": limit, "offset": offset}


@router.get("/audit/verify")
async def verify_audit_integrity(
    limit: int = Query(default=1000, ge=1, le=10_000),
    actor: Actor = Depends(requires(Capability.ADMIN_TENANT_MANAGE)),
):
    """Walk the audit hash chain and report the first break, if any.

    A `valid: false` result means the log has been altered or rows were
    deleted, and should be treated as a security incident.
    """
    return await _db(db.verify_audit_chain, limit)


@router.post("/impersonate")
async def impersonate(
    req: ImpersonateRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.ADMIN_IMPERSONATE)),
):
    """Issue a short-lived token acting as another user."""
    target = await _db(db.get_user, req.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Not found.")

    if target["id"] == actor.user_id:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself.")

    if target.get("is_platform_admin"):
        # Admin-on-admin impersonation would let one admin launder actions
        # through another's identity, undermining the whole audit story.
        raise HTTPException(
            status_code=403,
            detail="Impersonating another platform admin is not permitted.",
        )

    audit.record_from_actor(
        actor,
        "admin.impersonation.started",
        tier=audit.AuditTier.SECURITY,
        actor_ip=_client_ip(request),
        resource_type="user",
        resource_id=target["id"],
        detail={"reason": req.reason, "target_email": target["email"]},
    )

    token = security.create_access_token_with_provenance(
        target["id"], ttl=IMPERSONATION_TTL, impersonated_by=actor.user_id
    )
    logger.warning(
        "IMPERSONATION user=%s acting_as=%s reason=%s",
        actor.user_id, target["id"], req.reason,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": int(IMPERSONATION_TTL.total_seconds()),
        "impersonating_user_id": target["id"],
        "warning": "All actions taken with this token are audited and attributed to you.",
    }


@router.get("/organizations")
async def list_all_organizations(
    actor: Actor = Depends(requires(Capability.ADMIN_TENANT_MANAGE)),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Cross-tenant organization listing. Platform admins only."""
    return await _db(db.list_organizations, limit, offset)
