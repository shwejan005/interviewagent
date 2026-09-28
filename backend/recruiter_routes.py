"""
Recruiter-facing endpoints: campaigns, job postings, applicant pipeline.

Every endpoint requires an organization context (`X-Org-Id`) and a capability,
and every query is org-scoped in SQL as well as checked by `assert_tenant`.
The redundancy is deliberate: a route-layer check can be forgotten when a new
endpoint is added, whereas a query that cannot express a cross-tenant read is
structurally safe.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import audit
import candidate_db as cdb
import hiring_db as hdb
import matching
from authz import Actor, assert_tenant, requires
from hiring_models import (
    CampaignRequest,
    PostingRequest,
    PostingStatusRequest,
    PostingUpdateRequest,
    ReferralRequest,
    TransitionRequest,
)
from rbac import Capability

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orgs/{org_id}", tags=["recruiting"])

_NOT_FOUND = "Not found."


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _require_org(actor: Actor, org_id: int) -> None:
    """Both layers: tenant match, then a usable org context."""
    assert_tenant(actor, org_id)
    if actor.org_id is None:
        raise HTTPException(
            status_code=400,
            detail="Send an X-Org-Id header matching this organization.",
        )


# ── Campaigns ────────────────────────────────────────────────────────


@router.post("/campaigns", status_code=201)
async def create_campaign(
    org_id: int,
    req: CampaignRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_CREATE)),
):
    _require_org(actor, org_id)
    campaign_id = await _db(
        hdb.create_campaign, org_id, req.name, req.description, actor.user_id
    )
    audit.record_from_actor(
        actor, "campaign.created",
        actor_ip=_client_ip(request),
        resource_type="campaign", resource_id=campaign_id, resource_org_id=org_id,
        detail={"name": req.name},
    )
    return await _db(hdb.get_campaign, campaign_id, org_id)


@router.get("/campaigns")
async def list_campaigns(
    org_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ASSIGNED)),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _require_org(actor, org_id)
    return {"campaigns": await _db(hdb.list_campaigns, org_id, limit, offset)}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    org_id: int,
    campaign_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ASSIGNED)),
):
    _require_org(actor, org_id)
    campaign = await _db(hdb.get_campaign, campaign_id, org_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return campaign


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    org_id: int,
    campaign_id: int,
    req: CampaignRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    _require_org(actor, org_id)
    if not await _db(hdb.update_campaign, campaign_id, org_id, **req.model_dump()):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "campaign.updated",
        actor_ip=_client_ip(request),
        resource_type="campaign", resource_id=campaign_id, resource_org_id=org_id,
    )
    return await _db(hdb.get_campaign, campaign_id, org_id)


# ── Job postings ─────────────────────────────────────────────────────


@router.post("/postings", status_code=201)
async def create_posting(
    org_id: int,
    req: PostingRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_CREATE)),
):
    """Create a posting in DRAFT. Publishing is a separate, audited action."""
    _require_org(actor, org_id)

    # Verified org-scoped, so a posting cannot be attached to another tenant's campaign.
    if await _db(hdb.get_campaign, req.campaign_id, org_id) is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    if (req.min_experience is not None and req.max_experience is not None
            and req.min_experience > req.max_experience):
        raise HTTPException(status_code=400, detail="min_experience cannot exceed max_experience.")

    payload = req.model_dump()
    payload["screening_questions"] = [q.model_dump() for q in req.screening_questions]
    campaign_id = payload.pop("campaign_id")
    title = payload.pop("title")

    posting_id = await _db(
        hdb.create_posting, org_id, campaign_id, title, actor.user_id, **payload
    )
    audit.record_from_actor(
        actor, "posting.created",
        actor_ip=_client_ip(request),
        resource_type="job_posting", resource_id=posting_id, resource_org_id=org_id,
        detail={"title": title, "auto_reject_enabled": req.auto_reject_enabled},
    )
    return await _db(hdb.get_posting, posting_id, org_id)


@router.get("/postings")
async def list_postings(
    org_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ASSIGNED)),
    campaign_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None, pattern="^(DRAFT|PUBLISHED|CLOSED)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _require_org(actor, org_id)
    return {
        "postings": await _db(
            hdb.list_postings, org_id, campaign_id, status, limit, offset
        )
    }


@router.get("/postings/{posting_id}")
async def get_posting(
    org_id: int,
    posting_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ASSIGNED)),
):
    _require_org(actor, org_id)
    posting = await _db(hdb.get_posting, posting_id, org_id)
    if posting is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return posting


@router.patch("/postings/{posting_id}")
async def update_posting(
    org_id: int,
    posting_id: int,
    req: PostingUpdateRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    _require_org(actor, org_id)
    payload = req.model_dump(exclude_none=True)
    if req.screening_questions is not None:
        payload["screening_questions"] = [q.model_dump() for q in req.screening_questions]

    if not await _db(hdb.update_posting, posting_id, org_id, **payload):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    audit.record_from_actor(
        actor, "posting.updated",
        actor_ip=_client_ip(request),
        resource_type="job_posting", resource_id=posting_id, resource_org_id=org_id,
        detail={"fields": sorted(payload.keys())},
    )
    return await _db(hdb.get_posting, posting_id, org_id)


@router.post("/postings/{posting_id}/status")
async def set_posting_status(
    org_id: int,
    posting_id: int,
    req: PostingStatusRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.POSTING_PUBLISH)),
):
    """Publish, unpublish, or close a posting.

    Publishing makes the posting visible on the public job board, so it is
    gated on its own capability and audited separately from editing.
    """
    _require_org(actor, org_id)
    if not await _db(hdb.set_posting_status, posting_id, org_id, req.status):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    audit.record_from_actor(
        actor, f"posting.{req.status.casefold()}",
        actor_ip=_client_ip(request),
        resource_type="job_posting", resource_id=posting_id, resource_org_id=org_id,
    )
    return await _db(hdb.get_posting, posting_id, org_id)


# ── Applicant pipeline ───────────────────────────────────────────────


@router.get("/postings/{posting_id}/applications")
async def list_applications(
    org_id: int,
    posting_id: int,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ)),
    stage: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Applicant pipeline for one posting, with per-stage funnel counts."""
    _require_org(actor, org_id)
    if await _db(hdb.get_posting, posting_id, org_id) is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    applications = await _db(
        hdb.list_applications_for_posting, posting_id, org_id, stage, limit, offset
    )
    counts = await _db(hdb.count_applications_for_posting, posting_id, org_id)
    return {"applications": applications, "funnel": counts}


