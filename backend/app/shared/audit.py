"""
Audit trail: tiered, hash-chained, append-only.

Scope is deliberately defined rather than "log everything" — see
docs/PRODUCT_BLUEPRINT.md §4. Auditing every read would bury the security
signal in navigation noise and cost more than it returns.

    Tier 1  security and decisions   login, role change, hire/reject, export
    Tier 2  business mutations       campaign edited, interview scheduled
    Tier 3  sensitive reads          recruiter viewed a candidate profile

Integrity model: each event stores the hash of the previous event, so any
silent edit or deletion breaks the chain and is detectable by
``database.verify_audit_chain``. This gives *tamper evidence*, not tamper
proofing — an attacker able to rewrite every subsequent row could reforge the
chain. Resisting that requires periodic anchoring to separately-credentialed
storage, which is deliberately out of scope here and documented as such.
"""

import hashlib
import json
import logging
from enum import IntEnum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AuditTier(IntEnum):
    SECURITY = 1
    MUTATION = 2
    SENSITIVE_READ = 3


# Fields included in the integrity hash. Deliberately excludes `id` (assigned
# by the database after hashing) and `occurred_at` (defaulted by the database).
_HASHED_FIELDS = (
    "tier", "action", "actor_user_id", "actor_org_id", "actor_role",
    "impersonated_by", "resource_type", "resource_id", "resource_org_id",
    "outcome", "detail",
)


def compute_event_hash(event: dict, prev_hash: Optional[str]) -> str:
    """Deterministic SHA-256 over the event's material fields plus the prior hash."""
    payload = {field: event.get(field) for field in _HASHED_FIELDS}
    payload["prev_hash"] = prev_hash
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record(
    action: str,
    *,
    tier: AuditTier = AuditTier.MUTATION,
    actor_user_id: Optional[int] = None,
    actor_org_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    actor_ip: Optional[str] = None,
    impersonated_by: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
    resource_org_id: Optional[int] = None,
    outcome: str = "SUCCESS",
    detail: Optional[dict] = None,
    request_id: Optional[str] = None,
) -> Optional[int]:
    """Append an audit event.

    Never raises. An audit backend failure must not take down the product —
    but it is logged at ERROR so the gap is detectable rather than silent.
    Once a durable job queue exists this should enqueue rather than write
    inline (see docs/PRODUCT_BLUEPRINT.md §11.1).
    """
    from app.config import database as db

    event = {
        "tier": int(tier),
        "action": action,
        "actor_user_id": actor_user_id,
        "actor_org_id": actor_org_id,
        "actor_role": actor_role,
        "actor_ip": actor_ip,
        "impersonated_by": impersonated_by,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id is not None else None,
        "resource_org_id": resource_org_id,
        "outcome": outcome,
        "detail": json.dumps(detail or {}, sort_keys=True, default=str),
        "request_id": request_id,
    }

    try:
        prev_hash = db.get_last_audit_hash()
        event["prev_hash"] = prev_hash
        event["hash"] = compute_event_hash(event, prev_hash)
        return db.insert_audit_event(event)
    except Exception:
        logger.exception(
            "AUDIT WRITE FAILED action=%s actor=%s resource=%s:%s",
            action, actor_user_id, resource_type, resource_id,
        )
        return None


def record_from_actor(actor, action: str, **kwargs) -> Optional[int]:
    """Convenience wrapper that fills actor fields from an Actor instance."""
    kwargs.setdefault("actor_user_id", actor.user_id)
    kwargs.setdefault("actor_org_id", actor.org_id)
    kwargs.setdefault("actor_role", actor.role)
    kwargs.setdefault("impersonated_by", actor.impersonated_by)
    return record(action, **kwargs)


# ── Canonical action names ──────────────────────────────────────────
# Defined as constants so that a typo becomes an ImportError rather than an
# audit event nobody can find later.

class Action:
    USER_REGISTERED = "user.registered"
    USER_LOGIN_SUCCEEDED = "user.login.succeeded"
    USER_LOGIN_FAILED = "user.login.failed"

    ORG_CREATED = "org.created"
    ORG_MEMBER_INVITED = "org.member.invited"
    ORG_MEMBER_ADDED = "org.member.added"
    ORG_MEMBER_REMOVED = "org.member.removed"
    ORG_MEMBER_ROLE_CHANGED = "org.member.role_changed"

    EVALUATION_CREATED = "evaluation.created"
    EVALUATION_ROUND_SUBMITTED = "evaluation.round.submitted"
    EVALUATION_FINALIZED = "evaluation.finalized"
    EVALUATION_REJECTED = "evaluation.rejected"
    EVALUATION_VIEWED = "evaluation.viewed"

    AUTHZ_DENIED = "authz.denied"
