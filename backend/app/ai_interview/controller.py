"""Authenticated candidate and recruiter endpoints for application AI interviews."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.ai_interview import repository as interview_db
from app.ai_interview.dto import (
    CandidateInterviewResponse,
    CandidateInterviewTurn,
    RequestTextAccommodation,
    SaveInterviewDraftRequest,
    ScreeningOverrideRequest,
    StartInterviewRequest,
    SubmitInterviewAnswerRequest,
)
from app.ai_interview.service import build_question_plan as ai_interview_build_plan
from app.hiring import repository as hdb
from app.hiring.controller import _campaign_id_for_posting, _require_org
from app.shared import audit
from app.shared.authz import Actor, current_actor, requires
from app.shared.rbac import Capability

candidate_router = APIRouter(prefix="/me/applications", tags=["candidate-ai-interview"])
recruiter_router = APIRouter(prefix="/orgs/{org_id}/applications", tags=["recruiter-ai-interview"])
_NOT_FOUND = "Not found."


def _db(func, *args, **kwargs):
    return asyncio.to_thread(func, *args, **kwargs)


def _candidate_response(application_id: int, view: dict, message: str = "") -> CandidateInterviewResponse:
    turns = [CandidateInterviewTurn(**turn) for turn in view["turns"]]
    current = next((turn for turn in turns if turn.id == view.get("current_question_id")), None)
    status = view["status"]
    if not message:
        message = {
            "SCREENING_QUEUED": "Your application is in the screening queue.",
            "SCREENING": "Your application is being screened.",
            "INTERVIEW_READY": "Your AI interview is ready. Review the notice and choose when to start.",
            "INTERVIEW_IN_PROGRESS": "Your AI interview is in progress.",
            "ANSWER_PROCESSING": "Your answer is saved and being evaluated.",
            "REPORT_PENDING": "Your interview is complete and the report is being prepared.",
            "REPORT_READY": "Your interview report is available to the hiring team.",
            "PENDING_REVIEW": "Your application is awaiting human review.",
            "REVIEW_REQUIRED": "Your application needs additional review. No action is required from you right now.",
            "EXPIRED": "This AI interview invitation expired. Contact the hiring team to request a new invitation.",
            "CANCELLED": "This AI interview is no longer active.",
        }.get(status, "Your application interview status is available below.")
    return CandidateInterviewResponse(
        application_id=application_id,
        status=status,
        phase=view["phase"],
        rubric_version=view["rubric_version"],
        role_level=view["role_level"],
        consent_required=status == "INTERVIEW_READY",
        candidate_notice_version=view["candidate_notice_version"],
        modality=view.get("modality", "TEXT"),
        invitation_expires_at=view.get("invitation_expires_at"),
        current_question=current,
        turns=turns,
        message=message,
    )


async def _owned_application(application_id: int, actor: Actor) -> dict:
    application = await _db(hdb.get_application, application_id)
    if application is None or int(application["candidate_user_id"]) != actor.user_id:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return application


async def _candidate_view(application_id: int, actor: Actor) -> dict:
    await _owned_application(application_id, actor)
    view = await _db(interview_db.get_candidate_view, application_id, actor.user_id)
    if view is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return view


@candidate_router.get("/{application_id}/ai-interview", response_model=CandidateInterviewResponse)
async def get_candidate_ai_interview(application_id: int, actor: Actor = Depends(current_actor)):
    view = await _candidate_view(application_id, actor)
    return _candidate_response(application_id, view)


@candidate_router.put("/{application_id}/ai-interview/draft")
async def save_candidate_ai_interview_draft(
    application_id: int,
    req: SaveInterviewDraftRequest,
    actor: Actor = Depends(current_actor),
):
    await _owned_application(application_id, actor)
    try:
        return await _db(
            interview_db.save_answer_draft,
            application_id,
            actor.user_id,
            req.turn_id,
            req.draft_answer_text,
        )
    except interview_db.InterviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except interview_db.InterviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@candidate_router.post("/{application_id}/ai-interview/start", response_model=CandidateInterviewResponse)
async def start_candidate_ai_interview(
    application_id: int,
    req: StartInterviewRequest,
    actor: Actor = Depends(current_actor),
):
    view = await _candidate_view(application_id, actor)
    if not req.accepted:
        raise HTTPException(status_code=400, detail="You must acknowledge the AI interview notice before starting.")
    if req.notice_version != view["candidate_notice_version"]:
        raise HTTPException(status_code=409, detail="The interview notice changed. Review the current notice before starting.")
    try:
        started = await _db(
            interview_db.start_interview,
            application_id,
            actor.user_id,
            req.notice_version,
            req.modality,
        )
    except interview_db.InterviewConflictError as exc:
        if "invitation has expired" in str(exc).lower():
            return _candidate_response(
                application_id,
                await _candidate_view(application_id, actor),
                "This AI interview invitation expired. Contact the hiring team to request a new invitation.",
            )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if started is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    updated = await _candidate_view(application_id, actor)
    return _candidate_response(application_id, updated, "Your interview has started. Answer one question at a time; your progress is saved.")


@candidate_router.post("/{application_id}/ai-interview/text-accommodation")
async def request_candidate_text_accommodation(
    application_id: int,
    req: RequestTextAccommodation,
    actor: Actor = Depends(current_actor),
):
    application = await _owned_application(application_id, actor)
    view = await _candidate_view(application_id, actor)
    if req.notice_version != view["candidate_notice_version"]:
        raise HTTPException(status_code=409, detail="The interview notice changed. Review the current notice before changing modality.")
    try:
        result = await _db(
            interview_db.switch_to_text_accommodation,
            application_id,
            actor.user_id,
            req.notice_version,
        )
    except interview_db.InterviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except interview_db.InterviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result["duplicate"]:
        audit.record_from_actor(
            actor,
            "application.ai_interview_text_accommodation_selected",
            resource_type="application",
            resource_id=application_id,
            resource_org_id=application["org_id"],
            detail={"notice_version": req.notice_version},
        )
    return {"application_id": application_id, **result}


@candidate_router.post("/{application_id}/ai-interview/answers", status_code=202)
async def submit_candidate_ai_interview_answer(
    application_id: int,
    req: SubmitInterviewAnswerRequest,
    actor: Actor = Depends(current_actor),
):
    await _owned_application(application_id, actor)
    try:
        return await _db(
            interview_db.submit_answer,
            application_id,
            actor.user_id,
            req.turn_id,
            req.answer.strip(),
            req.source,
        )
    except interview_db.InterviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except interview_db.InterviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@recruiter_router.get("/{application_id}/ai-interview")
async def get_recruiter_ai_interview(
    org_id: int,
    application_id: int,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ)),
):
    _require_org(actor, org_id)
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])
    status = await _db(interview_db.get_recruiter_view, application_id, org_id)
    if status is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    interview = await _db(interview_db.get_internal, application_id, org_id)
    turns = await _db(interview_db.list_turns_internal, int(interview["id"])) if interview else []
    return {
        **status,
        "turns": turns,
        "role_level": (interview["policy_snapshot"].get("interview_settings") or {}).get("role_level", "MID") if interview else "MID",
    }


@recruiter_router.post("/{application_id}/ai-interview/approve-screening-exception")
async def approve_screening_exception(
    org_id: int,
    application_id: int,
    req: ScreeningOverrideRequest,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ, Capability.APPLICATION_ADVANCE)),
):
    _require_org(actor, org_id)
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])
    run = await _db(interview_db.get_internal, application_id, org_id)
    if run is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    try:
        plan = await _db(ai_interview_build_plan, run["policy_snapshot"], run["role"])
        result = await _db(
            interview_db.approve_screening_exception,
            application_id,
            org_id,
            actor.user_id,
            req.reason,
            plan,
        )
    except interview_db.InterviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except interview_db.InterviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit.record_from_actor(
        actor,
        "application.ai_interview_screening_exception_approved",
        resource_type="application",
        resource_id=application_id,
        resource_org_id=org_id,
        detail={"reason": req.reason.strip(), "interview_id": result["interview_id"]},
    )
    return {"application_id": application_id, **result}


@recruiter_router.post("/{application_id}/ai-interview/reinvite")
async def reinvite_expired_ai_interview(
    org_id: int,
    application_id: int,
    req: ScreeningOverrideRequest,
    request: Request,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ, Capability.APPLICATION_ADVANCE)),
):
    _require_org(actor, org_id)
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])
    try:
        result = await _db(
            interview_db.reinvite_expired_interview,
            application_id,
            org_id,
            actor.user_id,
            req.reason,
        )
    except interview_db.InterviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND) from exc
    except interview_db.InterviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit.record_from_actor(
        actor,
        "application.ai_interview_reinvited",
        actor_ip=request.client.host if request.client else None,
        resource_type="application",
        resource_id=application_id,
        resource_org_id=org_id,
        detail={"reason": req.reason.strip(), "invitation_round": result["invitation_round"]},
    )
    return result