@router.get("/applications/{application_id}")
async def get_application(
    org_id: int,
    application_id: int,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ)),
):
    """Full application detail. Reading a candidate's data is audited."""
    _require_org(actor, org_id)
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    # Tier 3: a recruiter reading candidate data is exactly what an
    # investigation or a subject-access request needs to reconstruct.
    audit.record_from_actor(
        actor, "application.viewed",
        tier=audit.AuditTier.SENSITIVE_READ,
        resource_type="application", resource_id=application_id, resource_org_id=org_id,
    )

    return {
        "application": application,
        "answers": await _db(hdb.get_application_answers, application_id),
        "timeline": await _db(hdb.list_application_events, application_id),
    }


@router.post("/applications/{application_id}/transition")
async def transition_application(
    org_id: int,
    application_id: int,
    req: TransitionRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.APPLICATION_ADVANCE)),
):
    """Move an application to a new stage.

    Rejection requires APPLICATION_REJECT in addition to APPLICATION_ADVANCE —
    advancing someone and ending their candidacy are different acts and are
    deliberately not granted by the same capability.
    """
    _require_org(actor, org_id)

    if req.to_stage == str(hdb.ApplicationStage.REJECTED) and not actor.has(Capability.APPLICATION_REJECT):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to reject applications.",
        )

    try:
        result = await _db(
            hdb.transition_application,
            application_id, org_id, req.to_stage, actor.user_id, req.note, False,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except hdb.InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    is_rejection = req.to_stage == str(hdb.ApplicationStage.REJECTED)
    audit.record_from_actor(
        actor,
        "application.rejected" if is_rejection else "application.advanced",
        # A rejection is an adverse decision about a person, so it is Tier 1
        # regardless of how routine it is operationally.
        tier=audit.AuditTier.SECURITY if is_rejection else audit.AuditTier.MUTATION,
        actor_ip=_client_ip(request),
        resource_type="application", resource_id=application_id, resource_org_id=org_id,
        detail={"from": result["from_stage"], "to": result["to_stage"], "note": req.note},
    )
    return result


# ── Candidate sourcing ───────────────────────────────────────────────


@router.get("/candidates/search")
async def search_candidates(
    org_id: int,
    actor: Actor = Depends(requires(Capability.CANDIDATE_SEARCH)),
    skill: Optional[str] = Query(default=None, max_length=100),
    location: Optional[str] = Query(default=None, max_length=200),
    min_years: Optional[float] = Query(default=None, ge=0, le=70),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Talent pool search.

    Only candidates who opted into `is_discoverable` ever appear here — that
    filter is enforced in the query itself, not as a post-filter, so it
    cannot be bypassed by a route bug. Reading this endpoint is audited
    because browsing candidates, unlike browsing your own pipeline, is a
    search over people who have not applied to you.
    """
    _require_org(actor, org_id)
    result = await _db(
        cdb.search_discoverable_profiles,
        skill, location, min_years, limit, offset,
    )
    audit.record_from_actor(
        actor, "candidate.searched",
        tier=audit.AuditTier.SENSITIVE_READ,
        resource_org_id=org_id,
        detail={"skill": skill, "location": location, "result_count": len(result["profiles"])},
    )
    return result


@router.get("/postings/{posting_id}/recommended-candidates")
async def recommended_candidates(
    org_id: int,
    posting_id: int,
    actor: Actor = Depends(requires(Capability.CANDIDATE_SEARCH)),
    skill: Optional[str] = Query(default=None, max_length=100),
    location: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Candidates ranked against this posting's requirements. See matching.py
    for the scoring model and its explicit, deterministic-not-learned scope."""
    _require_org(actor, org_id)
    if await _db(hdb.get_posting, posting_id, org_id) is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    results = await _db(
        matching.rank_candidates_for_posting, posting_id, org_id, limit, skill, location
    )
    audit.record_from_actor(
        actor, "candidate.searched",
        tier=audit.AuditTier.SENSITIVE_READ,
        resource_type="job_posting", resource_id=posting_id, resource_org_id=org_id,
        detail={"mode": "recommended", "result_count": len(results)},
    )
    return {"posting_id": posting_id, "candidates": results}


# ── Referrals ────────────────────────────────────────────────────────


@router.post("/postings/{posting_id}/referrals", status_code=201)
async def refer_candidate(
    org_id: int,
    posting_id: int,
    req: ReferralRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CANDIDATE_REFER)),
):
    """Refer a candidate a recruiter knows or has sourced to this posting."""
    _require_org(actor, org_id)
    if await _db(hdb.get_posting, posting_id, org_id) is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    try:
        referral_id = await _db(
            hdb.create_referral, org_id, posting_id, actor.user_id,
            str(req.candidate_email), req.note,
        )
    except hdb.DuplicateReferralError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    audit.record_from_actor(
        actor, "referral.created",
        actor_ip=_client_ip(request),
        resource_type="referral", resource_id=referral_id, resource_org_id=org_id,
        detail={"posting_id": posting_id},
    )
    return await _db(hdb.get_referral, referral_id, org_id)


