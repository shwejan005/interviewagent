"""
CrewAI Task Definitions — one task per interview round.

All tasks demand JSON output with explicit schemas to ensure
deterministic, parseable, and validateable agent responses.
Context is injected at runtime by crew_runner.py (AGENT CONTEXT principle).
"""

from crewai import Task, Agent
import json


# ── JSON Schema Strings ─────────────────────────────────────────────

SCREENING_SCHEMA = json.dumps({
    "decision": "PASS | BORDERLINE | FAIL",
    "score": "number 0-10",
    "strengths": ["string"],
    "weaknesses": ["string"],
    "reasoning": "string",
    "candidate_summary": "string",
    "skills_extracted": ["string"],
    "experience_years": "number or null",
    "recommended_questions": ["string"],
    "confidence": "number 0-1"
}, indent=2)

TECHNICAL_SCHEMA = json.dumps({
    "decision": "PASS | FAIL",
    "score": "number 0-10",
    "question_evaluations": [
        {
            "question": "string",
            "correctness": "number 0-10",
            "depth": "number 0-10",
            "clarity": "number 0-10",
            "assessment": "string"
        }
    ],
    "strengths": ["string"],
    "weaknesses": ["string"],
    "reasoning": "string",
    "coding_quality": "number 0-10 or null",
    "confidence": "number 0-1"
}, indent=2)

BEHAVIORAL_SCHEMA = json.dumps({
    "decision": "PASS | BORDERLINE | FAIL",
    "score": "number 0-10",
    "star_evaluation": "string",
    "leadership": "number 0-10",
    "communication": "number 0-10",
    "teamwork": "number 0-10",
    "ownership": "number 0-10",
    "conflict_handling": "number 0-10",
    "culture_fit": "number 0-10",
    "strengths": ["string"],
    "weaknesses": ["string"],
    "reasoning": "string",
    "confidence": "number 0-1"
}, indent=2)

RECOMMENDATION_SCHEMA = json.dumps({
    "decision": "HIRE | HOLD | REJECT",
    "score": "number 0-10",
    "detailed_recommendation": "string",
    "risks": ["string"],
    "positives": ["string"],
    "suggested_role": "string",
    "growth_areas": ["string"],
    "confidence": "number 0-1"
}, indent=2)

COMMITTEE_SCHEMA = json.dumps({
    "decision": "HIRE | HOLD | REJECT",
    "confidence": "number 0-1",
    "executive_summary": "string",
    "round_summaries": [
        {
            "round_name": "string",
            "decision": "string",
            "score": "number 0-10",
            "key_finding": "string"
        }
    ],
    "overall_assessment": "string",
    "recommendation": "string",
    "hiring_risks": ["string"],
    "strengths_summary": ["string"],
    "weaknesses_summary": ["string"]
}, indent=2)


# ── Round 1: Screening ──────────────────────────────────────────────


def create_screening_task(agent: Agent, resume: str, role: str) -> Task:
    """
    Screening task — agent evaluates resume against a specific role.
    Returns structured JSON verdict.
    """
    return Task(
        description=(
            f"You are conducting a resume screening for the **{role}** role.\n\n"
            f"## TARGET ROLE\n{role}\n\n"
            f"## CANDIDATE RESUME\n{resume}\n\n"
            f"## YOUR TASK\n"
            f"1. Evaluate the resume specifically for the **{role}** role — assess role fit, relevant skills, and experience.\n"
            f"2. Extract all technical skills mentioned.\n"
            f"3. Estimate years of experience.\n"
            f"4. Write a brief candidate summary.\n"
            f"5. Identify strengths and weaknesses relative to the {role} position.\n"
            f"6. Decide: PASS, BORDERLINE, or FAIL.\n"
            f"7. Assign a score from 0 to 10.\n"
            f"8. Generate 2-3 technical questions for the next round.\n"
            f"9. Rate your confidence in this assessment from 0 to 1.\n\n"
            f"## CRITICAL: OUTPUT FORMAT\n"
            f"You MUST return ONLY valid JSON matching this exact schema. No markdown, no explanation outside the JSON.\n\n"
            f"```json\n{SCREENING_SCHEMA}\n```\n\n"
            f"Return ONLY the JSON object, nothing else."
        ),
        expected_output=(
            "A single valid JSON object matching the screening verdict schema with "
            "decision, score, strengths, weaknesses, reasoning, candidate_summary, "
            "skills_extracted, experience_years, recommended_questions, and confidence."
        ),
        agent=agent,
    )


# ── Round 2: Technical ──────────────────────────────────────────────


