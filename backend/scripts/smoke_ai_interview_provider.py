"""Opt-in live-provider smoke check using only synthetic candidate content.

Usage (PowerShell, from the repository root):
  $env:RUN_LIVE_AI_INTERVIEW_SMOKE = '1'
  # Configure GEMINI_API_KEY or AGENT_BASE_URL (+ AGENT_MODEL/AGENT_API_KEY).
  .\.venv\Scripts\python.exe backend/scripts/smoke_ai_interview_provider.py

This makes paid/provider calls. It never reads real candidate records or prints
prompts, transcripts, raw provider output, credentials, or candidate details.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(REPOSITORY_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env", override=False)

from app.ai_interview import llm  # noqa: E402
from app.ai_interview.dto import AnswerAssessment  # noqa: E402
from app.ai_interview.service import screening_constraints  # noqa: E402


async def _run() -> int:
    if os.getenv("RUN_LIVE_AI_INTERVIEW_SMOKE") != "1":
        print(json.dumps({"status": "SKIPPED", "reason": "Set RUN_LIVE_AI_INTERVIEW_SMOKE=1 to enable paid live-provider calls."}))
        return 2
    if not os.getenv("AGENT_BASE_URL", "").strip() and not os.getenv("GEMINI_API_KEY", "").strip():
        print(json.dumps({"status": "SKIPPED", "reason": "Configure GEMINI_API_KEY or AGENT_BASE_URL before running."}))
        return 2

    policy = {
        "minimum_experience": 3,
        "maximum_experience": 8,
        "required_skills": ["Python", "PostgreSQL"],
        "pass_threshold": 6.0,
        "interview_settings": {"role_level": "MID"},
    }
    profile = {
        "headline": "Synthetic backend engineer",
        "years_experience": 5,
        "skills": [
            {"skill": "Python", "years": 5},
            {"skill": "PostgreSQL", "years": 3},
        ],
    }
    resume = (
        "Synthetic test profile: five years building backend services with Python "
        "and PostgreSQL. No real candidate information is used."
    )
    try:
        screening, _ = await llm.screen_application(
            role="Synthetic Backend Engineer",
            posting_description="Build and operate reliable Python services backed by PostgreSQL.",
            policy=policy,
            profile=profile,
            application_answers=[],
            resume_text=resume,
        )
        screening_issues = screening_constraints(policy, profile, screening, resume, [])
        if screening.decision == "PASS" and screening_issues:
            raise RuntimeError("The model proposed PASS despite invalid or ungrounded screening evidence")

        answer = "I designed a bounded retry policy and measured recovery with synthetic service metrics."
        assessment, _ = await llm.assess_answer(
            role="Synthetic Backend Engineer",
            policy=policy,
            phase="TECHNICAL",
            competency={"key": "reliability", "label": "Service reliability", "description": "Explain safe recovery behavior."},
            difficulty=2,
            question="How would you make a service recover safely from a dependency outage?",
            answer=answer,
            prior_turns=[],
            followups_remaining=1,
        )
        quote = assessment.evidence_quote.strip()
        answer_evidence = "GROUNDED" if quote and quote in answer else "REVIEW_REQUIRED"
        if assessment.follow_up_question and len(assessment.follow_up_question.strip()) < 12:
            raise RuntimeError("The provider returned a follow-up shorter than the server contract")

        print(json.dumps({
            "status": "PASS",
            "provider_calls": 2,
            "screening_schema_valid": True,
            "screening_decision": screening.decision,
            "screening_grounding": "GROUNDED" if not screening_issues else "REVIEW_REQUIRED",
            "answer_schema_valid": True,
            "answer_evidence": answer_evidence,
            "answer_follow_up_returned": bool(assessment.follow_up_question),
            "data_source": "synthetic-only",
        }, sort_keys=True))
        return 0
    except Exception as error:  # Do not print provider payloads or exception text.
        print(json.dumps({
            "status": "FAIL",
            "error_type": type(error).__name__,
            "data_source": "synthetic-only",
        }, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
