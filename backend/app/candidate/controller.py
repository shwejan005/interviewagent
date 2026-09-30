"""
Candidate-facing endpoints: profile vault, job discovery, applications.

Every endpoint here operates on the caller's *own* data. There is no path by
which a candidate reads another candidate's profile or applications, because
every query is keyed on the authenticated user ID rather than on an ID taken
from the request.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.candidate import repository as cdb, service as matching
from app.config import database as db
from app.hiring import repository as hdb
from app.hiring.dto import (
    ApplyRequest,
    EducationRequest,
    ExperienceRequest,
    PreferencesRequest,
    ProfileUpsertRequest,
    SkillsRequest,
    VaultAnswerRequest,
)
from app.shared import audit
from app.shared.authz import Actor, current_actor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/me", tags=["candidate"])
jobs_router = APIRouter(prefix="/jobs", tags=["jobs"])

_NO_PROFILE = "No candidate profile yet. Create one with PUT /me/profile."
_NOT_FOUND = "Not found."


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _require_profile(actor: Actor) -> dict:
    profile = await _db(cdb.get_profile_by_user, actor.user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=_NO_PROFILE)
    return profile


# â”€â”€ Profile vault â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/profile")
async def get_my_profile(actor: Actor = Depends(current_actor)):
    """The complete vault in one call: profile, experience, education, skills,
    preferences, and saved answers."""
    profile = await _db(cdb.get_full_profile, actor.user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=_NO_PROFILE)
    return profile


@router.put("/profile")
async def upsert_my_profile(
    req: ProfileUpsertRequest,
    actor: Actor = Depends(current_actor),
):
    """Create or update the caller's profile. Idempotent."""
    existing = await _db(cdb.get_profile_by_user, actor.user_id)
    if existing is None:
        profile_id = await _db(cdb.create_profile, actor.user_id, **req.model_dump())
        # Consent is stamped at creation because the profile cannot be stored
        # without it. Version is recorded so a policy change is auditable.
        await _db(cdb.record_consent, profile_id, "v1")
        created = True
    else:
        profile_id = existing["id"]
        await _db(cdb.update_profile, profile_id, **req.model_dump())
        created = False

    audit.record_from_actor(
        actor,
        "profile.created" if created else "profile.updated",
        resource_type="candidate_profile",
        resource_id=profile_id,
    )
    return await _db(cdb.get_full_profile, actor.user_id)


@router.post("/profile/experience", status_code=201)
async def add_experience(req: ExperienceRequest, actor: Actor = Depends(current_actor)):
    profile = await _require_profile(actor)
    experience_id = await _db(cdb.add_experience, profile["id"], **req.model_dump())
    audit.record_from_actor(
        actor, "profile.experience.created", resource_type="work_experience",
        resource_id=experience_id,
    )
    return {"id": experience_id}


