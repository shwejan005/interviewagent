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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.ai_interview import repository as interview_db
from app.candidate import repository as cdb, service as matching
from app.config import database as db
from app.evaluation.runner import AgentOutputError, run_screening
from app.hiring import repository as hdb
from app.hiring.dto import (
    CampaignRequest,
    CampaignUpdateRequest,
    CampaignMemberRequest,
    PostingRequest,
    PostingStatusRequest,
    PostingUpdateRequest,
    ReferralRequest,
    InterviewCreateRequest,
    InterviewScorecardRequest,
    ApplicationDecisionRequest,
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


async def _enqueue_interview_notifications(interview: dict, application_id: int, org_id: int, posting_title: str) -> None:
    for participant in interview.get("participants", []):
        await _db(
            db.enqueue_job,
            "human_interview_scheduled_notification",
            {
                "interview_id": interview["id"],
                "application_id": application_id,
                "org_id": org_id,
                "user_id": int(participant["user_id"]),
                "participant_role": participant["participant_role"],
                "interview_title": interview["title"],
                "posting_title": posting_title,
                "scheduled_start": interview["scheduled_start"],
            },
            idempotency_key=f"human-interview-scheduled:{interview['id']}:{participant['user_id']}",
            tenant_key=f"org:{org_id}",
        )


async def _application_interview_history(application_id: int, org_id: int, viewer_user_id: int) -> list[dict]:
    interviews = await _db(hdb.list_interviews_for_application, application_id, org_id)
    for interview in interviews:
        assigned = any(
            int(participant["user_id"]) == viewer_user_id and participant["participant_role"] == "INTERVIEWER"
            for participant in interview.get("participants", [])
        )
        interview["scorecard_summary"] = await _db(
            hdb.get_interview_scorecards,
            int(interview["id"]),
            org_id,
            viewer_user_id,
            assigned_interviewer=assigned,
        )
    return interviews


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
    include_archived: bool = Query(default=False),
):
    _require_org(actor, org_id)
    assigned_user_id = None if actor.has(Capability.CAMPAIGN_READ_ORG) else actor.user_id
    return {
        "campaigns": await _db(
            hdb.list_campaigns, org_id, limit, offset, assigned_user_id, include_archived
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
    req: CampaignUpdateRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    await _require_campaign_access(actor, org_id, campaign_id)
    payload = req.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=422, detail="Provide at least one campaign field to update.")
    try:
        updated = await _db(hdb.update_campaign, campaign_id, org_id, **payload)
    except hdb.HiringLifecycleConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "campaign.updated",
        actor_ip=_client_ip(request),
        resource_type="campaign", resource_id=campaign_id, resource_org_id=org_id,
        detail={"fields": sorted(payload.keys()), "status": payload.get("status")},
    )
    return await _db(hdb.get_campaign, campaign_id, org_id)


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def archive_campaign(
    org_id: int,
    campaign_id: int,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    """Archive a campaign without deleting its postings or applicant history."""
    await _require_campaign_access(actor, org_id, campaign_id)
    if not await _db(hdb.archive_campaign, campaign_id, org_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "campaign.archived",
        actor_ip=_client_ip(request),
        resource_type="campaign", resource_id=campaign_id, resource_org_id=org_id,
    )


@router.post("/campaigns/{campaign_id}/restore")
async def restore_campaign(
    org_id: int,
    campaign_id: int,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    """Restore visibility as CLOSED; roles remain closed until reopened individually."""
    await _require_campaign_access(actor, org_id, campaign_id)
    if not await _db(hdb.restore_campaign, campaign_id, org_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "campaign.restored",
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
    campaign = await _db(hdb.get_campaign, req.campaign_id, org_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if campaign.get("deleted_at") is not None or campaign.get("status") != "ACTIVE":
        raise HTTPException(status_code=409, detail="Reopen the campaign before adding a role.")

    if (req.min_experience is not None and req.max_experience is not None
            and req.min_experience > req.max_experience):
        raise HTTPException(status_code=400, detail="min_experience cannot exceed max_experience.")
    if req.salary_min is not None and req.salary_max is not None and req.salary_min > req.salary_max:
        raise HTTPException(status_code=400, detail="salary_min cannot exceed salary_max.")

    payload = req.model_dump()
    payload["screening_questions"] = [q.model_dump() for q in req.screening_questions]
    campaign_id = payload.pop("campaign_id")
    title = payload.pop("title")

    try:
        posting_id = await _db(
            hdb.create_posting, org_id, campaign_id, title, actor.user_id, **payload
        )
    except hdb.HiringLifecycleConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    include_archived: bool = Query(default=False),
):
    _require_org(actor, org_id)
    if campaign_id is not None:
        await _require_campaign_access(actor, org_id, campaign_id)
    assigned_user_id = None if actor.has(Capability.CAMPAIGN_READ_ORG) else actor.user_id
    return {
        "postings": await _db(
            hdb.list_postings, org_id, campaign_id, status, limit, offset, assigned_user_id,
            include_archived,
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
    current = await _db(hdb.get_posting, posting_id, org_id)
    if current is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if current.get("deleted_at") is not None:
        raise HTTPException(status_code=409, detail="Restore this archived role before editing it.")
    payload = req.model_dump(exclude_unset=True)
    if req.screening_questions is not None:
        payload["screening_questions"] = [q.model_dump() for q in req.screening_questions]

    min_experience = payload.get("min_experience", current.get("min_experience"))
    max_experience = payload.get("max_experience", current.get("max_experience"))
    if min_experience is not None and max_experience is not None and min_experience > max_experience:
        raise HTTPException(status_code=400, detail="min_experience cannot exceed max_experience.")
    salary_min = payload.get("salary_min", current.get("salary_min"))
    salary_max = payload.get("salary_max", current.get("salary_max"))
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise HTTPException(status_code=400, detail="salary_min cannot exceed salary_max.")

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
    campaign_id = await _campaign_id_for_posting(actor, org_id, posting_id)
    posting = await _db(hdb.get_posting, posting_id, org_id)
    if posting is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if posting.get("deleted_at") is not None:
        raise HTTPException(status_code=409, detail="Restore this archived role before changing its status.")
    campaign = await _db(hdb.get_campaign, campaign_id, org_id)
    if req.status == "PUBLISHED" and campaign and (
        campaign.get("deleted_at") is not None or campaign.get("status") != "ACTIVE"
    ):
        raise HTTPException(status_code=409, detail="Reopen the campaign before publishing this role.")
    try:
        updated = await _db(hdb.set_posting_status, posting_id, org_id, req.status)
    except hdb.HiringLifecycleConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    audit.record_from_actor(
        actor, f"posting.{req.status.casefold()}",
        actor_ip=_client_ip(request),
        resource_type="job_posting", resource_id=posting_id, resource_org_id=org_id,
    )
    return await _db(hdb.get_posting, posting_id, org_id)


@router.delete("/postings/{posting_id}", status_code=204)
async def archive_posting(
    org_id: int,
    posting_id: int,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    """Archive a role while preserving its applications, reports, and audit history."""
    await _campaign_id_for_posting(actor, org_id, posting_id)
    if not await _db(hdb.archive_posting, posting_id, org_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "posting.archived",
        actor_ip=_client_ip(request),
        resource_type="job_posting", resource_id=posting_id, resource_org_id=org_id,
    )


@router.post("/postings/{posting_id}/restore")
async def restore_posting(
    org_id: int,
    posting_id: int,
    request: Request,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    """Restore a role without automatically reopening or republishing it."""
    await _campaign_id_for_posting(actor, org_id, posting_id)
    try:
        restored = await _db(hdb.restore_posting, posting_id, org_id)
    except hdb.HiringLifecycleConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not restored:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "posting.restored",
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
        "interviews": await _application_interview_history(application_id, org_id, actor.user_id),
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
    if req.to_stage == str(hdb.ApplicationStage.REJECTED) and len(req.note.strip()) < 10:
        raise HTTPException(status_code=422, detail="Please provide a rejection reason of at least 10 characters.")

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


def _validate_report_decision(req: ApplicationDecisionRequest, actor: Actor, suggested_action: str) -> str:
    reason = req.reason.strip()
    if req.action in {"HOLD", "REJECT"} and len(reason) < 10:
        raise HTTPException(status_code=422, detail="Please provide a decision reason of at least 10 characters.")
    if req.action == "PROMOTE" and suggested_action != "PROMOTE" and len(reason) < 10:
        raise HTTPException(status_code=422, detail="A reason is required to go against the report's suggested action.")
    if req.action == "REJECT" and not actor.has(Capability.APPLICATION_REJECT):
        raise HTTPException(status_code=403, detail="You do not have permission to reject applications.")
    return reason


def _report_decision_audit(action: str) -> tuple[str, audit.AuditTier, str | None]:
    if action == "REJECT":
        return "application.rejected", audit.AuditTier.SECURITY, str(hdb.ApplicationStage.REJECTED)
    if action == "PROMOTE":
        return "application.promoted_after_ai_report", audit.AuditTier.MUTATION, None
    return "application.held_after_ai_report", audit.AuditTier.MUTATION, None


async def _application_report_for_decision(org_id: int, application_id: int, actor: Actor) -> tuple[dict, object]:
    _require_org(actor, org_id)
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])
    if application["current_stage"] != str(hdb.ApplicationStage.PENDING_REVIEW):
        raise HTTPException(status_code=409, detail="This application is not awaiting a report decision.")
    from app.interview_criteria.service import ReportService

    report = await _db(ReportService().get, application_id)
    if report is None:
        raise HTTPException(status_code=409, detail="An interview report is required before this decision.")
    return application, report


async def _effective_report_action(report: object, application_id: int, org_id: int, viewer_user_id: int) -> str:
    interviews = await _db(hdb.list_interviews_for_application, application_id, org_id)
    completed = sorted(
        (interview for interview in interviews if interview.get("status") == "COMPLETED"),
        key=lambda interview: str(interview.get("scheduled_start") or ""),
        reverse=True,
    )
    if completed:
        panel = await _db(
            hdb.get_interview_scorecards,
            int(completed[0]["id"]),
            org_id,
            viewer_user_id,
            assigned_interviewer=False,
        )
        if panel["complete"] and panel["scorecards"]:
            return "PROMOTE" if all(card["recommendation"] == "ADVANCE" for card in panel["scorecards"]) else "HOLD"
    return ((getattr(report, "interview_details", {}) or {}).get("fit_nudge") or {}).get("suggested_action", "HOLD")


def _scheduled_round_payload(req: ApplicationDecisionRequest, actor: Actor) -> dict | None:
    if req.action != "PROMOTE" or req.target_stage == "OFFER":
        return None
    if not req.scheduled_start or not req.scheduled_end:
        raise HTTPException(status_code=422, detail="Choose a time for the next human interview when promoting the candidate.")
    parsed_start = hdb._parse_ts(req.scheduled_start)
    if parsed_start is None or parsed_start <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Choose a future start time for the next human interview.")
    return {
        "title": f"{req.target_stage.replace('_', ' ').title()} interview",
        "scheduled_start": req.scheduled_start,
        "scheduled_end": req.scheduled_end,
        "timezone_name": req.timezone,
        "meeting_url": "",
        "interviewer_user_ids": req.interviewer_user_ids or [actor.user_id],
    }


async def _persist_human_decision(
    application_id: int,
    org_id: int,
    actor: Actor,
    req: ApplicationDecisionRequest,
    reason: str,
    target_stage: str | None,
    scheduled_interview: dict | None,
) -> dict:
    try:
        if req.action == "HOLD":
            return await _db(hdb.record_application_hold, application_id, org_id, actor.user_id, reason)
        if req.action == "PROMOTE" and req.target_stage == "OFFER":
            return await _db(hdb.record_application_offer, application_id, org_id, actor.user_id, reason)
        return await _db(
            hdb.transition_application,
            application_id,
            org_id,
            str(target_stage),
            actor.user_id,
            reason,
            False,
            scheduled_interview,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except (hdb.InvalidTransitionError, hdb.DuplicateInterviewError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/applications/{application_id}/decision")
async def decide_application(
    org_id: int,
    application_id: int,
    req: ApplicationDecisionRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.APPLICATION_ADVANCE)),
):
    """Record the recruiter's explicit human decision after an AI report."""
    application, report = await _application_report_for_decision(org_id, application_id, actor)
    fit_nudge = (report.interview_details or {}).get("fit_nudge") or {}
    suggested_action = await _effective_report_action(report, application_id, org_id, actor.user_id)
    reason = _validate_report_decision(req, actor, suggested_action)
    audit_action, audit_tier, rejection_stage = _report_decision_audit(req.action)
    target_stage = rejection_stage or req.target_stage
    scheduled_interview = _scheduled_round_payload(req, actor)
    result = await _persist_human_decision(
        application_id, org_id, actor, req, reason, target_stage, scheduled_interview,
    )

    audit.record_from_actor(
        actor,
        audit_action,
        tier=audit_tier,
        actor_ip=_client_ip(request),
        resource_type="application",
        resource_id=application_id,
        resource_org_id=org_id,
        detail={"action": req.action, "target_stage": target_stage, "reason": reason, "fit_band": fit_nudge.get("band"), "suggested_action": suggested_action},
    )
    if result.get("interview_id") is not None:
        scheduled = await _db(hdb.get_interview, result["interview_id"], org_id)
        if scheduled is not None:
            await _enqueue_interview_notifications(scheduled, application_id, org_id, application.get("posting_title", "this role"))
    return {**result, "action": req.action}


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
    if application.get("ai_interview_status"):
        raise HTTPException(status_code=409, detail="Application screening is automatic; use the application pipeline status and review tools.")
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
    if result["decision"] in ("FAIL", "BORDERLINE"):
        next_stage = hdb.ApplicationStage.PENDING_REVIEW
        await _db(
            hdb.transition_application,
            application_id,
            org_id,
            str(next_stage),
            actor.user_id,
            "Automated screening recommendation recorded.",
            True,
        )
    else:
        # The legacy screening adapter is retained for older evaluations. Its
        # valid stage path is APPLIED -> SCREENING -> TECHNICAL, not the
        # invalid direct APPLIED -> TECHNICAL transition.
        await _db(
            hdb.transition_application,
            application_id,
            org_id,
            str(hdb.ApplicationStage.SCREENING),
            actor.user_id,
            "Legacy screening recommendation recorded.",
            True,
        )
        next_stage = hdb.ApplicationStage.TECHNICAL
        await _db(
            hdb.transition_application,
            application_id,
            org_id,
            str(next_stage),
            actor.user_id,
            "Legacy screening passed; technical stage opened.",
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
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])
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

    application = await _db(hdb.get_application, application_id, org_id)
    await _enqueue_interview_notifications(
        interview,
        application_id,
        org_id,
        (application or {}).get("posting_title", req.title),
    )

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
        "interviews": await _application_interview_history(application_id, org_id, actor.user_id)
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


@router.post("/interviews/{interview_id}/scorecard")
async def submit_human_interview_scorecard(
    org_id: int,
    interview_id: int,
    req: InterviewScorecardRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.INTERVIEW_CONDUCT)),
):
    _require_org(actor, org_id)
    try:
        result = await _db(
            hdb.submit_interview_scorecard,
            interview_id,
            org_id,
            actor.user_id,
            ratings=[rating.model_dump() for rating in req.ratings],
            recommendation=req.recommendation,
            notes=req.notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except hdb.InterviewScorecardConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record_from_actor(
        actor,
        "interview.scorecard_submitted",
        actor_ip=_client_ip(request),
        resource_type="interview",
        resource_id=interview_id,
        resource_org_id=org_id,
        detail={"recommendation": req.recommendation, "complete": result["complete"]},
    )
    if result["complete"]:
        interview = await _db(hdb.get_interview, interview_id, org_id)
        await _db(
            db.enqueue_job,
            "human_interview_scorecards_ready_notification",
            {"interview_id": interview_id, "application_id": interview["application_id"], "org_id": org_id},
            idempotency_key=f"human-interview-scorecards-ready:{interview_id}",
            tenant_key=f"org:{org_id}",
        )
    return result


@router.get("/interviews/{interview_id}/scorecards")
async def get_human_interview_scorecards(
    org_id: int,
    interview_id: int,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ)),
):
    _require_org(actor, org_id)
    interview = await _db(hdb.get_interview, interview_id, org_id)
    if interview is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    is_assigned_interviewer = any(
        int(participant["user_id"]) == actor.user_id and participant["participant_role"] == "INTERVIEWER"
        for participant in interview.get("participants", [])
    )
    if actor.role == str(SystemRole.INTERVIEWER) and not is_assigned_interviewer:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if not is_assigned_interviewer:
        await _campaign_id_for_posting(actor, org_id, interview["posting_id"])
    from app.interview_criteria.service import ReportService

    ai_status = await _db(interview_db.get_recruiter_view, interview["application_id"], org_id)
    ai_report = await _db(ReportService().get, interview["application_id"])
    interview_evidence = (ai_report.interview_details or {}).get("interview", {}).get("turns", []) if ai_report else []
    return await _db(
        hdb.get_interview_scorecards,
        interview_id,
        org_id,
        actor.user_id,
        assigned_interviewer=is_assigned_interviewer,
        interview_evidence=interview_evidence,
        screening_evidence=(ai_status or {}).get("screening_result", {}).get("evidence", []),
    )


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
