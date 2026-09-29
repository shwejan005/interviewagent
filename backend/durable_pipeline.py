"""Durable handlers for the existing interview pipeline.

The legacy routes remain synchronous for compatibility. These handlers reuse the
same crew_runner functions and persistence rules behind queued v1 commands.
"""

import asyncio

import database as db
from crew_runner import (
    AgentOutputError,
    run_behavioral_evaluation,
    run_behavioral_question,
    run_hiring_committee,
    run_hiring_recommendation,
    run_screening,
    run_technical_evaluation,
    run_technical_questions,
)
from finalization import finalize_evaluation


def _db(func, *args, **kwargs):
    return asyncio.to_thread(func, *args, **kwargs)


async def _record_invalid_output(evaluation_id: int, agent_type: str, round_number: int, exc: AgentOutputError) -> None:
    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type=agent_type,
            round_number=round_number,
            verdict_json={"error": str(exc)},
            verdict_text=exc.raw_output,
            decision="INVALID_OUTPUT",
            error_type=type(exc).__name__,
        )
    except db.DuplicateVerdictError:
        pass


async def handle_screening(payload: dict) -> None:
    evaluation_id = int(payload["evaluation_id"])
    evaluation = await _db(db.get_evaluation, evaluation_id)
    if evaluation is None or await _db(db.get_verdict_by_round, evaluation_id, 1):
        return
    try:
        result = await run_screening(evaluation_id, evaluation["resume_text"], evaluation["role"])
    except AgentOutputError as exc:
        await _record_invalid_output(evaluation_id, "screening", 1, exc)
        raise
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
    if result["decision"] == "FAIL":
        await _db(db.update_evaluation, evaluation_id, status="REJECTED", current_round=1, final_decision="REJECT")
        return
    try:
        questions = await run_technical_questions(evaluation_id, evaluation["resume_text"])
    except AgentOutputError as exc:
        await _record_invalid_output(evaluation_id, "technical", 2, exc)
        raise
    await _db(db.save_questions, evaluation_id, 2, questions["questions"])
    await _db(db.update_evaluation, evaluation_id, current_round=2)


async def handle_technical(payload: dict) -> None:
    evaluation_id = int(payload["evaluation_id"])
    evaluation = await _db(db.get_evaluation, evaluation_id)
    if evaluation is None or await _db(db.get_verdict_by_round, evaluation_id, 2):
        return
    answer = await _db(db.get_answer, evaluation_id, 2)
    questions = await _db(db.get_questions, evaluation_id, 2) or ""
    if not answer:
        raise ValueError("Technical answer is missing")
    try:
        result = await run_technical_evaluation(evaluation_id, evaluation["resume_text"], questions, answer)
    except AgentOutputError as exc:
        await _record_invalid_output(evaluation_id, "technical", 2, exc)
        raise
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
    if result["decision"] == "FAIL":
        await _db(db.update_evaluation, evaluation_id, status="REJECTED", current_round=2, final_decision="REJECT")
        return
    try:
        question = await run_behavioral_question(evaluation_id, evaluation["resume_text"])
    except AgentOutputError as exc:
        await _record_invalid_output(evaluation_id, "behavioral", 3, exc)
        raise
    await _db(db.save_questions, evaluation_id, 3, question["question"])
    await _db(db.update_evaluation, evaluation_id, current_round=3)


async def handle_behavioral(payload: dict) -> None:
    evaluation_id = int(payload["evaluation_id"])
    evaluation = await _db(db.get_evaluation, evaluation_id)
    if evaluation is None or await _db(db.get_verdict_by_round, evaluation_id, 3):
        return
    answer = await _db(db.get_answer, evaluation_id, 3)
    question = await _db(db.get_questions, evaluation_id, 3) or ""
    if not answer:
        raise ValueError("Behavioral answer is missing")
    try:
        result = await run_behavioral_evaluation(evaluation_id, evaluation["resume_text"], question, answer)
    except AgentOutputError as exc:
        await _record_invalid_output(evaluation_id, "behavioral", 3, exc)
        raise
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
    if result["decision"] == "FAIL":
        await _db(db.update_evaluation, evaluation_id, status="REJECTED", current_round=3, final_decision="REJECT")
    else:
        await _db(db.update_evaluation, evaluation_id, current_round=4)


async def handle_final_decision(payload: dict) -> None:
    evaluation_id = int(payload["evaluation_id"])
    await finalize_evaluation(
        evaluation_id,
        run_recommendation=run_hiring_recommendation,
        run_committee=run_hiring_committee,
    )