@router.delete("/profile/experience/{experience_id}", status_code=204)
async def delete_experience(experience_id: int, actor: Actor = Depends(current_actor)):
    profile = await _require_profile(actor)
    # Scoped by profile_id, so a crafted ID cannot delete another user's row.
    if not await _db(cdb.delete_experience, profile["id"], experience_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    audit.record_from_actor(
        actor, "profile.experience.deleted", resource_type="work_experience",
        resource_id=experience_id,
    )


@router.post("/profile/education", status_code=201)
async def add_education(req: EducationRequest, actor: Actor = Depends(current_actor)):
    profile = await _require_profile(actor)
    education_id = await _db(cdb.add_education, profile["id"], **req.model_dump())
    audit.record_from_actor(
        actor, "profile.education.created", resource_type="education_entry",
        resource_id=education_id,
    )
    return {"id": education_id}


@router.put("/profile/skills")
async def set_skills(req: SkillsRequest, actor: Actor = Depends(current_actor)):
    """Replace the claimed-skill set.

    Skills previously verified by in-platform performance keep their verified
    flag â€” a profile edit must not be able to fabricate or erase that signal.
    """
    profile = await _require_profile(actor)
    await _db(cdb.set_skills, profile["id"], [s.model_dump() for s in req.skills])
    audit.record_from_actor(actor, "profile.skills.updated", resource_type="candidate_profile", resource_id=profile["id"])
    return {"skills": await _db(cdb.list_skills, profile["id"])}


@router.put("/profile/preferences")
async def set_preferences(req: PreferencesRequest, actor: Actor = Depends(current_actor)):
    profile = await _require_profile(actor)
    if req.min_salary is not None and req.max_salary is not None and req.min_salary > req.max_salary:
        raise HTTPException(status_code=400, detail="min_salary cannot exceed max_salary.")
    await _db(cdb.set_preferences, profile["id"], **req.model_dump())
    audit.record_from_actor(actor, "profile.preferences.updated", resource_type="candidate_profile", resource_id=profile["id"])
    return await _db(cdb.get_preferences, profile["id"])


@router.put("/profile/vault")
async def upsert_vault_answer(req: VaultAnswerRequest, actor: Actor = Depends(current_actor)):
    """Save a reusable answer so it never has to be typed again."""
    profile = await _require_profile(actor)
    await _db(
        cdb.upsert_vault_answer,
        profile["id"], req.question_key, req.answer_text, req.question_text,
    )
    audit.record_from_actor(
        actor, "profile.answer_vault.updated", resource_type="answer_vault_entry",
        resource_id=req.question_key,
    )
    return {"question_key": req.question_key}


# â”€â”€ Job discovery â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@jobs_router.get("")
async def search_jobs(
    q: Optional[str] = Query(default=None, max_length=200),
    location: Optional[str] = Query(default=None, max_length=200),
    remote_policy: Optional[str] = Query(default=None, pattern="^(REMOTE|HYBRID|ONSITE)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Public job board. Published postings only, across all organizations.

    Unauthenticated by design â€” job listings are public, and requiring an
    account to browse would defeat the acquisition funnel.
    """
    return await _db(
        hdb.search_published_postings,
        query=q, location=location, remote_policy=remote_policy,
        limit=limit, offset=offset,
    )


@jobs_router.get("/{posting_id}")
async def get_job(posting_id: int):
    posting = await _db(hdb.get_published_posting, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return posting


@jobs_router.get("/{posting_id}/application-form")
async def get_application_form(posting_id: int, actor: Actor = Depends(current_actor)):
    """The posting's questions, pre-filled from the caller's answer vault.

    This is the mechanism behind "fill it once": the client renders the
    returned questions with `prefilled_answer` already populated, and the
    candidate only types answers to questions they have never seen before.
    """
    posting = await _db(hdb.get_published_posting, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    profile = await _db(cdb.get_profile_by_user, actor.user_id)
    vault = await _db(cdb.get_vault_answers, profile["id"]) if profile else {}

    questions = [
        {
            **question,
            "prefilled_answer": vault.get(question.get("key", ""), ""),
            "is_prefilled": question.get("key", "") in vault,
        }
        for question in posting.get("screening_questions", [])
    ]
    return {
        "posting_id": posting_id,
        "title": posting["title"],
        "questions": questions,
        "profile_complete": profile is not None,
        "unanswered_count": sum(1 for q in questions if not q["is_prefilled"]),
    }


# â”€â”€ Applications â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@jobs_router.post("/{posting_id}/apply", status_code=201)
async def apply_to_job(
    posting_id: int,
    req: ApplyRequest,
    request: Request,
    actor: Actor = Depends(current_actor),
):
    """Submit an application, auto-filling from the vault."""
    posting = await _db(hdb.get_published_posting, posting_id)
    if posting is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    profile = await _db(cdb.get_profile_by_user, actor.user_id)
    if profile is None:
        raise HTTPException(
            status_code=400,
            detail="Create your profile before applying. See PUT /me/profile.",
        )

    vault = await _db(cdb.get_vault_answers, profile["id"])
    supplied = {a.question_key: a for a in req.answers}

    # Required questions must be answerable from the vault or this request.
    missing = [
        q["key"] for q in posting.get("screening_questions", [])
        if q.get("required", True)
        and q["key"] not in supplied
        and not vault.get(q["key"])
    ]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required answers: {missing}",
        )

    answers = []
    for question in posting.get("screening_questions", []):
        key = question["key"]
        if key in supplied:
            text = supplied[key].answer_text
        else:
            text = vault.get(key, "")
        answers.append({
            "question_key": key,
            "question_text": question.get("text", ""),
            "answer_text": text,
        })

    snapshot = await _db(cdb.build_application_snapshot, actor.user_id)

    try:
        application_id = await _db(
            hdb.create_application,
            org_id=posting["org_id"],
            posting_id=posting_id,
            candidate_user_id=actor.user_id,
            profile_id=profile["id"],
            snapshot=snapshot,
            answers=answers,
        )
    except hdb.DuplicateApplicationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Newly answered questions go back into the vault, so the next application
    # is cheaper than this one. This is the compounding value of the vault.
    if req.save_answers_to_vault:
        for answer in req.answers:
            await _db(
                cdb.upsert_vault_answer,
                profile["id"], answer.question_key, answer.answer_text, answer.question_text,
            )

    audit.record_from_actor(
        actor,
        "application.submitted",
        actor_ip=_client_ip(request),
        resource_type="application",
        resource_id=application_id,
        resource_org_id=posting["org_id"],
        detail={"posting_id": posting_id},
    )
    return {"application_id": application_id, "status": "APPLIED"}


@router.get("/applications")
async def list_my_applications(
    actor: Actor = Depends(current_actor),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """The caller's application tracker."""
    applications = await _db(
        hdb.list_applications_for_candidate, actor.user_id, limit, offset
    )
    return {"applications": applications, "limit": limit, "offset": offset}


@router.get("/interviews")
async def list_my_interviews(
    actor: Actor = Depends(current_actor),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Candidate and interviewer agenda, scoped by participant identity."""
    return {
        "interviews": await _db(hdb.list_interviews_for_user, actor.user_id, limit, offset),
        "limit": limit,
        "offset": offset,
    }


@router.get("/applications/{application_id}")
async def get_my_application(application_id: int, actor: Actor = Depends(current_actor)):
    """Detail plus timeline for one of the caller's own applications."""
    application = await _db(hdb.get_application, application_id)
    if application is None or application["candidate_user_id"] != actor.user_id:
        # Same 404 for "does not exist" and "belongs to someone else".
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    events = await _db(hdb.list_application_events, application_id)
    return {
        "application": application,
        "timeline": [
            {
                "event_type": e["event_type"],
                "to_stage": e["to_stage"],
                "created_at": e["created_at"],
                # Internal recruiter notes are deliberately not exposed here.
            }
            for e in events
        ],
    }


@router.post("/applications/{application_id}/withdraw", status_code=200)
async def withdraw_application(
    application_id: int,
    request: Request,
    actor: Actor = Depends(current_actor),
):
    if not await _db(hdb.withdraw_application, application_id, actor.user_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    audit.record_from_actor(
        actor,
        "application.withdrawn",
        actor_ip=_client_ip(request),
        resource_type="application",
        resource_id=application_id,
    )
    return {"application_id": application_id, "status": "WITHDRAWN"}


# ── Recommendations ──────────────────────────────────────────────────


@router.get("/recommended-jobs")
async def recommended_jobs(
    actor: Actor = Depends(current_actor),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Published postings ranked against the caller's profile, with an
    explanation for every score. See matching.py for the scoring model."""
    results = await _db(matching.rank_jobs_for_candidate, actor.user_id, limit)
    return {"recommendations": results}


# ── Referrals ────────────────────────────────────────────────────────


@router.get("/referrals")
async def list_my_referrals(actor: Actor = Depends(current_actor)):
    """Referrals sent to the caller's email address, across every organization."""
    return {"referrals": await _db(hdb.list_referrals_for_candidate, actor.email)}


@router.post("/referrals/{referral_id}/apply", status_code=201)
async def apply_via_referral(
    referral_id: int,
    req: ApplyRequest,
    request: Request,
    actor: Actor = Depends(current_actor),
):
    """Accept a referral by applying through it — one action, not two."""
    referral = await _db(hdb.get_referral, referral_id)
    if referral is None or referral["candidate_email"] != db.normalize_email(actor.email):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    if referral["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="This referral has already been responded to.")

    apply_response = await apply_to_job(referral["posting_id"], req, request, actor)
    await _db(
        hdb.respond_to_referral, referral_id, "APPLIED", apply_response["application_id"]
    )
    audit.record_from_actor(
        actor, "referral.accepted",
        actor_ip=_client_ip(request),
        resource_type="referral", resource_id=referral_id, resource_org_id=referral["org_id"],
    )
    return apply_response


@router.post("/referrals/{referral_id}/decline", status_code=200)
async def decline_referral(
    referral_id: int,
    request: Request,
    actor: Actor = Depends(current_actor),
):
    referral = await _db(hdb.get_referral, referral_id)
    if referral is None or referral["candidate_email"] != db.normalize_email(actor.email):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    if not await _db(hdb.respond_to_referral, referral_id, "DECLINED"):
        raise HTTPException(status_code=409, detail="This referral has already been responded to.")

    audit.record_from_actor(
        actor, "referral.declined",
        actor_ip=_client_ip(request),
        resource_type="referral", resource_id=referral_id, resource_org_id=referral["org_id"],
    )
    return {"referral_id": referral_id, "status": "DECLINED"}

