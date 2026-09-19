"""
Crew Runner — Orchestrates agent execution with explicit context passing.

This is the heart of the AGENT CONTEXT architecture. Each agent receives
only the context it is explicitly given. No hidden state, no shared memory.

Pipeline: Screening → Technical → Behavioral → Hiring Recommendation → Committee
"""

import asyncio
import os
import re
import json
import time
import logging
from crewai import Crew

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds to wait on rate-limit


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
from state import VERDICTS_DIR


# ── Helpers ──────────────────────────────────────────────────────────


def _read_verdict(filename: str) -> str:
    """Read a verdict file from DECISION MEMORY."""
    path = os.path.join(VERDICTS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Verdict file not found: {path}")
    with open(path, "r") as f:
        return f.read()


def _write_verdict(filename: str, content: str) -> str:
    """Write a verdict file to DECISION MEMORY and return the path."""
    path = os.path.join(VERDICTS_DIR, filename)
    os.makedirs(VERDICTS_DIR, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return path


def _parse_json_output(raw_text: str) -> dict:
    """
    Parse JSON from agent output. Handles common LLM quirks:
    - Markdown code blocks (```json ... ```)
    - Leading/trailing whitespace
    - Mixed content before/after JSON
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
        logger.debug(f"Raw output: {raw_text[:500]}")
        # Return a minimal fallback
        return {"error": "Failed to parse agent output", "raw": raw_text[:2000]}


def _parse_decision(verdict_text: str) -> str:
    """
    Extract the decision from a verdict string (JSON or plain text).
    """
    # Try JSON first
    try:
        data = json.loads(verdict_text) if isinstance(verdict_text, str) else verdict_text
        if isinstance(data, dict) and "decision" in data:
            return data["decision"].upper()
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback — regex
    match = re.search(
        r"Decision:\s*(PASS|FAIL|BORDERLINE|HIRE|HOLD|REJECT)",
        str(verdict_text),
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()

    # Last resort — keyword search
    upper = str(verdict_text).upper()
    for keyword in ["FAIL", "REJECT", "BORDERLINE", "HOLD", "PASS", "HIRE"]:
        if keyword in upper:
            return keyword
    return "BORDERLINE"


def _extract_score(data: dict) -> float:
    """Extract score from parsed verdict data."""
    if isinstance(data, dict) and "score" in data:
        try:
            return float(data["score"])
        except (ValueError, TypeError):
            pass
    return 0.0


def _extract_confidence(data: dict) -> float:
    """Extract confidence from parsed verdict data."""
    if isinstance(data, dict) and "confidence" in data:
        try:
            return float(data["confidence"])
        except (ValueError, TypeError):
            pass
    return 0.8


# ── Round 1: Screening ──────────────────────────────────────────────


async def run_screening(resume: str, role: str) -> dict:
    """
    Run the Screening Agent.
    AGENT CONTEXT: Resume + target role.
    Writes: verdicts/round1.txt
    """
    agent = create_screening_agent()
    task = create_screening_task(agent, resume, role)

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    # Parse structured output
    verdict_data = _parse_json_output(raw_output)
    decision = _parse_decision(verdict_data)
    score = _extract_score(verdict_data)
    confidence = _extract_confidence(verdict_data)

    # Write to DECISION MEMORY (both JSON and raw)
    _write_verdict("round1.txt", raw_output)
    _write_verdict("round1.json", json.dumps(verdict_data, indent=2))

    return {
        "round": 1,
        "decision": decision,
        "verdict": verdict_data,
        "verdict_text": raw_output,
        "score": score,
        "confidence": confidence,
    }


# ── Round 2: Technical (Question Generation) ────────────────────────


async def run_technical_questions(resume: str) -> dict:
    """
    Generate technical questions.
    AGENT CONTEXT: Resume + round1.txt verdict.
    """
    round1_verdict = _read_verdict("round1.txt")
    agent = create_technical_agent()
    task = create_technical_question_task(agent, resume, round1_verdict)

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    questions = await _run_crew_with_retry(crew)

    return {
        "round": 2,
        "questions": questions,
    }


async def run_technical_evaluation(resume: str, questions: str, answer: str) -> dict:
    """
    Evaluate technical answers.
    AGENT CONTEXT: Resume + round1.txt + candidate answers.
    Writes: verdicts/round2.txt
    """
    round1_verdict = _read_verdict("round1.txt")
    agent = create_technical_agent()
    task = create_technical_evaluation_task(
        agent, resume, round1_verdict, questions, answer
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    decision = _parse_decision(verdict_data)
    score = _extract_score(verdict_data)
    confidence = _extract_confidence(verdict_data)

    _write_verdict("round2.txt", raw_output)
    _write_verdict("round2.json", json.dumps(verdict_data, indent=2))

    return {
        "round": 2,
        "decision": decision,
        "verdict": verdict_data,
        "verdict_text": raw_output,
        "score": score,
        "confidence": confidence,
    }


# ── Round 3: Behavioral (Question Generation) ──────────────────────


async def run_behavioral_question(resume: str) -> dict:
    """
    Generate behavioral question.
    AGENT CONTEXT: Resume + round1.txt + round2.txt.
    """
    round1_verdict = _read_verdict("round1.txt")
    round2_verdict = _read_verdict("round2.txt")
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


async def run_behavioral_evaluation(resume: str, question: str, answer: str) -> dict:
    """
    Evaluate behavioral answer.
    AGENT CONTEXT: Resume + round1.txt + round2.txt + candidate answer.
    Writes: verdicts/round3.txt
    """
    round1_verdict = _read_verdict("round1.txt")
    round2_verdict = _read_verdict("round2.txt")
    agent = create_behavioral_agent()
    task = create_behavioral_evaluation_task(
        agent, resume, round1_verdict, round2_verdict, question, answer
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    decision = _parse_decision(verdict_data)
    score = _extract_score(verdict_data)
    confidence = _extract_confidence(verdict_data)

    _write_verdict("round3.txt", raw_output)
    _write_verdict("round3.json", json.dumps(verdict_data, indent=2))

    return {
        "round": 3,
        "decision": decision,
        "verdict": verdict_data,
        "verdict_text": raw_output,
        "score": score,
        "confidence": confidence,
    }


# ── Round 4: Hiring Recommendation ─────────────────────────────────


async def run_hiring_recommendation() -> dict:
    """
    Run the Hiring Recommendation Agent.
    AGENT CONTEXT: All three round verdicts (no resume, no raw answers).
    Writes: verdicts/round4.txt
    """
    round1_verdict = _read_verdict("round1.txt")
    round2_verdict = _read_verdict("round2.txt")
    round3_verdict = _read_verdict("round3.txt")

    agent = create_hiring_recommendation_agent()
    task = create_hiring_recommendation_task(
        agent, round1_verdict, round2_verdict, round3_verdict
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    decision = _parse_decision(verdict_data)
    score = _extract_score(verdict_data)
    confidence = _extract_confidence(verdict_data)

    _write_verdict("round4.txt", raw_output)
    _write_verdict("round4.json", json.dumps(verdict_data, indent=2))

    return {
        "round": 4,
        "decision": decision,
        "verdict": verdict_data,
        "verdict_text": raw_output,
        "score": score,
        "confidence": confidence,
    }


# ── Final: Committee Evaluator ──────────────────────────────────────


async def run_hiring_committee() -> dict:
    """
    Run the Hiring Committee Agent (Committee Evaluator).
    AGENT CONTEXT: ONLY verdict outputs from all agents (no resume, no raw answers).
    This is a critical design choice — the committee judges on peer verdicts only.
    """
    round1_verdict = _read_verdict("round1.txt")
    round2_verdict = _read_verdict("round2.txt")
    round3_verdict = _read_verdict("round3.txt")
    recommendation = _read_verdict("round4.txt")

    agent = create_hiring_committee_agent()
    task = create_committee_decision_task(
        agent, round1_verdict, round2_verdict, round3_verdict, recommendation
    )

    crew = Crew(agents=[agent], tasks=[task], verbose=True)
    raw_output = await _run_crew_with_retry(crew)

    verdict_data = _parse_json_output(raw_output)
    decision = _parse_decision(verdict_data)
    confidence = _extract_confidence(verdict_data)

    _write_verdict("committee.txt", raw_output)
    _write_verdict("committee.json", json.dumps(verdict_data, indent=2))

    return {
        "decision": decision,
        "verdict": verdict_data,
        "verdict_text": raw_output,
        "confidence": confidence,
    }
