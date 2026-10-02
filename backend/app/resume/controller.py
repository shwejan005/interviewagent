"""Controller: HTTP endpoints for resume upload, parsing, and import.

Mounted under /me alongside the existing candidate_routes.router (both use
the "/me" prefix; FastAPI merges routers cleanly since the paths don't
collide).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.candidate import repository as cdb
from app.shared import audit
from app.shared.authz import Actor, current_actor

from app.resume.dto import ResumeImportRequest, ResumeParseResponse
from app.resume.service import ResumeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/me/resume", tags=["resume"])


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _service() -> ResumeService:
    return ResumeService()


@router.post("/parse", response_model=ResumeParseResponse)
async def parse_resume(
    file: UploadFile = File(...),
    actor: Actor = Depends(current_actor),
):
    """Upload a resume and get back suggested profile fields to review.

    Nothing is written to the candidate's profile here — see POST
    /me/resume/import for the confirming step.
    """
    service = _service()
    document, parsed, parsed_by = await service.upload_and_parse(actor.user_id, file)
    warnings = []
    if parsed_by == "heuristic":
        warnings.append("Automatic extraction used a simplified parser; please review every field carefully.")
    return ResumeParseResponse(
        resume_document_id=document.id,
        char_count=document.char_count,
        parsed_by=parsed_by,
        raw_text=document.raw_text,
        parsed=parsed,
        warnings=warnings,
    )


@router.post("/import")
async def import_resume(
    req: ResumeImportRequest,
    actor: Actor = Depends(current_actor),
):
    """Apply reviewed/edited resume fields to the candidate's profile.

    This wholesale-replaces work experience, education, and skills (the
    candidate has already reviewed them in the client) and upserts the
    scalar profile fields, mirroring PUT /me/profile's create-or-update
    semantics.
    """
    existing = await _db(cdb.get_profile_by_user, actor.user_id)
    scalar_fields = {
        "headline": req.headline,
        "summary": req.summary,
        "location": req.location,
        "phone": req.phone,
        "work_authorization": req.work_authorization,
        "years_experience": req.years_experience,
        "resume_text": req.resume_text,
    }
    if existing is None:
        profile_id = await _db(cdb.create_profile, actor.user_id, **scalar_fields)
        await _db(cdb.record_consent, profile_id, "v1")
    else:
        profile_id = existing["id"]
        await _db(cdb.update_profile, profile_id, **scalar_fields)

    await _db(
        cdb.replace_experiences,
        profile_id,
        [item.model_dump() for item in req.work_experiences],
    )
    await _db(
        cdb.replace_education,
        profile_id,
        [item.model_dump() for item in req.education],
    )
    await _db(
        cdb.set_skills,
        profile_id,
        [item.model_dump() for item in req.skills],
    )

    audit.record_from_actor(
        actor,
        "profile.resume_imported",
        resource_type="candidate_profile",
        resource_id=profile_id,
    )

    full_profile = await _db(cdb.get_full_profile, actor.user_id)
    if full_profile is None:
        raise HTTPException(status_code=500, detail="Profile import failed unexpectedly.")
    return full_profile
