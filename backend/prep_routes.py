"""Authenticated, text-first interview preparation APIs."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import prep_db
from authz import Actor, current_actor
from prep_models import ProblemSubmissionRequest, RoadmapCreateRequest

router = APIRouter(prefix="/prep", tags=["preparation"])


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


@router.get("/topics")
async def topics(actor: Actor = Depends(current_actor)):
    return {"topics": await _db(prep_db.list_topics)}


@router.get("/problems")
async def problems(
    topic: Optional[str] = Query(default=None, max_length=100),
    difficulty: Optional[str] = Query(default=None, pattern="^(EASY|MEDIUM|HARD|APPLIED)$"),
    actor: Actor = Depends(current_actor),
):
    return {"problems": await _db(prep_db.list_problems, topic, difficulty)}


@router.get("/problems/{problem_id}")
async def problem(problem_id: int, actor: Actor = Depends(current_actor)):
    result = await _db(prep_db.get_problem, problem_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Problem not found.")
    return result


@router.post("/roadmaps", status_code=201)
async def create_roadmap(
    req: RoadmapCreateRequest,
    actor: Actor = Depends(current_actor),
):
    try:
        return await _db(prep_db.create_roadmap, actor.user_id, req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/roadmaps")
async def list_roadmaps(actor: Actor = Depends(current_actor)):
    return {"roadmaps": await _db(prep_db.list_roadmaps, actor.user_id)}


@router.get("/roadmaps/{roadmap_id}")
async def roadmap(roadmap_id: int, actor: Actor = Depends(current_actor)):
    result = await _db(prep_db.get_roadmap, roadmap_id, actor.user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Roadmap not found.")
    return result


@router.post("/roadmaps/{roadmap_id}/nodes/{node_id}/complete")
async def complete_roadmap_node(
    roadmap_id: int,
    node_id: int,
    actor: Actor = Depends(current_actor),
):
    result = await _db(prep_db.complete_node, roadmap_id, node_id, actor.user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Roadmap node not found.")
    return result


@router.post("/problems/{problem_id}/submissions", status_code=201)
async def submit_problem(
    problem_id: int,
    req: ProblemSubmissionRequest,
    actor: Actor = Depends(current_actor),
):
    result = await _db(prep_db.submit_problem, actor.user_id, problem_id, req.answer_text.strip())
    if result is None:
        raise HTTPException(status_code=404, detail="Problem not found.")
    return {
        **result,
        "note": "Submission recorded for review; no code was executed and the skill is not verified.",
    }


@router.get("/me/stats")
async def prep_stats(actor: Actor = Depends(current_actor)):
    return await _db(prep_db.get_gamification, actor.user_id)
