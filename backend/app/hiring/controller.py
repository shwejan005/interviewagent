"""
Recruiter-facing endpoints: campaigns, job postings, applicant pipeline.

Every endpoint requires an organization context (`X-Org-Id`) and a capability,
and every query is org-scoped in SQL as well as checked by `assert_tenant`.
The redundancy is deliberate: a route-layer check can be forgotten when a new
endpoint is added, whereas a query that cannot express a cross-tenant read is
structurally safe.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.candidate import repository as cdb, service as matching
from app.config import database as db
from app.evaluation.runner import AgentOutputError, run_screening
from app.hiring import repository as hdb
from app.hiring.dto import (
    CampaignRequest,
    CampaignMemberRequest,
    PostingRequest,
    PostingStatusRequest,
    PostingUpdateRequest,
    ReferralRequest,
    InterviewCreateRequest,
    TransitionRequest,
)
from app.shared import audit, notifications
from app.shared.authz import Actor, assert_tenant, requires
from app.shared.rbac import Capability, SystemRole

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


async def _require_campaign_access(actor: Actor, org_id: int, campaign_id: int) -> None:
    """Enforce tenant plus campaign assignment for non-org-wide roles."""
    _require_org(actor, org_id)
    if actor.has(Capability.CAMPAIGN_READ_ORG):
        return
    if not await _db(hdb.is_campaign_member, campaign_id, actor.user_id, org_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)


async def _campaign_id_for_posting(actor: Actor, org_id: int, posting_id: int) -> int:
    posting = await _db(hdb.get_posting, posting_id, org_id)
    if posting is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _require_campaign_access(actor, org_id, posting["campaign_id"])
    return posting["campaign_id"]


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
        hdb.create_campaign, org_id, req.name, req.description, actor.user_id,
        department=req.department, hiring_manager=req.hiring_manager,
        priority=req.priority, target_hires=req.target_hires,
        target_close_date=req.target_close_date,
    )
    await _db(hdb.assign_campaign_member, campaign_id, actor.user_id, actor.role or "RECRUITER")
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
    assigned_user_id = None if actor.has(Capability.CAMPAIGN_READ_ORG) else actor.user_id
    return {
        "campaigns": await _db(
            hdb.list_campaigns, org_id, limit, offset, assigned_user_id
        )
    }


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    org_id: int,
    campaign_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ASSIGNED)),
):
    await _require_campaign_access(actor, org_id, campaign_id)
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
    await _require_campaign_access(actor, org_id, campaign_id)
    if not await _db(hdb.update_campaign, campaign_id, org_id, **req.model_dump()):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "campaign.updated",
        actor_ip=_client_ip(request),
        resource_type="campaign", resource_id=campaign_id, resource_org_id=org_id,
    )
    return await _db(hdb.get_campaign, campaign_id, org_id)


@router.post("/campaigns/{campaign_id}/members", status_code=204)
async def assign_campaign_member(
    org_id: int,
    campaign_id: int,
    req: CampaignMemberRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    """Grant a tenant member access to one campaign."""
    await _require_campaign_access(actor, org_id, campaign_id)
    member = await _db(db.get_membership, req.user_id, org_id)
    if member is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _db(hdb.assign_campaign_member, campaign_id, req.user_id, req.member_role)
    audit.record_from_actor(
        actor,
        "campaign.member.assigned",
        actor_ip=_client_ip(request),
        resource_type="campaign",
        resource_id=campaign_id,
        resource_org_id=org_id,
        detail={"user_id": req.user_id, "member_role": req.member_role},
    )


# ── Job postings ─────────────────────────────────────────────────────


@router.post("/postings", status_code=201)
async def create_posting(
    org_id: int,
    req: PostingRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_CREATE)),
):
    """Create a posting in DRAFT. Publishing is a separate, audited action."""
    await _require_campaign_access(actor, org_id, req.campaign_id)

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
    if campaign_id is not None:
        await _require_campaign_access(actor, org_id, campaign_id)
    assigned_user_id = None if actor.has(Capability.CAMPAIGN_READ_ORG) else actor.user_id
    return {
        "postings": await _db(
            hdb.list_postings, org_id, campaign_id, status, limit, offset, assigned_user_id
        )
    }


@router.get("/postings/{posting_id}")
async def get_posting(
    org_id: int,
    posting_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ASSIGNED)),
):
    await _campaign_id_for_posting(actor, org_id, posting_id)
    posting = await _db(hdb.get_posting, posting_id, org_id)
    return posting


@router.patch("/postings/{posting_id}")
async def update_posting(
    org_id: int,
    posting_id: int,
    req: PostingUpdateRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    await _campaign_id_for_posting(actor, org_id, posting_id)
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
    await _campaign_id_for_posting(actor, org_id, posting_id)
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
    await _campaign_id_for_posting(actor, org_id, posting_id)
    if actor.role == str(SystemRole.INTERVIEWER):
        raise HTTPException(status_code=403, detail="Interviewers can only view assigned interviews.")

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
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])
    if (
        actor.role == str(SystemRole.INTERVIEWER)
        and not await _db(
            hdb.is_user_assigned_to_application, application_id, org_id, actor.user_id
        )
    ):
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
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])

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


@router.post("/applications/{application_id}/screen")
async def screen_application(
    org_id: int,
    application_id: int,
    request: Request,
    actor: Actor = Depends(
        requires(Capability.EVALUATION_CREATE, Capability.APPLICATION_ADVANCE)
    ),
):
    """Run the existing screening agent as an application-stage recommendation.

    This is intentionally human-reviewed: PASS moves to SCREENING, while
    BORDERLINE/FAIL moves to PENDING_REVIEW. No candidate is auto-rejected.
    """
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])
    if application.get("evaluation_id") is not None:
        raise HTTPException(status_code=409, detail="This application has already been screened.")
    if application["current_stage"] != str(hdb.ApplicationStage.APPLIED):
        raise HTTPException(status_code=409, detail="Only newly applied candidates can be screened.")

    profile = await _db(cdb.get_profile, application["profile_id"]) if application.get("profile_id") else None
    resume = (profile or {}).get("resume_text", "")
    if not resume:
        snapshot = application.get("profile_snapshot") or {}
        resume = json.dumps(snapshot, sort_keys=True)
    if not resume.strip():
        raise HTTPException(status_code=400, detail="Candidate has no resume or profile evidence to screen.")

    posting = await _db(hdb.get_posting, application["posting_id"], org_id)
    evaluation_id = await _db(
        db.create_evaluation,
        resume_text=resume,
        role=posting["title"],
        candidate_name=application.get("candidate_name", ""),
        org_id=org_id,
        owner_user_id=application["candidate_user_id"],
    )
    try:
        result = await run_screening(evaluation_id, resume, posting["title"])
    except AgentOutputError as exc:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="screening",
            round_number=1,
            verdict_json={"error": str(exc)},
            verdict_text=exc.raw_output,
            decision="INVALID_OUTPUT",
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The screening agent returned an invalid response. Retry the screening.",
        ) from exc

    await _db(
        db.save_verdict,
        evaluation_id=evaluation_id,
        agent_type="screening",
        round_number=1,
        verdict_json=result["verdict"],
        verdict_text=result["verdict_text"],
        score=result["score"],
        decision=result["decision"],
        confidence=result["confidence"],
    )
    if not await _db(hdb.attach_evaluation, application_id, org_id, evaluation_id):
        raise HTTPException(status_code=409, detail="Application changed while screening.")
    next_stage = (
        hdb.ApplicationStage.PENDING_REVIEW
        if result["decision"] in ("FAIL", "BORDERLINE")
        else hdb.ApplicationStage.TECHNICAL
    )
    await _db(
        hdb.transition_application,
        application_id,
        org_id,
        str(next_stage),
        actor.user_id,
        "Automated screening recommendation recorded.",
        True,
    )

    audit.record_from_actor(
        actor,
        "application.screened",
        actor_ip=_client_ip(request),
        resource_type="application",
        resource_id=application_id,
        resource_org_id=org_id,
        detail={"evaluation_id": evaluation_id, "decision": result["decision"]},
    )
    return {
        "application_id": application_id,
        "evaluation_id": evaluation_id,
        "decision": result["decision"],
        "recommendation": result["verdict"],
        "current_stage": str(next_stage),
        "human_review_required": result["decision"] in ("FAIL", "BORDERLINE"),
    }


@router.post("/applications/{application_id}/interviews", status_code=201)
async def schedule_interview(
    org_id: int,
    application_id: int,
    req: InterviewCreateRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.INTERVIEW_SCHEDULE)),
):
    """Schedule a candidate interview with explicit organization participants."""
    _require_org(actor, org_id)
    try:
        interview = await _db(
            hdb.create_interview,
            org_id,
            application_id,
            req.title,
            req.scheduled_start,
            req.scheduled_end,
            req.timezone,
            req.meeting_url,
            actor.user_id,
            req.interviewer_user_ids,
        )
    except hdb.DuplicateInterviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit.record_from_actor(
        actor,
        "interview.scheduled",
        actor_ip=_client_ip(request),
        resource_type="interview",
        resource_id=interview["id"],
        resource_org_id=org_id,
        detail={"application_id": application_id, "participant_count": len(interview["participants"])},
    )
    return interview


@router.get("/applications/{application_id}/interviews")
async def list_application_interviews(
    org_id: int,
    application_id: int,
    actor: Actor = Depends(requires(Capability.INTERVIEW_READ_ASSIGNED)),
):
    _require_org(actor, org_id)
    return {
        "interviews": await _db(
            hdb.list_interviews_for_application, application_id, org_id
        )
    }


@router.post("/interviews/{interview_id}/cancel")
async def cancel_scheduled_interview(
    org_id: int,
    interview_id: int,
    request: Request,
    actor: Actor = Depends(requires(Capability.INTERVIEW_SCHEDULE)),
):
    _require_org(actor, org_id)
    if not await _db(hdb.cancel_interview, interview_id, org_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor,
        "interview.cancelled",
        actor_ip=_client_ip(request),
        resource_type="interview",
        resource_id=interview_id,
        resource_org_id=org_id,
    )
    return {"interview_id": interview_id, "status": "CANCELLED"}


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
    referral = await _db(hdb.get_referral, referral_id, org_id)
    posting = await _db(hdb.get_posting, posting_id, org_id)
    delivery = await asyncio.to_thread(
        notifications.send_referral_email,
        str(req.candidate_email),
        actor.email,
        posting["title"],
        posting.get("org_name", "your organization"),
        req.note,
    )
    return {**referral, "email_delivery": delivery}


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


@router.get("/analytics/overview")
async def analytics_overview(
    org_id: int,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_READ_ORG)),
    days: int = Query(default=30, ge=7, le=180),
):
    """Dashboard-shaped aggregate: volume trend, stage mix, source mix,
    campaign/posting leaderboards, and time-to-hire."""
    _require_org(actor, org_id)
    return await _db(hdb.get_analytics_overview, org_id, days)


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
