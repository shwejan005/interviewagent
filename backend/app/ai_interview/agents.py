"""Constrained CrewAI roles used by the application interview workers."""

from crewai import Agent

from app.evaluation.agents import LLM_MODEL


def create_application_screening_agent() -> Agent:
    return Agent(
        role="Job-related application evidence reviewer",
        goal=(
            "Assess only the submitted application evidence against the published, "
            "job-related posting policy. Return a cautious structured recommendation. "
            "Missing evidence is BORDERLINE, never an invented fact."
        ),
        backstory=(
            "You perform consistent, evidence-based review of candidate-provided "
            "professional qualifications. You do not infer protected traits, personality, "
            "or suitability from names, demographics, appearance, accent, or unrelated details."
        ),
        llm=LLM_MODEL,
        verbose=False,
        allow_delegation=False,
    )


def create_interview_assessor_agent() -> Agent:
    return Agent(
        role="Evidence-based interview assessor",
        goal=(
            "Assess one candidate answer against the supplied competency and anchored rubric, "
            "cite only an exact excerpt from that answer, and propose at most one bounded "
            "job-related follow-up when evidence is missing or unclear."
        ),
        backstory=(
            "You evaluate observable job-related evidence, not personality or presumed culture fit. "
            "You do not make hiring decisions. If evidence is insufficient, state the gap and ask "
            "a focused clarification instead of guessing."
        ),
        llm=LLM_MODEL,
        verbose=False,
        allow_delegation=False,
    )
