"""Resumable final recommendation and committee execution."""

import asyncio
import logging
from typing import Awaitable, Callable

import database as db
from crew_runner import AgentOutputError

logger = logging.getLogger(__name__)

AgentRunner = Callable[[int], Awaitable[dict]]
REJECTION_REASON = "Candidate was rejected in an earlier round."


class FinalizationNotReadyError(Exception):
    """Raised when the candidate has not completed the interview rounds."""


async def _db(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def _record_agent_output_error(
    evaluation_id: int, agent_type: str, round_number: int, exc: AgentOutputError
) -> None:
    logger.error(
        "Agent output invalid (evaluation_id=%s, agent=%s, round=%s): %s",
        evaluation_id,
        agent_type,
        round_number,
        exc,
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
            error_type=type(exc).__name__,
        )
    except db.DuplicateVerdictError:
        pass


def _replay_result(evaluation: dict, committee_verdict: dict, recommendation_verdict: dict | None) -> dict:
    return {
        "evaluation_id": evaluation["id"],
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


def _rejected_result(evaluation_id: int) -> dict:
    return {
        "evaluation_id": evaluation_id,
        "decision": "REJECT",
        "verdict": {"decision": "REJECT", "reason": REJECTION_REASON},
        "verdict_text": REJECTION_REASON,
        "rationale": REJECTION_REASON,
        "status": "REJECTED",
    }


async def _run_recommendation(evaluation_id: int, runner: AgentRunner) -> dict:
    logger.info("Running Hiring Recommendation Agent for evaluation %s...", evaluation_id)
    try:
        result = await runner(evaluation_id)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "recommendation", 4, exc)
        raise

    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="recommendation",
            round_number=4,
            verdict_json=result["verdict"],
            verdict_text=result["verdict_text"],
            score=result.get("score"),
            decision=result["decision"],
            confidence=result["confidence"],
        )
    except db.DuplicateVerdictError:
        logger.info("Recommendation already persisted for evaluation %s", evaluation_id)
    return await _db(db.get_verdict_by_round, evaluation_id, 4)


async def _run_committee(evaluation_id: int, runner: AgentRunner) -> dict:
    logger.info("Running Hiring Committee Agent for evaluation %s...", evaluation_id)
    try:
        result = await runner(evaluation_id)
    except AgentOutputError as exc:
        await _record_agent_output_error(evaluation_id, "committee", 5, exc)
        raise

    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="committee",
            round_number=5,
            verdict_json=result["verdict"],
            verdict_text=result["verdict_text"],
            score=None,
            decision=result["decision"],
            confidence=result["confidence"],
        )
    except db.DuplicateVerdictError:
        logger.info("Committee verdict already persisted for evaluation %s", evaluation_id)
    return await _db(db.get_verdict_by_round, evaluation_id, 5)


async def _overall_score(evaluation_id: int) -> float | None:
    verdicts = await _db(db.get_verdicts, evaluation_id)
    scores = [
        verdict["score"]
        for verdict in verdicts
        if verdict["round_number"] in (1, 2, 3) and verdict["score"] is not None
    ]
    return round(sum(scores) / len(scores), 1) if scores else None


async def finalize_evaluation(
    evaluation_id: int,
    run_recommendation: AgentRunner,
    run_committee: AgentRunner,
) -> dict:
    """Run or resume recommendation and committee work for one evaluation.

    Each persisted verdict is a checkpoint. If a worker exits after saving
    round 4 or 5 but before updating the evaluation row, a later worker skips
    completed stages and finishes the remaining transition.
    """
    evaluation = await _db(db.get_evaluation, evaluation_id)
    if evaluation is None:
        raise LookupError("Evaluation not found")

    if evaluation["status"] == "REJECTED":
        return _rejected_result(evaluation_id)

    if evaluation["current_round"] < 4:
        raise FinalizationNotReadyError(
            "Interview is not complete. All rounds must be finished first."
        )

    committee_verdict = await _db(db.get_verdict_by_round, evaluation_id, 5)
    recommendation_verdict = await _db(db.get_verdict_by_round, evaluation_id, 4)
    if evaluation["status"] == "COMPLETE" and evaluation["final_decision"] and committee_verdict:
        return _replay_result(evaluation, committee_verdict, recommendation_verdict)

    if recommendation_verdict is None:
        recommendation_verdict = await _run_recommendation(evaluation_id, run_recommendation)

    committee_verdict = await _db(db.get_verdict_by_round, evaluation_id, 5)
    if committee_verdict is None:
        committee_verdict = await _run_committee(evaluation_id, run_committee)

    if recommendation_verdict is None or committee_verdict is None:
        raise RuntimeError("Finalization checkpoints could not be read after execution")

    overall_score = await _overall_score(evaluation_id)

    await _db(
        db.update_evaluation,
        evaluation_id,
        status="COMPLETE",
        current_round=5,
        final_decision=committee_verdict["decision"],
        overall_score=overall_score,
    )
    evaluation = await _db(db.get_evaluation, evaluation_id)
    return _replay_result(evaluation, committee_verdict, recommendation_verdict)
