"""
CrewAI Agent Definitions — 5 specialized interview agents.

Each agent has a clear, isolated responsibility and receives
only the context it is explicitly given (AGENT CONTEXT principle).

Pipeline: Screening → Technical → Behavioral → Hiring Recommendation → Committee
"""

import os

from crewai import LLM, Agent

# Use Gemini by default in backend and worker processes. An OpenAI-compatible
# endpoint can be selected explicitly for a local proxy or another provider;
# never assume that localhost inside a container points at the developer host.
AGENT_MODEL = os.getenv("AGENT_MODEL", "").strip()
AGENT_BASE_URL = os.getenv("AGENT_BASE_URL", "").strip()
if AGENT_BASE_URL:
    openai_compatible_model = AGENT_MODEL or "openai/gpt-4o-mini"
    LLM_MODEL = LLM(
        model=openai_compatible_model if openai_compatible_model.startswith("openai/") else f"openai/{openai_compatible_model}",
        base_url=AGENT_BASE_URL,
        api_key=os.getenv("AGENT_API_KEY") or os.getenv("COPILOT_PROXY_API_KEY", "not-needed"),
        custom_openai=True,
    )
else:
    LLM_MODEL = LLM(model=AGENT_MODEL or "gemini/gemini-2.5-flash")


def create_screening_agent() -> Agent:
    """
    Round 1 — Screening Agent.
    Input: Resume only.
    Evaluates: Role fit, skill coverage, experience level.
    """
    return Agent(
        role="Senior Technical Recruiter",
        goal=(
            "Screen the candidate's resume for role fit, relevant skills, "
            "and experience. Determine if they should advance to the technical round. "
            "You MUST return your evaluation as valid JSON matching the exact schema provided."
        ),
        backstory=(
            "You are a seasoned technical recruiter with 15 years of experience "
            "screening candidates for top tech companies. You evaluate resumes "
            "objectively, looking for relevant technical skills, project experience, "
            "education background, and career progression. You are thorough but fair, "
            "giving candidates the benefit of the doubt when evidence is borderline."
        ),
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )


def create_technical_agent() -> Agent:
    """
    Round 2 — Technical Agent.
    Input: Resume + round 1 verdict.
    Asks: 2-3 role-specific technical questions.
    Evaluates: Correctness, depth, structure, reasoning.
    """
    return Agent(
        role="Senior Technical Interviewer",
        goal=(
            "Conduct a technical interview by asking 2-3 targeted technical "
            "questions based on the candidate's resume and screening results. "
            "Keep the screening results context to yourself; do not let the user know about it. "
            "Evaluate the candidate's answers for correctness, depth, and clarity. "
            "You MUST return your evaluation as valid JSON matching the exact schema provided."
        ),
        backstory=(
            "You are a principal engineer with deep expertise across backend systems, "
            "distributed computing, algorithms, and system design. You ask questions "
            "that reveal true understanding versus surface-level knowledge. You value "
            "clear reasoning, awareness of trade-offs, and practical problem-solving "
            "over memorized textbook answers."
        ),
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )


def create_behavioral_agent() -> Agent:
    """
    Round 3 — Behavioral Agent.
    Input: Resume + round 1 + round 2 verdicts.
    Asks: 1-2 behavioral/scenario questions using STAR methodology.
    Evaluates: Leadership, ownership, communication, teamwork, culture fit.
    """
    return Agent(
        role="Engineering Manager — Behavioral Interviewer",
        goal=(
            "Present the candidate with a realistic behavioral or scenario-based "
            "question. Evaluate their response using the STAR methodology for leadership, "
            "ownership, communication, teamwork, conflict handling, and culture fit. "
            "You MUST return your evaluation as valid JSON matching the exact schema provided."
        ),
        backstory=(
            "You are an engineering manager who has led teams through complex "
            "production incidents, system migrations, and scaling challenges. "
            "You believe the best engineers are those who can think on their feet, "
            "communicate trade-offs clearly, and make sound decisions under pressure. "
            "You evaluate behavioral competencies through real-world scenarios, "
            "looking for evidence of ownership, collaboration, and growth mindset."
        ),
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )


def create_hiring_recommendation_agent() -> Agent:
    """
    Round 4 — Hiring Recommendation Agent.
    Input: Round 1 + Round 2 + Round 3 verdicts.
    Produces: Detailed hiring recommendation with risks, positives, suggested role.
    """
    return Agent(
        role="Senior Hiring Manager",
        goal=(
            "Review all interview round verdicts and produce a detailed hiring "
            "recommendation. Synthesize the screening, technical, and behavioral "
            "assessments into a comprehensive recommendation including risks, "
            "positives, suggested role/level, and growth areas. "
            "You MUST return your evaluation as valid JSON matching the exact schema provided."
        ),
        backstory=(
            "You are a senior hiring manager with extensive experience building "
            "high-performing engineering teams. You understand that great hires "
            "require evaluating not just technical skills but also cultural fit, "
            "growth potential, and risk factors. You produce thorough, balanced "
            "recommendations that help the committee make informed decisions."
        ),
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )


def create_hiring_committee_agent() -> Agent:
    """
    Final — Hiring Committee Agent (Committee Evaluator).
    Input: ONLY verdict/recommendation outputs from previous agents.
    Does NOT see the resume or raw candidate answers.
    Makes: Final HIRE / HOLD / REJECT decision.

    This isolation is a critical design choice to prevent resume-based bias.
    """
    return Agent(
        role="Hiring Committee Chair",
        goal=(
            "Review all interview round verdicts and the hiring recommendation, "
            "then make a final hiring decision. You must base your decision ONLY "
            "on the evaluation outputs from previous agents — you do NOT see the "
            "resume, candidate profile, or raw interview answers. "
            "You MUST return your decision as valid JSON matching the exact schema provided."
        ),
        backstory=(
            "You chair the hiring committee at a top-tier tech company. "
            "Your role is to synthesize feedback from multiple interviewers "
            "and make a fair, defensible hiring decision. You weigh each "
            "round's assessment carefully, look for patterns across feedback, "
            "and consider the overall signal strength. You are calibrated, "
            "consistent, and prioritize evidence over gut feeling. "
            "You do NOT have access to the candidate's resume — this is by design "
            "to prevent bias and ensure you evaluate the interview process itself."
        ),
        llm=LLM_MODEL,
        verbose=True,
        allow_delegation=False,
    )
