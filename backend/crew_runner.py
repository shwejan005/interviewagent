"""
Crew Runner — Orchestrates agent execution with explicit context passing.

This is the heart of the AGENT CONTEXT architecture. Each agent receives
only the context it is explicitly given. No hidden state, no shared memory.

Pipeline: Screening → Technical → Behavioral → Hiring Recommendation → Committee

Every verdict-producing function validates the agent's raw output against its
Pydantic schema. Malformed output (invalid JSON, wrong types, out-of-range
scores, or a decision outside the allowed enum) never becomes a business
decision — it raises AgentOutputError, which the caller must handle explicitly
(see routes.py) instead of silently defaulting to a score, decision, or
confidence value.
"""

import asyncio
import os
import re
import json
import time
import logging
from typing import Type, TypeVar

from crewai import Crew
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds to wait on rate-limit


class AgentOutputError(Exception):
    """Raised when agent output fails to parse or validate against its schema.

    This must never be silently converted into a PASS/FAIL/HIRE/REJECT
    decision — callers persist it as a distinct, clearly-labeled failure for
    human triage and surface an explicit error to the client.
    """

    def __init__(self, message: str, raw_output: str):
        super().__init__(message)
        self.raw_output = raw_output


def _run_crew_with_retry_sync(crew: Crew) -> str:
    """Run a CrewAI Crew with retry logic for rate-limit errors (sync)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = crew.kickoff()
            return str(result)
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                if attempt < MAX_RETRIES:
                    wait = RETRY_DELAY * attempt
                    logger.warning(
                        f"Rate limited (attempt {attempt}/{MAX_RETRIES}). "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                    continue
            raise


async def _run_crew_with_retry(crew: Crew) -> str:
    """Async wrapper — offloads sync crew.kickoff() to a thread."""
    return await asyncio.to_thread(_run_crew_with_retry_sync, crew)


from agents import (
    create_screening_agent,
    create_technical_agent,
    create_behavioral_agent,
    create_hiring_recommendation_agent,
    create_hiring_committee_agent,
)
from tasks import (
    create_screening_task,
    create_technical_question_task,
    create_technical_evaluation_task,
    create_behavioral_question_task,
    create_behavioral_evaluation_task,
    create_hiring_recommendation_task,
    create_committee_decision_task,
)
from models import (
    ScreeningVerdict,
    TechnicalVerdict,
    BehavioralVerdict,
    HiringRecommendation,
    CommitteeDecision,
)
from state import eval_verdicts_dir

VerdictT = TypeVar("VerdictT", bound=BaseModel)


# ── Helpers ──────────────────────────────────────────────────────────


def _read_verdict(evaluation_id: int, filename: str) -> str:
    """Read a verdict file from this evaluation's DECISION MEMORY."""
    path = os.path.join(eval_verdicts_dir(evaluation_id), filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Verdict file not found: {path}")
    with open(path, "r") as f:
        return f.read()


def _write_verdict(evaluation_id: int, filename: str, content: str) -> str:
    """Write a verdict file to this evaluation's DECISION MEMORY and return the path."""
    path = os.path.join(eval_verdicts_dir(evaluation_id), filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _parse_json_output(raw_text: str) -> dict:
    """
    Extract and parse a JSON object from raw agent output. Handles common LLM
    quirks (markdown code fences, surrounding prose) but never fabricates a
    fallback value — invalid JSON raises AgentOutputError.
    """
    text = raw_text.strip()

    # Try to extract from markdown code block
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1).strip()

    # Try to find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON output: {e}")
        raise AgentOutputError(f"Agent output is not valid JSON: {e}", raw_text) from e


def _validate_verdict(data: dict, schema: Type[VerdictT], raw_output: str) -> VerdictT:
    """Validate parsed JSON against the agent's declared Pydantic schema.

    Enforces the allowed decision enum, numeric bounds, and required fields
    (including confidence — the agent must assert it explicitly; there is no
    silent default). Any violation raises AgentOutputError.
    """
    if not isinstance(data, dict):
        raise AgentOutputError("Agent output JSON is not an object.", raw_output)
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        logger.warning(f"Agent output failed schema validation: {e}")
        raise AgentOutputError(f"Agent output failed schema validation: {e}", raw_output) from e


# ── Round 1: Screening ──────────────────────────────────────────────


async def run_screening(evaluation_id: int, resume: str, role: str) -> dict:
    """
    Run the Screening Agent.
    AGENT CONTEXT: Resume + target role.
    Writes: verdicts/{evaluation_id}/round1.txt

    Raises AgentOutputError if the agent's output cannot be validated —
    callers must not treat this as a PASS/FAIL/BORDERLINE decision.
    """
    agent = create_screening_agent()
    task = create_screening_task(agent, resume, role)

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    verdict = _validate_verdict(verdict_data, ScreeningVerdict, raw_output)

    _write_verdict(evaluation_id, "round1.txt", raw_output)
    _write_verdict(evaluation_id, "round1.json", verdict.model_dump_json(indent=2))

    return {
        "round": 1,
        "decision": verdict.decision.value,
        "verdict": verdict.model_dump(mode="json"),
        "verdict_text": raw_output,
        "score": verdict.score,
        "confidence": verdict.confidence,
    }


# ── Round 2: Technical (Question Generation) ────────────────────────


async def run_technical_questions(evaluation_id: int, resume: str) -> dict:
    """
    Generate technical questions.
    AGENT CONTEXT: Resume + round1.txt verdict.
    """
    round1_verdict = _read_verdict(evaluation_id, "round1.txt")
    agent = create_technical_agent()
    task = create_technical_question_task(agent, resume, round1_verdict)

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    questions = await _run_crew_with_retry(crew)

    return {
        "round": 2,
        "questions": questions,
    }


async def run_technical_evaluation(evaluation_id: int, resume: str, questions: str, answer: str) -> dict:
    """
    Evaluate technical answers.
    AGENT CONTEXT: Resume + round1.txt + candidate answers.
    Writes: verdicts/{evaluation_id}/round2.txt
    """
    round1_verdict = _read_verdict(evaluation_id, "round1.txt")
    agent = create_technical_agent()
    task = create_technical_evaluation_task(
        agent, resume, round1_verdict, questions, answer
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    verdict = _validate_verdict(verdict_data, TechnicalVerdict, raw_output)

    _write_verdict(evaluation_id, "round2.txt", raw_output)
    _write_verdict(evaluation_id, "round2.json", verdict.model_dump_json(indent=2))

    return {
        "round": 2,
        "decision": verdict.decision.value,
        "verdict": verdict.model_dump(mode="json"),
        "verdict_text": raw_output,
        "score": verdict.score,
        "confidence": verdict.confidence,
    }


# ── Round 3: Behavioral (Question Generation) ──────────────────────


async def run_behavioral_question(evaluation_id: int, resume: str) -> dict:
    """
    Generate behavioral question.
    AGENT CONTEXT: Resume + round1.txt + round2.txt.
    """
    round1_verdict = _read_verdict(evaluation_id, "round1.txt")
    round2_verdict = _read_verdict(evaluation_id, "round2.txt")
    agent = create_behavioral_agent()
    task = create_behavioral_question_task(
        agent, resume, round1_verdict, round2_verdict
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    question = await _run_crew_with_retry(crew)

    return {
        "round": 3,
        "question": question,
    }


async def run_behavioral_evaluation(evaluation_id: int, resume: str, question: str, answer: str) -> dict:
    """
    Evaluate behavioral answer.
    AGENT CONTEXT: Resume + round1.txt + round2.txt + candidate answer.
    Writes: verdicts/{evaluation_id}/round3.txt
    """
    round1_verdict = _read_verdict(evaluation_id, "round1.txt")
    round2_verdict = _read_verdict(evaluation_id, "round2.txt")
    agent = create_behavioral_agent()
    task = create_behavioral_evaluation_task(
        agent, resume, round1_verdict, round2_verdict, question, answer
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    verdict = _validate_verdict(verdict_data, BehavioralVerdict, raw_output)

    _write_verdict(evaluation_id, "round3.txt", raw_output)
    _write_verdict(evaluation_id, "round3.json", verdict.model_dump_json(indent=2))

    return {
        "round": 3,
        "decision": verdict.decision.value,
        "verdict": verdict.model_dump(mode="json"),
        "verdict_text": raw_output,
        "score": verdict.score,
        "confidence": verdict.confidence,
    }


# ── Round 4: Hiring Recommendation ─────────────────────────────────


async def run_hiring_recommendation(evaluation_id: int) -> dict:
    """
    Run the Hiring Recommendation Agent.
    AGENT CONTEXT: All three round verdicts (no resume, no raw answers).
    Writes: verdicts/{evaluation_id}/round4.txt
    """
    round1_verdict = _read_verdict(evaluation_id, "round1.txt")
    round2_verdict = _read_verdict(evaluation_id, "round2.txt")
    round3_verdict = _read_verdict(evaluation_id, "round3.txt")

    agent = create_hiring_recommendation_agent()
    task = create_hiring_recommendation_task(
        agent, round1_verdict, round2_verdict, round3_verdict
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    verdict = _validate_verdict(verdict_data, HiringRecommendation, raw_output)

    _write_verdict(evaluation_id, "round4.txt", raw_output)
    _write_verdict(evaluation_id, "round4.json", verdict.model_dump_json(indent=2))

    return {
        "round": 4,
        "decision": verdict.decision.value,
        "verdict": verdict.model_dump(mode="json"),
        "verdict_text": raw_output,
        "score": verdict.score,
        "confidence": verdict.confidence,
    }


# ── Final: Committee Evaluator ──────────────────────────────────────


async def run_hiring_committee(evaluation_id: int) -> dict:
    """
    Run the Hiring Committee Agent (Committee Evaluator).
    AGENT CONTEXT: ONLY verdict outputs from all agents (no resume, no raw answers).
    This is a critical design choice — the committee judges on peer verdicts only.
    """
    round1_verdict = _read_verdict(evaluation_id, "round1.txt")
    round2_verdict = _read_verdict(evaluation_id, "round2.txt")
    round3_verdict = _read_verdict(evaluation_id, "round3.txt")
    recommendation = _read_verdict(evaluation_id, "round4.txt")

    agent = create_hiring_committee_agent()
    task = create_committee_decision_task(
        agent, round1_verdict, round2_verdict, round3_verdict, recommendation
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    verdict = _validate_verdict(verdict_data, CommitteeDecision, raw_output)

    _write_verdict(evaluation_id, "committee.txt", raw_output)
    _write_verdict(evaluation_id, "committee.json", verdict.model_dump_json(indent=2))

    return {
        "decision": verdict.decision.value,
        "verdict": verdict.model_dump(mode="json"),
        "verdict_text": raw_output,
        "confidence": verdict.confidence,
    }