@router.get("/referrals")
async def list_referrals(
    org_id: int,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ)),
    posting_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _require_org(actor, org_id)
    return {"referrals": await _db(hdb.list_referrals_for_org, org_id, posting_id, limit, offset)}


# ── Analytics ────────────────────────────────────────────────────────


@router.get("/analytics/funnel")
async def analytics_funnel(
    org_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ORG)),
    campaign_id: Optional[int] = Query(default=None),
    posting_id: Optional[int] = Query(default=None),
):
    """Stage-to-stage conversion. Gated at org-wide read (hiring_manager+),
    not the narrower campaign:read:assigned a plain recruiter holds."""
    _require_org(actor, org_id)
    return await _db(hdb.get_funnel, org_id, campaign_id, posting_id)


@router.get("/analytics/selection-rates")
async def analytics_selection_rates(
    org_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ORG)),
    segment_by: str = Query(default="source", pattern="^(source|experience_band)$"),
):
    """Disparate-impact-style selection-rate divergence. See hiring_db.get_selection_rates
    for the explicit, honest scope of what this is and is not."""
    _require_org(actor, org_id)
    try:
        result = await _db(hdb.get_selection_rates, org_id, segment_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result["flag_adverse_impact"]:
        audit.record_from_actor(
            actor, "analytics.adverse_impact_flagged",
            tier=audit.AuditTier.SECURITY,
            resource_org_id=org_id,
            detail={"segment_by": segment_by, "ratio": result["adverse_impact_ratio"]},
        )
    return result