def create_technical_question_task(
    agent: Agent,
    resume: str,
    round1_verdict: str,
) -> Task:
    """
    Technical round — generate questions based on resume + screening verdict.
    """
    return Task(
        description=(
            f"You are conducting a technical interview.\n\n"
            f"## CANDIDATE RESUME\n{resume}\n\n"
            f"## SCREENING VERDICT (Round 1)\n{round1_verdict}\n\n"
            f"## YOUR TASK\n"
            f"Based on the resume and the screening verdict, generate exactly "
            f"2-3 targeted technical questions. The questions should:\n"
            f"- Probe the candidate's claimed skills and address weaknesses noted in screening\n"
            f"- Test practical understanding, not just textbook knowledge\n"
            f"- Be appropriate for the role level\n\n"
            f"## OUTPUT FORMAT\n"
            f"Return ONLY the questions, numbered 1-3. No other text.\n\n"
            f"1. [question]\n"
            f"2. [question]\n"
            f"3. [question]"
        ),
        expected_output="2-3 targeted technical questions, numbered.",
        agent=agent,
    )


def create_technical_evaluation_task(
    agent: Agent,
    resume: str,
    round1_verdict: str,
    questions: str,
    answer: str,
) -> Task:
    """
    Technical round — evaluate candidate's answers.
    Returns structured JSON verdict.
    """
    return Task(
        description=(
            f"You are evaluating a candidate's technical interview answers.\n\n"
            f"## CANDIDATE RESUME\n{resume}\n\n"
            f"## SCREENING VERDICT (Round 1)\n{round1_verdict}\n\n"
            f"## TECHNICAL QUESTIONS ASKED\n{questions}\n\n"
            f"## CANDIDATE'S ANSWERS\n{answer}\n\n"
            f"## YOUR TASK\n"
            f"1. Evaluate each answer for correctness, depth, and clarity (score each 0-10).\n"
            f"2. Identify overall technical strengths and weaknesses.\n"
            f"3. Assess coding quality if code was provided.\n"
            f"4. Decide: PASS or FAIL.\n"
            f"5. Assign an overall score from 0 to 10.\n"
            f"6. Rate your confidence from 0 to 1.\n\n"
            f"## CRITICAL: OUTPUT FORMAT\n"
            f"You MUST return ONLY valid JSON matching this exact schema. No markdown, no explanation outside the JSON.\n\n"
            f"```json\n{TECHNICAL_SCHEMA}\n```\n\n"
            f"Return ONLY the JSON object, nothing else."
        ),
        expected_output=(
            "A single valid JSON object matching the technical verdict schema with "
            "decision, score, question_evaluations, strengths, weaknesses, reasoning, "
            "coding_quality, and confidence."
        ),
        agent=agent,
    )


# ── Round 3: Behavioral ────────────────────────────────────────────


def create_behavioral_question_task(
    agent: Agent,
    resume: str,
    round1_verdict: str,
    round2_verdict: str,
) -> Task:
    """
    Behavioral round — generate a behavioral/scenario question using STAR methodology.
    """
    return Task(
        description=(
            f"You are designing a behavioral interview question.\n\n"
            f"## CANDIDATE RESUME\n{resume}\n\n"
            f"## SCREENING VERDICT (Round 1)\n{round1_verdict}\n\n"
            f"## TECHNICAL VERDICT (Round 2)\n{round2_verdict}\n\n"
            f"## YOUR TASK\n"
            f"Based on the candidate's background and previous round performance, "
            f"create 1-2 behavioral questions that test:\n"
            f"- Leadership and ownership\n"
            f"- Teamwork and conflict resolution\n"
            f"- Decision-making under pressure\n"
            f"- Communication and collaboration\n\n"
            f"The questions should invite STAR-format responses (Situation, Task, Action, Result).\n"
            f"Make them specific to their skill set and experience level.\n\n"
            f"## OUTPUT FORMAT\n"
            f"Return ONLY the question(s). No other text.\n\n"
            f"1. [question]\n"
            f"2. [question] (optional)"
        ),
        expected_output="1-2 behavioral interview questions designed for STAR responses.",
        agent=agent,
    )


def create_behavioral_evaluation_task(
    agent: Agent,
    resume: str,
    round1_verdict: str,
    round2_verdict: str,
    question: str,
    answer: str,
) -> Task:
    """
    Behavioral round — evaluate candidate's response using STAR methodology.
    Returns structured JSON verdict.
    """
    return Task(
        description=(
            f"You are evaluating a candidate's behavioral interview response.\n\n"
            f"## CANDIDATE RESUME\n{resume}\n\n"
            f"## SCREENING VERDICT (Round 1)\n{round1_verdict}\n\n"
            f"## TECHNICAL VERDICT (Round 2)\n{round2_verdict}\n\n"
            f"## BEHAVIORAL QUESTION ASKED\n{question}\n\n"
            f"## CANDIDATE'S RESPONSE\n{answer}\n\n"
            f"## YOUR TASK\n"
            f"1. Evaluate using STAR methodology — did they provide Situation, Task, Action, Result?\n"
            f"2. Score each dimension (0-10): leadership, communication, teamwork, ownership, conflict_handling, culture_fit.\n"
            f"3. Identify behavioral strengths and weaknesses.\n"
            f"4. Decide: PASS, BORDERLINE, or FAIL.\n"
            f"5. Assign an overall score from 0 to 10.\n"
            f"6. Rate your confidence from 0 to 1.\n\n"
            f"## CRITICAL: OUTPUT FORMAT\n"
            f"You MUST return ONLY valid JSON matching this exact schema. No markdown, no explanation outside the JSON.\n\n"
            f"```json\n{BEHAVIORAL_SCHEMA}\n```\n\n"
            f"Return ONLY the JSON object, nothing else."
        ),
        expected_output=(
            "A single valid JSON object matching the behavioral verdict schema with "
            "decision, score, star_evaluation, leadership, communication, teamwork, "
            "ownership, conflict_handling, culture_fit, strengths, weaknesses, reasoning, "
            "and confidence."
        ),
        agent=agent,
    )


