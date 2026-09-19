"""
API Routes — FastAPI endpoints for the interview pipeline.

FastAPI handles orchestration only — no decision-making logic here.
All decisions are made by CrewAI agents via crew_runner.py.

Supports both the legacy session-based flow and new evaluation-based REST API.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from models import (
    StartRequest,
    AnswerRequest,
    RoundResponse,
    EvaluationSummary,
    PipelineStage,
    PipelineStatus,
    DashboardStats,
)
from state import (
    get_state,
    update_state,
    reset_state,
    interview_state,
    AVAILABLE_ROLES,
    PIPELINE_STAGES,
)
from crew_runner import (
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


# ── POST /reset ──────────────────────────────────────────────────────


@router.post("/reset")
async def reset_interview():
    """
    Explicitly reset all interview state and clear verdict files.
    Called by the frontend before starting a new interview.
    """
    reset_state()
    return {"status": "reset", "message": "Interview state cleared."}


# ── POST /start ──────────────────────────────────────────────────────


@router.post("/start")
async def start_interview(req: StartRequest):
    """
    Start a new interview evaluation.
    - Resets session context and decision memory
    - Creates evaluation record in database
    - Runs ScreeningAgent with resume only (AGENT CONTEXT)
    - Writes verdict to DECISION MEMORY (verdicts/round1.txt)
    - Returns structured verdict + next round info
    """
    if not req.resume.strip():
        raise HTTPException(status_code=400, detail="Resume cannot be empty.")
    if not req.role.strip():
        raise HTTPException(status_code=400, detail="Role must be selected.")
    if req.role.strip() not in AVAILABLE_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choose from: {AVAILABLE_ROLES}")

    # Reset everything for a fresh interview
    reset_state()
    update_state(resume=req.resume.strip(), role=req.role.strip(), candidate_name=req.candidate_name.strip())

    # Create database record
    eval_id = db.create_evaluation(
        resume_text=req.resume.strip(),
        role=req.role.strip(),
        candidate_name=req.candidate_name.strip(),
    )
    interview_state["evaluation_id"] = eval_id

    # Run Round 1 — Screening Agent (context: resume + role)
    result = await run_screening(req.resume.strip(), req.role.strip())

    # Save verdict to database
    db.save_verdict(
        evaluation_id=eval_id,
        agent_type="screening",
        round_number=1,
        verdict_json=result["verdict"],
        verdict_text=result["verdict_text"],
        score=result.get("score"),
        decision=result["decision"],
        confidence=result.get("confidence"),
    )

    # Update SESSION CONTEXT
    interview_state["verdicts"]["round1"] = "verdicts/round1.txt"
    decision = result["decision"]

    if decision == "FAIL":
        update_state(status="REJECTED")
        db.update_evaluation(eval_id, status="REJECTED", current_round=1, final_decision="REJECT")
        return {
            "evaluation_id": eval_id,
            "round": 1,
            "decision": "FAIL",
            "verdict": result["verdict"],
            "verdict_text": result["verdict_text"],
            "status": "REJECTED",
            "message": "The candidate did not pass the screening round.",
        }

    # PASS or BORDERLINE — generate technical questions for Round 2
    tech_result = await run_technical_questions(get_state()["resume"])
    interview_state["questions"]["round2"] = tech_result["questions"]
    db.save_questions(eval_id, 2, tech_result["questions"])
    update_state(round=2)
    db.update_evaluation(eval_id, current_round=2)

    return {
        "evaluation_id": eval_id,
        "round": 1,
        "decision": decision,
        "verdict": result["verdict"],
        "verdict_text": result["verdict_text"],
        "status": "ONGOING",
        "next_round": 2,
        "question": tech_result["questions"],
    }


# ── POST /round/2/answer ────────────────────────────────────────────


@router.post("/round/2/answer")
async def round2_answer(req: AnswerRequest):
    """
    Submit answer for Round 2 (Technical).
    - Runs TechnicalAgent with AGENT CONTEXT (resume + round1.txt)
    - Writes verdict to verdicts/round2.txt
    - Returns verdict + next round or rejection
    """
    state = get_state()

    if state["status"] != "ONGOING":
        raise HTTPException(status_code=400, detail=f"Interview is {state['status']}.")
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    eval_id = state.get("evaluation_id")

    # Store answer
    interview_state["answers"]["round2"].append(req.answer.strip())
    if eval_id:
        db.save_answer(eval_id, 2, req.answer.strip())

    # Run Technical evaluation
    questions = interview_state["questions"]["round2"] or ""
    result = await run_technical_evaluation(state["resume"], questions, req.answer.strip())

    # Save verdict to database
    if eval_id:
        db.save_verdict(
            evaluation_id=eval_id,
            agent_type="technical",
            round_number=2,
            verdict_json=result["verdict"],
            verdict_text=result["verdict_text"],
            score=result.get("score"),
            decision=result["decision"],
            confidence=result.get("confidence"),
        )

    interview_state["verdicts"]["round2"] = "verdicts/round2.txt"
    decision = result["decision"]

    if decision == "FAIL":
        update_state(status="REJECTED")
        if eval_id:
            db.update_evaluation(eval_id, status="REJECTED", current_round=2, final_decision="REJECT")
        return {
            "evaluation_id": eval_id,
            "round": 2,
            "decision": "FAIL",
            "verdict": result["verdict"],
            "verdict_text": result["verdict_text"],
            "status": "REJECTED",
            "message": "The candidate did not pass the technical round.",
        }

    # PASS — generate behavioral question for Round 3
    behavioral_result = await run_behavioral_question(state["resume"])
    interview_state["questions"]["round3"] = behavioral_result["question"]
    if eval_id:
        db.save_questions(eval_id, 3, behavioral_result["question"])
    update_state(round=3)
    if eval_id:
        db.update_evaluation(eval_id, current_round=3)

    return {
        "evaluation_id": eval_id,
        "round": 2,
        "decision": decision,
        "verdict": result["verdict"],
        "verdict_text": result["verdict_text"],
        "status": "ONGOING",
        "next_round": 3,
        "question": behavioral_result["question"],
    }


# ── POST /round/3/answer ────────────────────────────────────────────


@router.post("/round/3/answer")
async def round3_answer(req: AnswerRequest):
    """
    Submit answer for Round 3 (Behavioral).
    - Runs BehavioralAgent with AGENT CONTEXT
    - Writes verdict to verdicts/round3.txt
    - Returns completion status
    """
    state = get_state()

    if state["status"] != "ONGOING":
        raise HTTPException(status_code=400, detail=f"Interview is {state['status']}.")
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    eval_id = state.get("evaluation_id")

    # Store answer
    interview_state["answers"]["round3"].append(req.answer.strip())
    if eval_id:
        db.save_answer(eval_id, 3, req.answer.strip())

    # Run Behavioral evaluation
    question = interview_state["questions"]["round3"] or ""
    result = await run_behavioral_evaluation(state["resume"], question, req.answer.strip())

    # Save verdict to database
    if eval_id:
        db.save_verdict(
            evaluation_id=eval_id,
            agent_type="behavioral",
            round_number=3,
            verdict_json=result["verdict"],
            verdict_text=result["verdict_text"],
            score=result.get("score"),
            decision=result["decision"],
            confidence=result.get("confidence"),
        )

    interview_state["verdicts"]["round3"] = "verdicts/round3.txt"
    decision = result["decision"]

    if decision == "FAIL":
        update_state(status="REJECTED")
        if eval_id:
            db.update_evaluation(eval_id, status="REJECTED", current_round=3, final_decision="REJECT")
        return {
            "evaluation_id": eval_id,
            "round": 3,
            "decision": "FAIL",
            "verdict": result["verdict"],
            "verdict_text": result["verdict_text"],
            "status": "REJECTED",
            "message": "The candidate did not pass the behavioral round.",
        }

    # PASS or BORDERLINE — mark complete (recommendation + committee happen at /final-decision)
    update_state(status="COMPLETE", round=4)
    if eval_id:
        db.update_evaluation(eval_id, current_round=4)

    return {
        "evaluation_id": eval_id,
        "round": 3,
        "decision": decision,
        "verdict": result["verdict"],
        "verdict_text": result["verdict_text"],
        "status": "COMPLETE",
        "next": "/final-decision",
    }


# ── GET /final-decision ─────────────────────────────────────────────


@router.get("/final-decision")
async def final_decision():
    """
    Get the final hiring decision.
    - Runs HiringRecommendationAgent (Round 4)
    - Runs HiringCommitteeAgent (Committee Evaluator)
    - Neither agent sees the resume or raw answers
    - Returns final decision + full rationale
    """
    state = get_state()
    eval_id = state.get("evaluation_id")

    if state["status"] == "REJECTED":
        return {
            "evaluation_id": eval_id,
            "decision": "REJECT",
            "verdict": {"decision": "REJECT", "reason": "Candidate was rejected in an earlier round."},
            "verdict_text": "Candidate was rejected in an earlier round.",
            "rationale": "Candidate was rejected in an earlier round.",
            "status": "REJECTED",
        }

    if state["status"] != "COMPLETE":
        raise HTTPException(
            status_code=400,
            detail="Interview is not complete. All rounds must be finished first.",
        )

    # Check for cached decision
    if state["final_decision"]:
        return state["final_decision"]

    # Run Round 4 — Hiring Recommendation Agent
    logger.info("Running Hiring Recommendation Agent...")
    rec_result = await run_hiring_recommendation()
    interview_state["verdicts"]["round4"] = "verdicts/round4.txt"

    if eval_id:
        db.save_verdict(
            evaluation_id=eval_id,
            agent_type="recommendation",
            round_number=4,
            verdict_json=rec_result["verdict"],
            verdict_text=rec_result["verdict_text"],
            score=rec_result.get("score"),
            decision=rec_result["decision"],
            confidence=rec_result.get("confidence"),
        )

    # Run Committee Evaluator — ONLY sees agent outputs, NOT resume
    logger.info("Running Committee Evaluator...")
    committee_result = await run_hiring_committee()

    if eval_id:
        db.save_verdict(
            evaluation_id=eval_id,
            agent_type="committee",
            round_number=5,
            verdict_json=committee_result["verdict"],
            verdict_text=committee_result["verdict_text"],
            decision=committee_result["decision"],
            confidence=committee_result.get("confidence"),
        )

    # Calculate overall score (average of all round scores)
    all_verdicts = db.get_verdicts(eval_id) if eval_id else []
    scores = [v["score"] for v in all_verdicts if v.get("score") is not None]
    overall_score = round(sum(scores) / len(scores), 1) if scores else None

    if eval_id:
        db.update_evaluation(
            eval_id,
            status="COMPLETE",
            current_round=5,
            final_decision=committee_result["decision"],
            overall_score=overall_score,
        )

    # Build response
    final = {
        "evaluation_id": eval_id,
        "decision": committee_result["decision"],
        "verdict": committee_result["verdict"],
        "verdict_text": committee_result["verdict_text"],
        "rationale": committee_result["verdict_text"],
        "recommendation": rec_result["verdict"],
        "recommendation_text": rec_result["verdict_text"],
        "overall_score": overall_score,
        "confidence": committee_result.get("confidence", 0.8),
        "status": "COMPLETE",
    }
    interview_state["final_decision"] = final

    return final


# ── GET /roles ───────────────────────────────────────────────────────


@router.get("/roles")
async def get_available_roles():
    """Return the list of available interview roles."""
    return {"roles": AVAILABLE_ROLES}


# ── GET /status ──────────────────────────────────────────────────────


@router.get("/status")
async def get_interview_status():
    """Return current interview state (for frontend polling / debugging)."""
    state = get_state()
    return {
        "evaluation_id": state.get("evaluation_id"),
        "round": state["round"],
        "status": state["status"],
        "role": state["role"],
        "candidate_name": state.get("candidate_name", ""),
        "has_resume": bool(state["resume"]),
        "verdicts": {
            k: v is not None for k, v in state["verdicts"].items()
        },
    }


# ── Evaluation REST API ─────────────────────────────────────────────


@router.get("/evaluations")
async def list_evaluations(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all evaluations with optional filtering."""
    evaluations = db.list_evaluations(status=status, limit=limit, offset=offset)
    total = db.count_evaluations(status=status)

    # Enrich with verdict summaries
    enriched = []
    for ev in evaluations:
        verdicts = db.get_verdicts(ev["id"])
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
    """Get full evaluation details including all verdicts."""
    evaluation = db.get_evaluation(eval_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    verdicts = db.get_verdicts(eval_id)

    return {
        "evaluation": evaluation,
        "verdicts": verdicts,
    }


@router.get("/evaluations/{eval_id}/report")
async def get_evaluation_report(eval_id: int):
    """Get a structured evaluation report."""
    evaluation = db.get_evaluation(eval_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    verdicts = db.get_verdicts(eval_id)

    # Build pipeline stages
    stages = []
    for ps in PIPELINE_STAGES:
        verdict = next(
            (v for v in verdicts if v["round_number"] == ps["stage"]),
            None,
        )
        stage_status = "complete" if verdict else "pending"
        if evaluation["current_round"] == ps["stage"] and evaluation["status"] == "IN_PROGRESS":
            stage_status = "active"
        if verdict and verdict["decision"] in ("FAIL", "REJECT"):
            stage_status = "failed"

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
    """Get pipeline status for an evaluation."""
    evaluation = db.get_evaluation(eval_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found.")

    verdicts = db.get_verdicts(eval_id)

    stages = []
    for ps in PIPELINE_STAGES:
        verdict = next(
            (v for v in verdicts if v["round_number"] == ps["stage"]),
            None,
        )
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
    stats = db.get_dashboard_stats()
    return stats
