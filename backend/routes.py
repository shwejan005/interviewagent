"""
API Routes — FastAPI endpoints for the interview pipeline.

FastAPI handles orchestration only — no decision-making logic here.
All decisions are made by CrewAI agents via crew_runner.py.

The database is the single source of truth for evaluation status and round
progress — there is no shared in-memory session. Every mutating endpoint
takes (or returns) an `evaluation_id` and re-derives state from the database
on each request, so concurrent evaluations for different candidates cannot
interfere with each other.
"""

import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from models import (
    StartRequest,
    AnswerRequest,
    PipelineStage,
    PipelineStatus,
)
from state import AVAILABLE_ROLES, PIPELINE_STAGES
from crew_runner import (
    AgentOutputError,
    run_screening,
    run_technical_questions,
    run_technical_evaluation,
    run_behavioral_question,
    run_behavioral_evaluation,
    run_hiring_recommendation,
    run_hiring_committee,
)
import database as db

logger = logging.getLogger(__name__)
router = APIRouter()


async def _db(func, *args, **kwargs):
    """Run a synchronous database call off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def _record_agent_output_error(
    evaluation_id: int, agent_type: str, round_number: int, exc: AgentOutputError
) -> None:
    """Persist a failed agent execution for triage without recording a business decision.

    decision='INVALID_OUTPUT' is exempt from the canonical-verdict uniqueness
    constraint, so a subsequent retry for the same round is still possible.
    """
    logger.error(
        "Agent output invalid (evaluation_id=%s, agent=%s, round=%s): %s",
        evaluation_id, agent_type, round_number, exc,
    )
    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type=agent_type,
            round_number=round_number,
            verdict_json={"error": str(exc)},
            verdict_text=exc.raw_output,
            score=None,
            decision="INVALID_OUTPUT",
            confidence=None,
        )
    except db.DuplicateVerdictError:
        # A canonical verdict already exists for this round — nothing to record.
        pass


# ── POST /reset ──────────────────────────────────────────────────────


@router.post("/reset")
async def reset_interview():
    """
    Deprecated no-op, retained for backward compatibility with older clients.
    Every evaluation is isolated by its own `evaluation_id`; there is no
    shared session state to reset.
    """
    return {"status": "ok", "message": "No shared session state to reset."}


# ── POST /start ──────────────────────────────────────────────────────


@router.post("/start")
async def start_interview(req: StartRequest):
    """
    Start a new interview evaluation.
    - Creates an isolated evaluation record in the database
    - Runs the Screening Agent with resume + role only (AGENT CONTEXT)
    - Writes the verdict to this evaluation's DECISION MEMORY
    - Returns the structured verdict + next round info
    """
    resume = req.resume.strip()
    role = req.role.strip()
    candidate_name = req.candidate_name.strip()

    if not resume:
        raise HTTPException(status_code=400, detail="Resume cannot be empty.")
    if not role:
        raise HTTPException(status_code=400, detail="Role must be selected.")
    if role not in AVAILABLE_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choose from: {AVAILABLE_ROLES}")

    evaluation_id = await _db(
        db.create_evaluation, resume_text=resume, role=role, candidate_name=candidate_name
    )

    # Run Round 1 — Screening Agent (context: resume + role)
    try:
        result = await run_screening(evaluation_id, resume, role)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "screening", 1, exc)
        raise HTTPException(
            status_code=502,
            detail="The screening agent returned an invalid response. Please retry.",
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

    decision = result["decision"]

    if decision == "FAIL":
        await _db(
            db.update_evaluation,
            evaluation_id, status="REJECTED", current_round=1, final_decision="REJECT",
        )
        return {
            "evaluation_id": evaluation_id,
            "round": 1,
            "decision": "FAIL",
            "verdict": result["verdict"],
            "verdict_text": result["verdict_text"],
            "status": "REJECTED",
            "message": "The candidate did not pass the screening round.",
        }

    # PASS or BORDERLINE — generate technical questions for Round 2
    try:
        tech_result = await run_technical_questions(evaluation_id, resume)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "technical", 2, exc)
        raise HTTPException(
            status_code=502,
            detail="The technical agent failed to generate questions. Please retry.",
        ) from exc

    await _db(db.save_questions, evaluation_id, 2, tech_result["questions"])
    await _db(db.update_evaluation, evaluation_id, current_round=2)

    return {
        "evaluation_id": evaluation_id,
        "round": 1,
        "decision": decision,
        "verdict": result["verdict"],
        "verdict_text": result["verdict_text"],
        "status": "IN_PROGRESS",
        "next_round": 2,
        "question": tech_result["questions"],
    }


# ── POST /round/2/answer ────────────────────────────────────────────


@router.post("/round/2/answer")
async def round2_answer(
    req: AnswerRequest,
    evaluation_id: int = Query(..., description="Evaluation ID returned by /start"),
):
    """
    Submit answer for Round 2 (Technical).
    - Runs the Technical Agent with AGENT CONTEXT (resume + round1 verdict)
    - Writes the verdict to this evaluation's DECISION MEMORY
    - Returns the verdict + next round or rejection
    """
    answer = req.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    evaluation = await _db(db.get_evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    if evaluation["status"] != "IN_PROGRESS":
        raise HTTPException(status_code=400, detail=f"Evaluation is {evaluation['status']}.")
    if evaluation["current_round"] != 2:
        raise HTTPException(
            status_code=409,
            detail=f"Evaluation is at round {evaluation['current_round']}, not round 2.",
        )
    if await _db(db.get_verdict_by_round, evaluation_id, 2) is not None:
        raise HTTPException(status_code=409, detail="Round 2 has already been evaluated.")

    await _db(db.save_answer, evaluation_id, 2, answer)

    questions = await _db(db.get_questions, evaluation_id, 2) or ""

    try:
        result = await run_technical_evaluation(evaluation_id, evaluation["resume_text"], questions, answer)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "technical", 2, exc)
        raise HTTPException(
            status_code=502,
            detail="The technical agent returned an invalid response. Please retry.",
        ) from exc

    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="technical",
            round_number=2,
            verdict_json=result["verdict"],
            verdict_text=result["verdict_text"],
            score=result["score"],
            decision=result["decision"],
            confidence=result["confidence"],
        )
    except db.DuplicateVerdictError as exc:
        raise HTTPException(status_code=409, detail="Round 2 has already been evaluated.") from exc

    decision = result["decision"]

    if decision == "FAIL":
        await _db(
            db.update_evaluation,
            evaluation_id, status="REJECTED", current_round=2, final_decision="REJECT",
        )
        return {
            "evaluation_id": evaluation_id,
            "round": 2,
            "decision": "FAIL",
            "verdict": result["verdict"],
            "verdict_text": result["verdict_text"],
            "status": "REJECTED",
            "message": "The candidate did not pass the technical round.",
        }

    # PASS — generate behavioral question for Round 3
    try:
        behavioral_result = await run_behavioral_question(evaluation_id, evaluation["resume_text"])
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "behavioral", 3, exc)
        raise HTTPException(
            status_code=502,
            detail="The behavioral agent failed to generate a question. Please retry.",
        ) from exc

    await _db(db.save_questions, evaluation_id, 3, behavioral_result["question"])
    await _db(db.update_evaluation, evaluation_id, current_round=3)

    return {
        "evaluation_id": evaluation_id,
        "round": 2,
        "decision": decision,
        "verdict": result["verdict"],
        "verdict_text": result["verdict_text"],
        "status": "IN_PROGRESS",
        "next_round": 3,
        "question": behavioral_result["question"],
    }


# ── POST /round/3/answer ────────────────────────────────────────────


@router.post("/round/3/answer")
async def round3_answer(
    req: AnswerRequest,
    evaluation_id: int = Query(..., description="Evaluation ID returned by /start"),
):
    """
    Submit answer for Round 3 (Behavioral).
    - Runs the Behavioral Agent with AGENT CONTEXT
    - Writes the verdict to this evaluation's DECISION MEMORY
    - Returns completion status (recommendation + committee run at /final-decision)
    """
    answer = req.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    evaluation = await _db(db.get_evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    if evaluation["status"] != "IN_PROGRESS":
        raise HTTPException(status_code=400, detail=f"Evaluation is {evaluation['status']}.")
    if evaluation["current_round"] != 3:
        raise HTTPException(
            status_code=409,
            detail=f"Evaluation is at round {evaluation['current_round']}, not round 3.",
        )
    if await _db(db.get_verdict_by_round, evaluation_id, 3) is not None:
        raise HTTPException(status_code=409, detail="Round 3 has already been evaluated.")

    await _db(db.save_answer, evaluation_id, 3, answer)

    question = await _db(db.get_questions, evaluation_id, 3) or ""

    try:
        result = await run_behavioral_evaluation(evaluation_id, evaluation["resume_text"], question, answer)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "behavioral", 3, exc)
        raise HTTPException(
            status_code=502,
            detail="The behavioral agent returned an invalid response. Please retry.",
        ) from exc

    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="behavioral",
            round_number=3,
            verdict_json=result["verdict"],
            verdict_text=result["verdict_text"],
            score=result["score"],
            decision=result["decision"],
            confidence=result["confidence"],
        )
    except db.DuplicateVerdictError as exc:
        raise HTTPException(status_code=409, detail="Round 3 has already been evaluated.") from exc

    decision = result["decision"]

    if decision == "FAIL":
        await _db(
            db.update_evaluation,
            evaluation_id, status="REJECTED", current_round=3, final_decision="REJECT",
        )
        return {
            "evaluation_id": evaluation_id,
            "round": 3,
            "decision": "FAIL",
            "verdict": result["verdict"],
            "verdict_text": result["verdict_text"],
            "status": "REJECTED",
            "message": "The candidate did not pass the behavioral round.",
        }

    # PASS or BORDERLINE — rounds are done; recommendation + committee run at /final-decision.
    # The evaluation row's `status` column stays IN_PROGRESS (final_decision is not
    # yet known); the response's own `status` field tells the client the
    # answer phase is complete and it should call /final-decision next.
    await _db(db.update_evaluation, evaluation_id, current_round=4)

    return {
        "evaluation_id": evaluation_id,
        "round": 3,
        "decision": decision,
        "verdict": result["verdict"],
        "verdict_text": result["verdict_text"],
        "status": "COMPLETE",
        "next": "/final-decision",
    }


# ── GET /final-decision ─────────────────────────────────────────────


@router.get("/final-decision")
async def final_decision(
    evaluation_id: int = Query(..., description="Evaluation ID returned by /start"),
):
    """
    Get the final hiring decision.
    - Runs the Hiring Recommendation Agent (Round 4)
    - Runs the Committee Evaluator (Final)
    - Neither agent sees the resume or raw answers
    - Idempotent: replays the persisted committee verdict if already finalized
    """
    evaluation = await _db(db.get_evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    if evaluation["status"] == "REJECTED":
        return {
            "evaluation_id": evaluation_id,
            "decision": "REJECT",
            "verdict": {"decision": "REJECT", "reason": "Candidate was rejected in an earlier round."},
            "verdict_text": "Candidate was rejected in an earlier round.",
            "rationale": "Candidate was rejected in an earlier round.",
            "status": "REJECTED",
        }

    if evaluation["current_round"] < 4:
        raise HTTPException(
            status_code=400,
            detail="Interview is not complete. All rounds must be finished first.",
        )

    # Idempotent replay: if already finalized, return the persisted result
    # instead of re-running (and re-billing) the recommendation/committee agents.
    if evaluation["status"] == "COMPLETE" and evaluation["final_decision"]:
        committee_verdict = await _db(db.get_verdict_by_round, evaluation_id, 5)
        if committee_verdict is not None:
            recommendation_verdict = await _db(db.get_verdict_by_round, evaluation_id, 4)
            return {
                "evaluation_id": evaluation_id,
                "decision": evaluation["final_decision"],
                "verdict": committee_verdict["verdict_json"],
                "verdict_text": committee_verdict["verdict_text"],
                "rationale": committee_verdict["verdict_text"],
                "recommendation": recommendation_verdict["verdict_json"] if recommendation_verdict else None,
                "recommendation_text": recommendation_verdict["verdict_text"] if recommendation_verdict else None,
                "overall_score": evaluation["overall_score"],
                "confidence": committee_verdict["confidence"],
                "status": "COMPLETE",
            }

    if await _db(db.get_verdict_by_round, evaluation_id, 4) is not None:
        raise HTTPException(
            status_code=409,
            detail="Final decision is already being processed for this evaluation.",
        )

    # Run Round 4 — Hiring Recommendation Agent
    logger.info("Running Hiring Recommendation Agent for evaluation %s...", evaluation_id)
    try:
        rec_result = await run_hiring_recommendation(evaluation_id)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "recommendation", 4, exc)
        raise HTTPException(
            status_code=502,
            detail="The recommendation agent returned an invalid response. Please retry.",
        ) from exc

    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="recommendation",
            round_number=4,
            verdict_json=rec_result["verdict"],
            verdict_text=rec_result["verdict_text"],
            score=rec_result["score"],
            decision=rec_result["decision"],
            confidence=rec_result["confidence"],
        )
    except db.DuplicateVerdictError as exc:
        raise HTTPException(status_code=409, detail="Final decision is already being processed.") from exc

    # Run Committee Evaluator — ONLY sees agent outputs, NOT resume
    logger.info("Running Committee Evaluator for evaluation %s...", evaluation_id)
    try:
        committee_result = await run_hiring_committee(evaluation_id)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "committee", 5, exc)
        raise HTTPException(
            status_code=502,
            detail="The committee evaluator returned an invalid response. Please retry.",
        ) from exc

    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="committee",
            round_number=5,
            verdict_json=committee_result["verdict"],
            verdict_text=committee_result["verdict_text"],
            decision=committee_result["decision"],
            confidence=committee_result["confidence"],
        )
    except db.DuplicateVerdictError as exc:
        raise HTTPException(status_code=409, detail="Final decision is already being processed.") from exc

    # Overall score is the average of the genuine round evaluations (screening,
    # technical, behavioral) only — the recommendation's own score already
    # synthesizes those three and would otherwise double-count in the average.
    all_verdicts = await _db(db.get_verdicts, evaluation_id)
    scores = [
        v["score"] for v in all_verdicts
        if v["round_number"] in (1, 2, 3) and v["score"] is not None
    ]
    overall_score = round(sum(scores) / len(scores), 1) if scores else None

    await _db(
        db.update_evaluation,
        evaluation_id,
        status="COMPLETE",
        current_round=5,
        final_decision=committee_result["decision"],
        overall_score=overall_score,
    )

    return {
        "evaluation_id": evaluation_id,
        "decision": committee_result["decision"],
        "verdict": committee_result["verdict"],
        "verdict_text": committee_result["verdict_text"],
        "rationale": committee_result["verdict_text"],
        "recommendation": rec_result["verdict"],
        "recommendation_text": rec_result["verdict_text"],
        "overall_score": overall_score,
        "confidence": committee_result["confidence"],
        "status": "COMPLETE",
    }


# ── GET /roles ───────────────────────────────────────────────────────


@router.get("/roles")
async def get_available_roles():
    """Return the list of available interview roles."""
    return {"roles": AVAILABLE_ROLES}


# ── GET /status ──────────────────────────────────────────────────────


@router.get("/status")
async def get_interview_status(
    evaluation_id: int = Query(..., description="Evaluation ID returned by /start"),
):
    """Return the current status of one evaluation, derived from the database."""
    evaluation = await _db(db.get_evaluation_public, evaluation_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    verdicts = await _db(db.get_verdicts, evaluation_id)
    completed_rounds = {
        v["round_number"] for v in verdicts if v["decision"] != "INVALID_OUTPUT"
    }

    return {
        "evaluation_id": evaluation_id,
        "round": evaluation["current_round"],
        "status": evaluation["status"],
        "role": evaluation["role"],
        "candidate_name": evaluation.get("candidate_name", ""),
        "verdicts": {f"round{n}": n in completed_rounds for n in (1, 2, 3, 4, 5)},
    }


# ── Evaluation REST API ─────────────────────────────────────────────


@router.get("/evaluations")
async def list_evaluations(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List evaluations with optional filtering (resume text is never included)."""
    evaluations = await _db(db.list_evaluations, status=status, limit=limit, offset=offset)
    total = await _db(db.count_evaluations, status=status)

    # Batch-fetch verdict summaries in a single query instead of one per evaluation.
    summaries = await _db(db.get_verdict_summaries, [ev["id"] for ev in evaluations])

    enriched = []
    for ev in evaluations:
        verdicts = summaries.get(ev["id"], [])
        ev["verdict_count"] = len(verdicts)
        ev["verdicts_summary"] = [
            {
                "agent_type": v["agent_type"],
                "round_number": v["round_number"],
                "decision": v["decision"],
                "score": v["score"],
            }
            for v in verdicts
        ]
        enriched.append(ev)

    return {
        "evaluations": enriched,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/evaluations/{eval_id}")
async def get_evaluation(eval_id: int):
    """Get evaluation summary + all verdicts. Resume text is never included here."""
    evaluation = await _db(db.get_evaluation_public, eval_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    verdicts = await _db(db.get_verdicts, eval_id)

    return {
        "evaluation": evaluation,
        "verdicts": verdicts,
    }


@router.get("/evaluations/{eval_id}/report")
async def get_evaluation_report(eval_id: int):
    """Get a structured evaluation report. Resume text is never included here."""
    evaluation = await _db(db.get_evaluation_public, eval_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    verdicts = await _db(db.get_verdicts, eval_id)

    # Build pipeline stages — prefer the canonical verdict over any recorded
    # INVALID_OUTPUT failure for the same round, so a retried failure doesn't
    # hide the eventual successful result.
    stages = []
    for ps in PIPELINE_STAGES:
        stage_verdicts = [v for v in verdicts if v["round_number"] == ps["stage"]]
        verdict = next((v for v in stage_verdicts if v["decision"] != "INVALID_OUTPUT"), None)
        failed_output = verdict is None and any(v["decision"] == "INVALID_OUTPUT" for v in stage_verdicts)

        stage_status = "complete" if verdict else "pending"
        if evaluation["current_round"] == ps["stage"] and evaluation["status"] == "IN_PROGRESS":
            stage_status = "active"
        if verdict and verdict["decision"] in ("FAIL", "REJECT"):
            stage_status = "failed"
        if failed_output:
            stage_status = "agent_output_invalid"

        stages.append({
            "stage": ps["stage"],
            "name": ps["name"],
            "agent": ps["agent"],
            "status": stage_status,
            "score": verdict["score"] if verdict else None,
            "decision": verdict["decision"] if verdict else None,
            "verdict": verdict["verdict_json"] if verdict else None,
        })

    return {
        "evaluation_id": eval_id,
        "candidate_name": evaluation["candidate_name"],
        "role": evaluation["role"],
        "status": evaluation["status"],
        "overall_score": evaluation["overall_score"],
        "final_decision": evaluation["final_decision"],
        "pipeline": stages,
        "verdicts": verdicts,
        "created_at": evaluation["created_at"],
        "updated_at": evaluation["updated_at"],
    }


@router.get("/evaluations/{eval_id}/pipeline")
async def get_pipeline_status(eval_id: int):
    """Get pipeline status for an evaluation. Resume text is never included here."""
    evaluation = await _db(db.get_evaluation_public, eval_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    verdicts = await _db(db.get_verdicts, eval_id)

    stages = []
    for ps in PIPELINE_STAGES:
        stage_verdicts = [v for v in verdicts if v["round_number"] == ps["stage"]]
        verdict = next((v for v in stage_verdicts if v["decision"] != "INVALID_OUTPUT"), None)

        stage_status = "complete" if verdict else "pending"
        if evaluation["current_round"] == ps["stage"] and evaluation["status"] == "IN_PROGRESS":
            stage_status = "active"

        stages.append(PipelineStage(
            stage=ps["stage"],
            name=ps["name"],
            agent=ps["agent"],
            status=stage_status,
            score=verdict["score"] if verdict else None,
            decision=verdict["decision"] if verdict else None,
        ))

    return PipelineStatus(
        evaluation_id=eval_id,
        stages=stages,
        current_stage=evaluation["current_round"],
        overall_status=evaluation["status"],
    )


# ── Dashboard Stats ──────────────────────────────────────────────────


@router.get("/dashboard/stats")
async def get_dashboard_stats():
    """Get aggregated dashboard statistics."""
    return await _db(db.get_dashboard_stats)