# ── Round 4: Hiring Recommendation ─────────────────────────────────


def create_hiring_recommendation_task(
    agent: Agent,
    round1_verdict: str,
    round2_verdict: str,
    round3_verdict: str,
) -> Task:
    """
    Hiring Recommendation — synthesizes all previous agent evaluations.
    Receives outputs from Screening, Technical, and Behavioral agents.
    Returns structured JSON recommendation.
    """
    return Task(
        description=(
            f"You are producing a hiring recommendation based on all interview evaluations.\n\n"
            f"## ROUND 1 — SCREENING VERDICT\n{round1_verdict}\n\n"
            f"## ROUND 2 — TECHNICAL VERDICT\n{round2_verdict}\n\n"
            f"## ROUND 3 — BEHAVIORAL VERDICT\n{round3_verdict}\n\n"
            f"## YOUR TASK\n"
            f"1. Synthesize all three round evaluations into a comprehensive recommendation.\n"
            f"2. Identify key hiring risks.\n"
            f"3. List the strongest positives supporting a hire.\n"
            f"4. Suggest the appropriate role/level for this candidate.\n"
            f"5. Identify growth areas for the candidate.\n"
            f"6. Make a recommendation: HIRE, HOLD, or REJECT.\n"
            f"7. Assign an overall score from 0 to 10.\n"
            f"8. Rate your confidence from 0 to 1.\n\n"
            f"## CRITICAL: OUTPUT FORMAT\n"
            f"You MUST return ONLY valid JSON matching this exact schema. No markdown, no explanation outside the JSON.\n\n"
            f"```json\n{RECOMMENDATION_SCHEMA}\n```\n\n"
            f"Return ONLY the JSON object, nothing else."
        ),
        expected_output=(
            "A single valid JSON object matching the hiring recommendation schema with "
            "decision, score, detailed_recommendation, risks, positives, suggested_role, "
            "growth_areas, and confidence."
        ),
        agent=agent,
    )


# ── Final: Committee Evaluator ──────────────────────────────────────


def create_committee_decision_task(
    agent: Agent,
    round1_verdict: str,
    round2_verdict: str,
    round3_verdict: str,
    recommendation: str,
) -> Task:
    """
    Committee Evaluator — makes final decision based ONLY on agent outputs.
    Does NOT receive the resume, candidate profile, or raw answers.
    This isolation prevents resume-based bias in the final decision.
    """
    return Task(
        description=(
            f"You are the hiring committee chair making the final hiring decision.\n\n"
            f"## CRITICAL CONSTRAINT\n"
            f"You must base your decision ONLY on the evaluation outputs below. "
            f"You do NOT have access to the candidate's resume, personal details, "
            f"or raw interview answers. This is by design to prevent bias.\n\n"
            f"## ROUND 1 — SCREENING EVALUATION\n{round1_verdict}\n\n"
            f"## ROUND 2 — TECHNICAL EVALUATION\n{round2_verdict}\n\n"
            f"## ROUND 3 — BEHAVIORAL EVALUATION\n{round3_verdict}\n\n"
            f"## HIRING RECOMMENDATION\n{recommendation}\n\n"
            f"## YOUR TASK\n"
            f"1. Write a brief executive summary of the candidate evaluation.\n"
            f"2. Summarize each round's key finding.\n"
            f"3. Identify patterns across all evaluations.\n"
            f"4. List top strengths and weaknesses.\n"
            f"5. Identify key hiring risks.\n"
            f"6. Make a final decision: HIRE, HOLD, or REJECT.\n"
            f"7. Provide your overall assessment and recommendation.\n"
            f"8. Rate your confidence from 0 to 1.\n\n"
            f"## CRITICAL: OUTPUT FORMAT\n"
            f"You MUST return ONLY valid JSON matching this exact schema. No markdown, no explanation outside the JSON.\n\n"
            f"```json\n{COMMITTEE_SCHEMA}\n```\n\n"
            f"Return ONLY the JSON object, nothing else."
        ),
        expected_output=(
            "A single valid JSON object matching the committee decision schema with "
            "decision, confidence, executive_summary, round_summaries, overall_assessment, "
            "recommendation, hiring_risks, strengths_summary, and weaknesses_summary."
        ),
        agent=agent,
    )
