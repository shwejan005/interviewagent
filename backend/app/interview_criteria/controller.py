"""Controller: recruiter endpoints for posting evaluation criteria and
generated per-application interview reports.

Mounted under /orgs/{org_id} alongside recruiter_routes.router. Tenant and
campaign-assignment checks are reused from recruiter_routes rather than
reimplemented, since they are the single source of truth for that logic.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.hiring import repository as hdb
from app.hiring.controller import _campaign_id_for_posting, _require_org
from app.shared import audit
from app.shared.authz import Actor, requires
from app.shared.rbac import Capability

from app.interview_criteria.dto import (
    ApplicationReportResponse,
    CompetencyScoreDTO,
    CriteriaResponse,
    CriteriaUpsertRequest,
)
from app.interview_criteria.service import CriteriaService, ReportService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orgs/{org_id}", tags=["interview-criteria"])

_NOT_FOUND = "Not found."


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _to_response(criteria) -> CriteriaResponse:
    return CriteriaResponse(
        posting_id=criteria.posting_id,
        competencies=criteria.competencies,
        custom_questions=criteria.custom_questions,
        pass_threshold=criteria.pass_threshold,
        interview_settings=criteria.interview_settings,
        rubric_version=criteria.rubric_version,
        updated_at=criteria.updated_at,
    )


@router.get("/postings/{posting_id}/criteria", response_model=CriteriaResponse)
async def get_criteria(
    org_id: int,
    posting_id: int,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ)),
):
    await _campaign_id_for_posting(actor, org_id, posting_id)
    criteria = await _db(CriteriaService().get_or_default, posting_id, org_id)
    return _to_response(criteria)


@router.put("/postings/{posting_id}/criteria", response_model=CriteriaResponse)
async def upsert_criteria(
    org_id: int,
    posting_id: int,
    req: CriteriaUpsertRequest,
    actor: Actor = Depends(requires(Capability.CAMPAIGN_UPDATE)),
):
    await _campaign_id_for_posting(actor, org_id, posting_id)
    criteria = await _db(
        CriteriaService().upsert,
        posting_id,
        org_id,
        [c.model_dump() for c in req.competencies],
        req.custom_questions,
        req.pass_threshold,
        req.interview_settings.model_dump(),
        actor.user_id,
    )
    audit.record_from_actor(
        actor,
        "posting.criteria_updated",
        resource_type="job_posting",
        resource_id=posting_id,
    )
    return _to_response(criteria)


@router.get("/applications/{application_id}/report", response_model=ApplicationReportResponse)
async def get_application_report(
    org_id: int,
    application_id: int,
    actor: Actor = Depends(requires(Capability.APPLICATION_READ)),
):
    _require_org(actor, org_id)
    application = await _db(hdb.get_application, application_id, org_id)
    if application is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await _campaign_id_for_posting(actor, org_id, application["posting_id"])

    report = await _db(ReportService().get, application_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No interview report yet. It is generated automatically once the interview pipeline completes.",
        )
    return ApplicationReportResponse(
        application_id=report.application_id,
        evaluation_id=report.evaluation_id,
        posting_id=report.posting_id,
        competency_scores=[CompetencyScoreDTO(**score) for score in report.competency_scores],
        overall_weighted_score=report.overall_weighted_score,
        recommendation=report.recommendation,
        rubric_version=report.rubric_version,
        generated_at=report.generated_at,
        interview_details=report.interview_details,
    )
