"""Human evidence-review endpoints for completed evaluations."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import database as db
from app.evaluation.controller import _load_accessible_evaluation
from app.review import repository as review_db
from app.shared.authz import Actor, requires
from app.shared.rbac import Capability

router = APIRouter(prefix="/review", tags=["review"])


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


class ReviewActionRequest(BaseModel):
    action: Literal["APPROVE", "CORRECT", "ESCALATE"]
    note: str = Field(default="", max_length=4_000)
    correction: dict = Field(default_factory=dict)
    rubric_version: str = Field(default="backend-v1", max_length=80)


@router.get("/evaluations/{evaluation_id}")
async def review_packet(
    evaluation_id: int,
    actor: Actor = Depends(requires(Capability.EVALUATION_READ)),
):
    await _load_accessible_evaluation(evaluation_id, actor, None)
    verdicts = await _db(db.get_verdicts, evaluation_id)
    actions = await _db(review_db.list_review_actions, evaluation_id)
    return {
        "evaluation": await _db(db.get_evaluation_public, evaluation_id),
        "verdicts": verdicts,
        "actions": actions,
        "review_state": actions[-1]["action"] if actions else "UNREVIEWED",
        "rubric_version": "backend-v1",
        "review_guidance": "Approve supported evidence, correct material errors with an attributed note, or escalate uncertainty.",
    }


@router.post("/evaluations/{evaluation_id}/actions")
async def record_review_action(
    evaluation_id: int,
    request: ReviewActionRequest,
    actor: Actor = Depends(requires(Capability.EVALUATION_READ)),
):
    await _load_accessible_evaluation(evaluation_id, actor, None)
    action = await _db(
        review_db.record_review_action,
        evaluation_id,
        actor.user_id,
        request.action,
        request.note,
        request.correction,
        request.rubric_version,
    )
    return {"action": action, "review_state": request.action}


@router.get("/benchmarks")
async def benchmark_cases(
    split: str | None = None,
    actor: Actor = Depends(requires(Capability.AUDIT_READ)),
):
    return {"cases": await _db(review_db.list_benchmark_cases, split)}
