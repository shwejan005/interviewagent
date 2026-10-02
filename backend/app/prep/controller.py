"""Authenticated, text-first interview preparation APIs."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.prep import code_runner, repository as prep_db, service as prep_ai
from app.prep.dto import CodeExecutionRequest, GeneratedProblemRequest, PrepGoalRequest, ProblemSubmissionRequest, RoadmapCreateRequest
from app.shared.authz import Actor, current_actor

router = APIRouter(prefix="/prep", tags=["preparation"])
_PROBLEM_NOT_FOUND = "Problem not found."


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


@router.get("/topics")
async def topics(actor: Actor = Depends(current_actor)):
    return {"topics": await _db(prep_db.list_topics)}


@router.get("/catalog")
async def catalog(actor: Actor = Depends(current_actor)):
    """Return the prep navigation data in one authenticated round trip."""
    topics, problems = await asyncio.gather(
        _db(prep_db.list_topics),
        _db(prep_db.list_problems),
    )
    return {"topics": topics, "problems": problems}


@router.get("/problems")
async def problems(
    topic: Optional[str] = Query(default=None, max_length=100),
    difficulty: Optional[str] = Query(default=None, pattern="^(EASY|MEDIUM|HARD|APPLIED)$"),
    actor: Actor = Depends(current_actor),
):
    return {"problems": await _db(prep_db.list_problems, topic, difficulty)}


@router.post("/problems/generate", status_code=201)
async def generate_problem(req: GeneratedProblemRequest, actor: Actor = Depends(current_actor)):
    topic = next((item for item in await _db(prep_db.list_topics) if item["slug"] == req.topic_slug), None)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found.")
    try:
        generated = await _db(prep_ai.generate_problem, topic, req.difficulty, req.language)
        return await _db(prep_db.create_generated_problem, generated)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/problems/{problem_id}")
async def problem(problem_id: int, actor: Actor = Depends(current_actor)):
    result = await _db(prep_db.get_problem, problem_id)
    if result is None:
        raise HTTPException(status_code=404, detail=_PROBLEM_NOT_FOUND)
    return result


@router.get("/problems/{problem_id}/submissions")
async def problem_submissions(problem_id: int, actor: Actor = Depends(current_actor)):
    return {"submissions": await _db(prep_db.list_code_submissions, actor.user_id, problem_id)}


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
        raise HTTPException(status_code=404, detail=_PROBLEM_NOT_FOUND)
    return {
        **result,
        "note": "Submission recorded for review; no code was executed and the skill is not verified.",
    }


@router.get("/me/stats")
async def prep_stats(actor: Actor = Depends(current_actor)):
    return await _db(prep_db.get_gamification, actor.user_id)


@router.get("/me/dashboard")
async def prep_dashboard(actor: Actor = Depends(current_actor)):
    return await _db(prep_db.get_dashboard, actor.user_id)


@router.get("/goals")
async def get_prep_goal(actor: Actor = Depends(current_actor)):
    return {"goal": await _db(prep_db.get_goal, actor.user_id)}


@router.put("/goals")
async def save_prep_goal(req: PrepGoalRequest, actor: Actor = Depends(current_actor)):
    return {"goal": await _db(prep_db.upsert_goal, actor.user_id, req.model_dump())}


@router.post("/roadmaps/generate", status_code=201)
async def generate_roadmap(actor: Actor = Depends(current_actor)):
    goal = await _db(prep_db.get_goal, actor.user_id)
    if goal is None:
        raise HTTPException(status_code=400, detail="Set your preparation goals before generating a roadmap.")
    topics = await _db(prep_db.list_topics)
    problems = await _db(prep_db.list_problems)
    plan = await _db(prep_ai.generate_roadmap_plan, goal, topics, problems)
    roadmap = await _db(prep_db.create_generated_roadmap, actor.user_id, goal, plan, problems)
    return {"roadmap": roadmap, "plan": plan}


@router.post("/execute")
async def execute_code(req: CodeExecutionRequest, actor: Actor = Depends(current_actor)):
    """Run code only through the explicitly configured isolated sandbox."""
    try:
        if req.problem_id is not None:
            problem = await _db(prep_db.get_problem_for_execution, req.problem_id)
            if problem is None:
                raise HTTPException(status_code=404, detail=_PROBLEM_NOT_FOUND)
            if req.mode == "submit":
                test_cases = problem["test_cases"]
            elif req.test_case_id is not None:
                test_cases = [case for case in problem["test_cases"] if case["id"] == req.test_case_id]
            else:
                test_cases = [case for case in problem["test_cases"] if not case.get("is_hidden")][:1]
            if not test_cases:
                raise HTTPException(status_code=400, detail="No runnable test case was selected.")
            harness = problem.get("harnesses", {}).get(req.language, "")
            result = await _db(
                code_runner.execute_problem,
                language=req.language,
                source_code=req.source_code,
                harness=harness,
                test_cases=test_cases,
            )
            await _db(prep_db.record_code_submission, actor.user_id, req.problem_id, req.language, req.source_code, result)
            return result
        return await _db(
            code_runner.execute_code,
            language=req.language,
            source_code=req.source_code,
            stdin=req.stdin,
            expected_output=req.expected_output,
        )
    except code_runner.SandboxUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except code_runner.SandboxExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
