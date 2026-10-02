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
import random
import logging
import time
from typing import Type, TypeVar

from crewai import Crew
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = float(os.getenv("AGENT_RETRY_BASE_DELAY_SECONDS", "1"))
RETRY_MAX_DELAY_SECONDS = float(os.getenv("AGENT_RETRY_MAX_DELAY_SECONDS", "60"))
RETRY_JITTER_RATIO = float(os.getenv("AGENT_RETRY_JITTER_RATIO", "0.2"))
STAGE_TIMEOUT_SECONDS = float(os.getenv("AGENT_STAGE_TIMEOUT_SECONDS", "180"))


class TransientAgentError(Exception):
    """A provider failure that may succeed when retried later."""

    def __init__(self, message: str, *, stage: str, retry_after: float | None = None):
        super().__init__(message)
        self.stage = stage
        self.retry_after = retry_after


class AgentRateLimitError(TransientAgentError):
    """The provider rejected work because of quota or rate limiting."""


class AgentProviderError(TransientAgentError):
    """A transient network or upstream provider failure."""


class AgentTimeoutError(TransientAgentError):
    """A stage exceeded its configured execution deadline."""


class AgentOutputError(Exception):
    """Raised when agent output fails to parse or validate against its schema.

    This must never be silently converted into a PASS/FAIL/HIRE/REJECT
    decision — callers persist it as a distinct, clearly-labeled failure for
    human triage and surface an explicit error to the client.
    """

    def __init__(self, message: str, raw_output: str):
        super().__init__(message)
        self.raw_output = raw_output


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text or "quota" in text or "rate limit" in text


def _is_provider_transient_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in ("timeout", "timed out", "temporarily unavailable", "connection reset", "502", "503", "504")
    )


def _as_transient_error(error: Exception, *, stage: str) -> TransientAgentError | None:
    if _is_rate_limit_error(error):
        return AgentRateLimitError(str(error), stage=stage)
    if _is_provider_transient_error(error):
        return AgentProviderError(str(error), stage=stage)
    return None


def _retry_delay(attempt: int, *, random_value: float | None = None) -> float:
    """Return a capped exponential delay with bounded multiplicative jitter."""
    base = min(
        RETRY_MAX_DELAY_SECONDS,
        RETRY_BASE_DELAY_SECONDS * (2 ** max(attempt - 1, 0)),
    )
    jitter = random.uniform(1 - RETRY_JITTER_RATIO, 1 + RETRY_JITTER_RATIO)
    if random_value is not None:
        jitter = random_value
    return min(RETRY_MAX_DELAY_SECONDS, max(0.0, base * jitter))


def _run_crew_with_retry_sync(crew: Crew, *, stage: str) -> str:
    """Run a CrewAI Crew with typed transient-error retries (sync)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = crew.kickoff()
            return str(result)
        except Exception as error:
            transient_error = _as_transient_error(error, stage=stage)
            if transient_error is None or attempt >= MAX_RETRIES:
                if transient_error is not None:
                    raise transient_error from error
                raise
            wait = _retry_delay(attempt)
            logger.warning(
                "Transient agent error at stage %s (attempt %s/%s). Retrying in %.2fs.",
                stage,
                attempt,
                MAX_RETRIES,
                wait,
            )
            time.sleep(wait)


async def _run_crew_with_retry(
    crew: Crew,
    *,
    stage: str,
    timeout_seconds: float = STAGE_TIMEOUT_SECONDS,
) -> str:
    """Run a stage off the event loop with a hard request-side deadline."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_crew_with_retry_sync, crew, stage=stage),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as error:
        raise AgentTimeoutError(
            f"Agent stage {stage} exceeded its {timeout_seconds:.1f}s deadline.",
            stage=stage,
        ) from error


async def run_structured_agent_task(agent, task, schema: Type[BaseModel], *, stage: str) -> tuple[BaseModel, str]:
    """Run a single CrewAI task and enforce its Pydantic result contract.

    Unlike the legacy evaluation helpers below, this boundary does not read or
    write verdict files. Application-linked interview workflows keep their
    complete context in database-owned records so a worker restart or a second
    worker cannot lose the conversation state.
    """
    crew = Crew(agents=[agent], tasks=[task], verbose=False)
    raw_output = await _run_crew_with_retry(crew, stage=stage)
    parsed = _parse_json_output(raw_output)
    return _validate_verdict(parsed, schema, raw_output), raw_output


from app.evaluation.agents import (
    create_screening_agent,
    create_technical_agent,
    create_behavioral_agent,
    create_hiring_recommendation_agent,
    create_hiring_committee_agent,
)
from app.evaluation.tasks import (
    create_screening_task,
    create_technical_question_task,
    create_technical_evaluation_task,
    create_behavioral_question_task,
    create_behavioral_evaluation_task,
    create_hiring_recommendation_task,
    create_committee_decision_task,
)
from app.evaluation.dto import (
    ScreeningVerdict,
    TechnicalVerdict,
    BehavioralVerdict,
    HiringRecommendation,
    CommitteeDecision,
)
from app.evaluation.state import eval_verdicts_dir

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
    raw_output = await _run_crew_with_retry(crew, stage="screening")

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
    questions = await _run_crew_with_retry(crew, stage="technical_questions")

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
    raw_output = await _run_crew_with_retry(crew, stage="technical_evaluation")

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
    question = await _run_crew_with_retry(crew, stage="behavioral_question")

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
    raw_output = await _run_crew_with_retry(crew, stage="behavioral_evaluation")

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
    raw_output = await _run_crew_with_retry(crew, stage="hiring_recommendation")

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
    raw_output = await _run_crew_with_retry(crew, stage="hiring_committee")

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

