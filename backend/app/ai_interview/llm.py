"""Typed CrewAI adapter for the durable application AI interview pipeline."""

from app.ai_interview.agents import (
    create_application_screening_agent,
    create_interview_assessor_agent,
)
from app.ai_interview.dto import ApplicationScreeningAssessment, AnswerAssessment
from app.ai_interview.tasks import (
    create_answer_assessment_task,
    create_application_screening_task,
)
from app.evaluation.runner import run_structured_agent_task


async def screen_application(
    *,
    role: str,
    posting_description: str,
    policy: dict,
    profile: dict,
    application_answers: list[dict],
    resume_text: str,
) -> tuple[ApplicationScreeningAssessment, str]:
    agent = create_application_screening_agent()
    task = create_application_screening_task(
        agent,
        role=role,
        posting_description=posting_description,
        policy=policy,
        profile=profile,
        application_answers=application_answers,
        resume_text=resume_text,
    )
    result, raw = await run_structured_agent_task(agent, task, ApplicationScreeningAssessment, stage="application_screening")
    return result, raw


async def assess_answer(
    *,
    role: str,
    policy: dict,
    phase: str,
    competency: dict,
    difficulty: int,
    question: str,
    answer: str,
    prior_turns: list[dict],
    followups_remaining: int,
) -> tuple[AnswerAssessment, str]:
    agent = create_interview_assessor_agent()
    task = create_answer_assessment_task(
        agent,
        role=role,
        policy=policy,
        phase=phase,
        competency=competency,
        difficulty=difficulty,
        question=question,
        answer=answer,
        prior_turns=prior_turns,
        followups_remaining=followups_remaining,
    )
    result, raw = await run_structured_agent_task(agent, task, AnswerAssessment, stage="application_interview_answer")
    return result, raw
