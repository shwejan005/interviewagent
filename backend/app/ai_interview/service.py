"""Application-linked screening and interview orchestration services."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.ai_interview import llm, repository as interview_db
from app.ai_interview.dto import ApplicationScreeningAssessment, AnswerAssessment, InterviewQuestion, InterviewQuestionPlan
from app.config import database as db
from app.evaluation.runner import AgentOutputError, run_structured_agent_task
from app.hiring.repository import ApplicationStage

logger = logging.getLogger(__name__)


def _db(func, *args, **kwargs):
    return asyncio.to_thread(func, *args, **kwargs)


def _normalize(text: str) -> str:
    return " ".join((text or "").casefold().split())


def screening_constraints(
    policy: dict,
    profile: dict,
    assessment: ApplicationScreeningAssessment,
    resume_text: str,
    application_answers: list[dict],
) -> list[str]:
    """Validate screening citations and job constraints; uncertainty is review, not rejection."""
    evidence_by_key = {item.criterion_key: item for item in assessment.evidence}
    sources = _screening_source_texts(profile, resume_text, application_answers)
    issues = _screening_citation_gaps(assessment, sources)
    issues.extend(_experience_constraint_gaps(policy, profile, evidence_by_key))
    issues.extend(_required_skill_gaps(policy, evidence_by_key, sources))
    return issues


def _screening_source_texts(profile: dict, resume_text: str, application_answers: list[dict]) -> dict[str, str]:
    answers_text = "\n".join(
        f"{answer.get('question_key', '')}: {answer.get('answer_text', '')}"
        for answer in application_answers
        if isinstance(answer, dict)
    )
    return {
        "RESUME": resume_text,
        "PROFILE": json.dumps(profile, ensure_ascii=False, sort_keys=True),
        "APPLICATION_ANSWER": answers_text,
    }


def _candidate_profile_claims(profile: dict) -> list[dict[str, Any]]:
    claims = []
    seen: set[str] = set()
    for item in profile.get("skills", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("skill", "")).strip()
        normalized = _normalize(label)
        if not label or normalized in seen:
            continue
        claims.append({"claim": label, "years": item.get("years"), "source": "PROFILE"})
        seen.add(normalized)
    years = profile.get("years_experience")
    if years is not None:
        claims.append({"claim": "Years of experience", "years": years, "source": "PROFILE"})
    return claims


def _minimum_experience_check(policy: dict, profile: dict) -> list[dict[str, Any]]:
    minimum = policy.get("minimum_experience")
    years = profile.get("years_experience")
    if minimum is None:
        return []
    if years is None:
        state = "UNCLEAR"
        reason = "Years of experience are not available in the structured profile."
    elif float(years) < float(minimum):
        state = "BELOW_MINIMUM"
        reason = f"The profile lists {years} years; the posting requires at least {minimum}."
    else:
        state = "MET"
        reason = f"The profile lists {years} years; the posting requires at least {minimum}."
    return [{"criterion_key": "minimum_experience", "state": state, "expected": minimum, "observed": years, "reason": reason}]


def _required_skill_checks(policy: dict, profile: dict, resume_text: str) -> list[dict[str, Any]]:
    skills = policy.get("required_skills") or []
    profile_skills = {
        _normalize(str(skill.get("skill", "")))
        for skill in profile.get("skills", [])
        if isinstance(skill, dict) and skill.get("skill")
    }
    normalized_resume = _normalize(resume_text)
    checks = []
    for index, skill in enumerate(skills, start=1):
        normalized_skill = _normalize(str(skill))
        in_profile = normalized_skill in profile_skills
        in_resume = bool(normalized_skill and normalized_skill in normalized_resume)
        state = "MET" if in_profile or in_resume else "UNCLEAR"
        checks.append({
            "criterion_key": f"required_skill_{index}",
            "requirement": str(skill),
            "state": state,
            "reason": "Found in submitted profile or resume." if state == "MET" else "Not found in structured skills or resume; evidence review is required.",
        })
    return checks


def _minimum_gate_status(checks: list[dict]) -> str:
    states = {check.get("state") for check in checks}
    if "BELOW_MINIMUM" in states:
        return "BELOW_MINIMUM"
    if "UNCLEAR" in states:
        return "NEEDS_EVIDENCE"
    return "MEETS_MINIMUM"


def deterministic_minimum_criteria_gate(policy: dict, profile: dict, resume_text: str) -> dict:
    """Check only explicit recruiter-set facts; uncertainty never becomes a fail."""
    checks = _minimum_experience_check(policy, profile)
    checks.extend(_required_skill_checks(policy, profile, resume_text))
    return {
        "status": _minimum_gate_status(checks),
        "checks": checks,
        "decision_owner": "HUMAN",
    }


def _resolve_minimum_criteria_gate(
    gate: dict,
    assessment: ApplicationScreeningAssessment,
    profile: dict,
    resume_text: str,
    application_answers: list[dict],
) -> dict:
    """Resolve profile-only unknowns only when the LLM supplies a grounded exact quote."""
    resolved = {**gate, "checks": [dict(check) for check in gate.get("checks", [])]}
    sources = _screening_source_texts(profile, resume_text, application_answers)
    evidence_by_key = {item.criterion_key: item for item in assessment.evidence}
    for check in resolved["checks"]:
        if check["state"] != "UNCLEAR":
            continue
        evidence_key = "experience_years" if check["criterion_key"] == "minimum_experience" else check["criterion_key"]
        evidence = evidence_by_key.get(evidence_key)
        if (
            evidence is not None
            and evidence.status == "MET"
            and evidence.quote
            and evidence.quote in sources.get(evidence.source or "", "")
        ):
            check.update({
                "state": "MET",
                "source": evidence.source,
                "quote": evidence.quote,
                "observed": evidence.value if evidence.value is not None else check.get("observed"),
            })
    resolved["status"] = _minimum_gate_status(resolved["checks"])
    return resolved


def _screening_citation_gaps(assessment: ApplicationScreeningAssessment, sources: dict[str, str]) -> list[str]:
    return [
        f"Evidence for {item.criterion_key} was not found in its cited source."
        for item in assessment.evidence
        if item.status == "MET" and item.quote not in sources.get(item.source or "", "")
    ]


def _experience_constraint_gaps(policy: dict, profile: dict, evidence_by_key: dict) -> list[str]:
    issues: list[str] = []
    minimum = policy.get("minimum_experience")
    experience = profile.get("years_experience")
    maximum = policy.get("maximum_experience")
    if minimum is not None or maximum is not None:
        experience_evidence = evidence_by_key.get("experience_years")
        observed = experience
        if observed is None and experience_evidence and experience_evidence.status == "MET":
            observed = experience_evidence.value
        if observed is None:
            issues.append("Required years of experience could not be verified from the submitted profile or cited application evidence.")
        elif minimum is not None and float(observed) < float(minimum):
            issues.append(f"Experience evidence ({observed} years) is below the posting's stated minimum ({minimum} years).")
        elif maximum is not None and float(observed) > float(maximum):
            issues.append(f"Experience evidence ({observed} years) is above the posting's configured maximum ({maximum} years); human review is required.")
    return issues


def _required_skill_gaps(policy: dict, evidence_by_key: dict, sources: dict[str, str]) -> list[str]:
    issues: list[str] = []
    required_skills = policy.get("required_skills") or []
    for index, skill in enumerate(required_skills, start=1):
        item = evidence_by_key.get(f"required_skill_{index}")
        if item is None or item.status != "MET" or not item.quote or item.quote not in sources.get(item.source or "", ""):
            issues.append(f"Required skill evidence is missing or unclear for: {skill}.")
    return issues


def build_question_plan(policy: dict, role: str) -> dict:
    """Build the same core questions for every application on one policy revision.

    Adaptive behavior is confined to bounded follow-ups/difficulty adjustments
    after answers; baseline questions remain deterministic and comparable.
    """
    settings = policy.get("interview_settings") or {}
    technical_competencies = [
        item for item in policy.get("competencies", [])
        if isinstance(item, dict) and item.get("category") == "TECHNICAL"
    ]
    behavioral_competencies = [
        item for item in policy.get("competencies", [])
        if isinstance(item, dict) and item.get("category") == "BEHAVIORAL"
    ]
    if not technical_competencies or not behavioral_competencies:
        raise AgentOutputError("The pinned interview rubric must include technical and behavioral competencies.", "")

    level = settings.get("role_level", "MID")
    difficulty = {"ENTRY": 1, "MID": 2, "SENIOR": 3}.get(level, 2)
    technical_templates = (
        "For the {role} role, explain how you would apply {competency} to solve a realistic problem. Walk through your approach and assumptions.",
        "Describe a difficult trade-off involving {competency}. How would you diagnose the problem and decide what to do?",
        "How would you test and validate a solution involving {competency}? Which failure modes would you check?",
        "How would you scale and maintain a system that relies on {competency} as usage grows?",
        "What alternative would you consider to {competency}, and how would you compare the options?",
    )
    behavioral_templates = (
        "Describe a specific work situation where you demonstrated {competency}. What was the situation, your responsibility, your actions, and the result?",
        "Tell me about a time you handled a disagreement related to {competency}. What did you do, and what changed afterward?",
        "Describe a project where {competency} became challenging as scope grew. How did you align the team and measure the outcome?",
        "What feedback have you received about {competency}, and what concrete change did you make afterward?",
    )
    technical_count = int(settings.get("technical_question_count", 2))
    behavioral_count = int(settings.get("behavioral_question_count", 2))
    custom_questions = [str(question).strip() for question in policy.get("custom_questions", []) if str(question).strip()]

    technical = []
    for index in range(technical_count):
        competency = technical_competencies[index % len(technical_competencies)]
        if index < len(custom_questions):
            question = custom_questions[index]
        else:
            question = technical_templates[index % len(technical_templates)].format(
                role=role,
                competency=competency.get("label", competency["key"]),
            )
        technical.append(InterviewQuestion(
            competency_key=competency["key"],
            question=question,
            difficulty=difficulty,
        ))

    behavioral = []
    for index in range(behavioral_count):
        competency = behavioral_competencies[index % len(behavioral_competencies)]
        question = behavioral_templates[index % len(behavioral_templates)].format(
            competency=competency.get("label", competency["key"]),
        )
        behavioral.append(InterviewQuestion(
            competency_key=competency["key"],
            question=question,
            difficulty=difficulty,
        ))

    plan = InterviewQuestionPlan(technical_questions=technical, behavioral_questions=behavioral)
    return validate_question_plan(plan, policy)


def validate_question_plan(plan: InterviewQuestionPlan, policy: dict) -> dict:
    settings = policy.get("interview_settings") or {}
    competencies = {
        item.get("key"): item
        for item in policy.get("competencies", [])
        if isinstance(item, dict) and item.get("key")
    }
    technical_count = int(settings.get("technical_question_count", 2))
    behavioral_count = int(settings.get("behavioral_question_count", 2))
    if len(plan.technical_questions) != technical_count:
        raise AgentOutputError(
            f"Question planner returned {len(plan.technical_questions)} technical questions; expected {technical_count}.",
            plan.model_dump_json(),
        )
    if len(plan.behavioral_questions) != behavioral_count:
        raise AgentOutputError(
            f"Question planner returned {len(plan.behavioral_questions)} behavioral questions; expected {behavioral_count}.",
            plan.model_dump_json(),
        )
    _validate_question_phase(plan, "TECHNICAL", plan.technical_questions, competencies)
    _validate_question_phase(plan, "BEHAVIORAL", plan.behavioral_questions, competencies)
    return plan.model_dump(mode="json")


def _validate_question_phase(
    plan: InterviewQuestionPlan,
    phase: str,
    questions: list[InterviewQuestion],
    competencies: dict,
) -> None:
    seen: set[str] = set()
    for question in questions:
        competency = competencies.get(question.competency_key)
        if competency is None:
            raise AgentOutputError(
                f"Question planner referenced unknown competency {question.competency_key!r}.",
                plan.model_dump_json(),
            )
        if competency.get("category") != phase:
            raise AgentOutputError(
                f"{phase.title()} question mapped to non-{phase.lower()} competency {question.competency_key!r}.",
                plan.model_dump_json(),
            )
        folded = _normalize(question.question)
        if folded in seen:
            raise AgentOutputError("Question planner returned duplicate questions.", plan.model_dump_json())
        seen.add(folded)


def _quote_is_grounded(assessment: AnswerAssessment, answer: str) -> bool:
    quote = assessment.evidence_quote.strip()
    return bool(quote) and quote in answer


async def run_application_screening(interview_id: int) -> None:
    run = await _db(interview_db.get_internal_by_id, interview_id)
    if _screening_already_resolved(run):
        return
    claim = await _db(interview_db.begin_screening, interview_id)
    if not claim or not claim.get("claimed"):
        return

    evaluation_id = await _db(interview_db.ensure_evaluation, interview_id)
    policy = run["policy_snapshot"]
    screening_input = run["screening_input"]
    profile = screening_input.get("profile_snapshot") or {}
    resume_text = screening_input.get("resume_text") or ""
    gate = deterministic_minimum_criteria_gate(policy, profile, resume_text)
    if gate["status"] == "BELOW_MINIMUM":
        reasons = [check["reason"] for check in gate["checks"] if check["state"] == "BELOW_MINIMUM"]
        summary = {
            "decision": "REVIEW_REQUIRED",
            "summary": "A recruiter-defined minimum criterion needs human review.",
            "constraint_gaps": reasons,
            "minimum_criteria": gate,
            "candidate_claims": _candidate_profile_claims(profile),
        }
        await _db(
            interview_db.mark_review_required,
            interview_id,
            "MINIMUM_CRITERIA_REVIEW",
            " ".join(reasons),
            summary,
        )
        return

    verdict, raw_output = await _assess_application_evidence(interview_id, run, policy, screening_input, profile)
    gate = _resolve_minimum_criteria_gate(
        gate,
        verdict,
        profile,
        resume_text,
        screening_input.get("application_answers") or [],
    )
    screening_summary, verdict, decision, raw_output = await _persist_screening_verdict(
        evaluation_id, run, verdict, raw_output, policy, profile, screening_input
    )
    screening_summary["minimum_criteria"] = gate
    screening_summary["candidate_claims"] = _candidate_profile_claims(profile)
    issues = screening_summary.get("constraint_gaps", [])
    threshold = float(policy.get("pass_threshold", 6.0))
    if _screening_needs_review(decision, verdict.score, threshold, issues) or gate["status"] != "MEETS_MINIMUM":
        issues = list(issues)
        if gate["status"] != "MEETS_MINIMUM":
            issues.extend(check["reason"] for check in gate["checks"] if check["state"] == "UNCLEAR")
        reasons = issues or [f"Screening outcome requires review ({decision}, score {verdict.score:g})."]
        await _db(
            interview_db.mark_review_required,
            interview_id,
            "SCREENING_REVIEW_REQUIRED",
            " ".join(reasons),
            {**screening_summary, "raw_summary": raw_output[:4000]},
        )
        return

    try:
        safe_plan = build_question_plan(policy, run["role"])
    except AgentOutputError as exc:
        await _db(interview_db.mark_review_required, interview_id, "QUESTION_PLAN_INVALID", str(exc), screening_summary)
        raise
    await _db(interview_db.save_screening_pass, interview_id, screening_summary, raw_output, safe_plan)


def _screening_already_resolved(run: Optional[dict]) -> bool:
    if run is None or run.get("withdrawn_at"):
        return True
    return run["status"] in {
        "INTERVIEW_READY", "INTERVIEW_IN_PROGRESS", "ANSWER_PROCESSING",
        "REPORT_PENDING", "REPORT_READY", "COMPLETED", "CANCELLED",
        "REVIEW_REQUIRED", "EXPIRED",
    }


async def _assess_application_evidence(interview_id: int, run: dict, policy: dict, screening_input: dict, profile: dict):
    try:
        return await llm.screen_application(
            role=run["role"],
            posting_description=run["posting_description"],
            policy=policy,
            profile=profile,
            application_answers=screening_input.get("application_answers") or [],
            resume_text=screening_input.get("resume_text") or "",
        )
    except AgentOutputError as exc:
        await _db(interview_db.mark_review_required, interview_id, "SCREENING_INVALID_OUTPUT", str(exc))
        raise


async def _persist_screening_verdict(
    evaluation_id: int,
    run: dict,
    verdict: ApplicationScreeningAssessment,
    raw_output: str,
    policy: dict,
    profile: dict,
    screening_input: dict,
) -> tuple[dict, ApplicationScreeningAssessment, str, str]:
    screening_summary = verdict.model_dump(mode="json")
    issues = screening_constraints(
        policy,
        profile,
        verdict,
        screening_input.get("resume_text") or "",
        screening_input.get("application_answers") or [],
    )
    threshold = float(policy.get("pass_threshold", 6.0))
    decision = verdict.decision
    screening_summary["configured_pass_threshold"] = threshold
    screening_summary["constraint_gaps"] = issues
    try:
        await _db(
            db.save_verdict,
            evaluation_id=evaluation_id,
            agent_type="application_screening",
            round_number=1,
            verdict_json=screening_summary,
            verdict_text=raw_output,
            score=verdict.score,
            decision=decision,
            confidence=None,
            rubric_version=run["rubric_version"],
            prompt_version="application-screening-v1",
        )
    except db.DuplicateVerdictError:
        existing = await _db(db.get_verdict_by_round, evaluation_id, 1)
        if existing is None:
            raise
        screening_summary = existing.get("verdict_json") or screening_summary
        issues = screening_summary.get("constraint_gaps", issues)
        decision = str(existing.get("decision") or decision)
        raw_output = existing.get("verdict_text") or raw_output
        verdict = ApplicationScreeningAssessment.model_validate({
            key: value for key, value in screening_summary.items()
            if key in ApplicationScreeningAssessment.model_fields
        })
    return screening_summary, verdict, decision, raw_output


def _screening_needs_review(decision: str, score: float, threshold: float, issues: list[str]) -> bool:
    return decision != "PASS" or score < threshold or bool(issues)


async def assess_application_answer(interview_id: int, turn_id: int) -> None:
    context = await _db(interview_db.get_answer_context, interview_id, turn_id)
    if context is None:
        raise interview_db.InterviewNotFoundError("Interview turn not found")
    if context.get("state") == "ASSESSED":
        return
    if context.get("state") != "ANSWER_QUEUED" or not context.get("answer_text"):
        raise interview_db.InterviewConflictError("Interview answer is not queued")
    if context.get("withdrawn_at") or context.get("interview_status") == "CANCELLED":
        return

    policy = context["policy_snapshot"]
    competency = next(
        (item for item in policy.get("competencies", []) if item.get("key") == context["competency_key"]),
        {"key": context["competency_key"], "label": context["competency_key"], "description": ""},
    )
    max_followups = int((policy.get("interview_settings") or {}).get("max_followups_per_question", 1))
    followups_remaining = max(0, max_followups - int(context.get("follow_ups_for_question") or 0))
    try:
        assessment, raw = await llm.assess_answer(
            role=context["role"],
            policy=policy,
            phase=context["phase"],
            competency=competency,
            difficulty=int(context["difficulty"]),
            question=context["question_text"],
            answer=context["answer_text"],
            prior_turns=context["prior_turns"],
            followups_remaining=followups_remaining,
        )
    except AgentOutputError as exc:
        await _db(interview_db.mark_job_failure, interview_id, "ANSWER_INVALID_OUTPUT", str(exc))
        raise

    if not _quote_is_grounded(assessment, context["answer_text"]):
        error = AgentOutputError(
            "Interview assessor did not provide an exact evidence quote from the submitted answer.",
            raw,
        )
        await _db(interview_db.mark_job_failure, interview_id, "ANSWER_EVIDENCE_UNGROUNDED", str(error))
        raise error

    await _db(
        interview_db.apply_answer_assessment,
        interview_id,
        turn_id,
        assessment.model_dump(mode="json"),
    )


def _build_competency_scores(policy: dict, turns: list[dict]) -> list[dict]:
    rows = []
    for competency in policy.get("competencies", []):
        key = competency.get("key", "")
        evidence_turns = [
            turn for turn in turns
            if turn.get("competency_key") == key
            and turn.get("state") == "ASSESSED"
            and turn.get("assessment", {}).get("evidence_quote")
        ]
        scores = [float(turn["assessment"]["score"]) for turn in evidence_turns]
        evidence = "\n".join(
            f"[{turn['phase'].title()} · level {turn['difficulty']}] “{turn['assessment']['evidence_quote']}” — "
            f"{turn['assessment']['summary']}"
            for turn in evidence_turns
        )
        rows.append({
            "key": key,
            "label": competency.get("label", key),
            "weight": float(competency.get("weight", 0)),
            "score": round(sum(scores) / len(scores), 2) if scores else None,
            "evidence": evidence or "Insufficient grounded interview evidence for this competency.",
        })
    return rows


def _weighted_interview_score(policy: dict, competency_rows: list[dict]) -> tuple[float | None, float, list[dict]]:
    assessed_rows = [row for row in competency_rows if row["score"] is not None]
    scored_weight = sum(row["weight"] for row in assessed_rows)
    total_weight = sum(float(item.get("weight", 0)) for item in policy.get("competencies", []))
    overall = round(sum(row["score"] * row["weight"] for row in assessed_rows) / scored_weight, 2) if scored_weight else None
    coverage = round((scored_weight / total_weight) * 100, 1) if total_weight else 0.0
    return overall, coverage, assessed_rows


def _coverage_status(score: float | None, threshold: float) -> str:
    if score is None:
        return "NOT_ASSESSED"
    if score < threshold - 1:
        return "GAP"
    if score >= threshold + 1:
        return "DEMONSTRATED"
    return "PARTIAL"


def _matching_competency_key(skill: str, competencies: dict) -> str | None:
    normalized_skill = _normalize(skill)
    for key, competency in competencies.items():
        label = _normalize(str(competency.get("label", "")))
        if normalized_skill in label or normalized_skill == _normalize(str(key)):
            return key
    return None


def _screening_evidence_index(screening: dict) -> dict:
    return {
        item.get("criterion_key"): item
        for item in screening.get("evidence", [])
        if isinstance(item, dict)
    }


def _skill_coverage_row(
    skill: str,
    competency_by_key: dict,
    score_by_key: dict,
    threshold: float,
    source: str,
    resume_evidence: str,
    evidence_status: str,
) -> tuple[dict, dict, str]:
    matching_key = _matching_competency_key(skill, competency_by_key)
    score_row = score_by_key.get(matching_key) if matching_key else None
    if score_row is None or score_row["score"] is None:
        claim_status = "NOT_PROBED"
        coverage_status = "CLAIMED_ONLY" if evidence_status == "MET" else "NOT_ASSESSED"
    elif score_row["score"] >= threshold:
        claim_status, coverage_status = "CONFIRMED_IN_INTERVIEW", "DEMONSTRATED"
    else:
        claim_status, coverage_status = "WORTH_FOLLOW_UP", "GAP"
    interview_evidence = score_row["evidence"] if score_row else "Not assessed in the interview."
    resume_text = resume_evidence or f"Candidate profile lists: {skill}."
    claim = {
        "claim": skill,
        "status": claim_status,
        "source": source,
        "resume_evidence": resume_text,
        "interview_evidence": interview_evidence,
    }
    row = {
        "key": "claim_" + re.sub(r"[^a-z0-9]+", "_", _normalize(skill)).strip("_"),
        "label": skill,
        "kind": "RESUME_CLAIM",
        "status": coverage_status,
        "score": score_row["score"] if score_row else None,
        "weight": score_row["weight"] if score_row else 0,
        "evidence": interview_evidence,
        "resume_evidence": resume_text,
    }
    return row, claim, coverage_status


def _required_skill_coverage(
    policy: dict,
    evidence_by_key: dict,
    competency_by_key: dict,
    score_by_key: dict,
    threshold: float,
) -> tuple[list[dict], list[dict], list[str], set[str]]:
    rows, claims, statuses, seen = [], [], [], set()
    for index, skill in enumerate(policy.get("required_skills") or [], start=1):
        item = evidence_by_key.get(f"required_skill_{index}", {})
        row, claim, status = _skill_coverage_row(
            str(skill), competency_by_key, score_by_key, threshold,
            str(item.get("source") or "RESUME"), item.get("quote", ""), item.get("status", "UNCLEAR"),
        )
        row.update({"key": f"required_skill_{index}", "kind": "MUST_HAVE"})
        rows.append(row)
        claims.append(claim)
        statuses.append(status)
        seen.add(_normalize(str(skill)))
    return rows, claims, statuses, seen


def _profile_claim_coverage(
    screening: dict,
    competency_by_key: dict,
    score_by_key: dict,
    threshold: float,
    seen_claims: set[str],
) -> tuple[list[dict], list[dict]]:
    rows, claims = [], []
    for candidate_claim in screening.get("candidate_claims", []):
        if not isinstance(candidate_claim, dict):
            continue
        claim = str(candidate_claim.get("claim", "")).strip()
        normalized = _normalize(claim)
        if not claim or normalized in seen_claims:
            continue
        source = str(candidate_claim.get("source") or "PROFILE")
        years = candidate_claim.get("years")
        evidence = f"Candidate profile lists {years} years of experience." if claim == "Years of experience" else ""
        row, claim_row, _status = _skill_coverage_row(
            claim, competency_by_key, score_by_key, threshold, source, evidence, "MET",
        )
        rows.append(row)
        claims.append(claim_row)
        seen_claims.add(normalized)
    return rows, claims


def _build_requirements_coverage(
    policy: dict,
    screening: dict,
    competency_rows: list[dict],
    threshold: float,
) -> tuple[list[dict], list[dict], list[str]]:
    coverage = [{
        "key": row["key"],
        "label": row["label"],
        "kind": "COMPETENCY",
        "status": _coverage_status(row["score"], threshold),
        "score": row["score"],
        "weight": row["weight"],
        "evidence": row["evidence"],
    } for row in competency_rows]
    screening_by_key = _screening_evidence_index(screening)
    competency_by_key = {item.get("key"): item for item in policy.get("competencies", [])}
    score_by_key = {row["key"]: row for row in competency_rows}
    required_rows, claims, must_have_statuses, seen_claims = _required_skill_coverage(
        policy, screening_by_key, competency_by_key, score_by_key, threshold,
    )
    profile_rows, profile_claims = _profile_claim_coverage(
        screening, competency_by_key, score_by_key, threshold, seen_claims,
    )
    coverage.extend(required_rows)
    coverage.extend(profile_rows)
    claims.extend(profile_claims)
    return coverage, claims, must_have_statuses


def _assessment_highlights(turns: list[dict]) -> tuple[list[dict], list[dict]]:
    highlights: dict[str, list[dict]] = {"strengths": [], "concerns": []}
    seen: dict[str, set[str]] = {"strengths": set(), "concerns": set()}
    for turn in turns:
        if turn.get("state") != "ASSESSED":
            continue
        assessment = turn.get("assessment", {})
        quote = assessment.get("evidence_quote", "")
        for target, field in (("strengths", "strengths"), ("concerns", "gaps")):
            for text in assessment.get(field, []):
                key = _normalize(str(text))
                if key and key not in seen[target]:
                    highlights[target].append({"text": text, "turn_sequence": turn["sequence_no"], "evidence_quote": quote})
                    seen[target].add(key)
    return highlights["strengths"], highlights["concerns"]


def _build_fit_nudge(
    overall: float | None,
    score_coverage: float,
    threshold: float,
    competency_rows: list[dict],
    must_have_statuses: list[str],
) -> dict:
    if overall is None or score_coverage < 50:
        band = "INSUFFICIENT_EVIDENCE"
    elif overall < threshold - 1:
        band = "UNLIKELY_FIT"
    elif overall < threshold:
        band = "MIXED"
    elif overall >= threshold + 1 and all(status == "DEMONSTRATED" for status in must_have_statuses):
        band = "STRONG_FIT"
    elif overall >= threshold and not any(status == "GAP" for status in must_have_statuses):
        band = "LIKELY_FIT"
    else:
        band = "MIXED"
    return {
        "band": band,
        "suggested_action": "PROMOTE" if band in {"STRONG_FIT", "LIKELY_FIT"} else "HOLD",
        "score_threshold": threshold,
        "evidence_coverage_percent": score_coverage,
        "summary": (
            f"The available job-related evidence leans toward {band.replace('_', ' ').lower()} "
            f"({sum(row['score'] is not None for row in competency_rows)} of {len(competency_rows)} competencies assessed). "
            "Review the cited examples and gaps; this is an advisory, not a hiring decision."
        ),
        "calibration": "UNVALIDATED_ADVISORY",
    }


def _report_turns(turns: list[dict]) -> list[dict]:
    return [{
        "sequence_no": turn["sequence_no"],
        "phase": turn["phase"],
        "question_type": turn["question_type"],
        "competency_key": turn["competency_key"],
        "difficulty": turn["difficulty"],
        "question": turn["question_text"],
        "answer": turn.get("answer_text"),
        "answer_source": turn.get("answer_source", "TEXT"),
        "assessment": turn.get("assessment", {}),
    } for turn in turns]


def _build_report_details(
    run: dict,
    turns: list[dict],
    screening: dict,
    policy: dict,
    requirements_coverage: list[dict],
    resume_claims: list[dict],
    strengths: list[dict],
    concerns: list[dict],
    score_coverage: float,
    fit_nudge: dict,
) -> dict:
    next_round_focus = [
        {"requirement": item["label"], "status": item["status"]}
        for item in requirements_coverage
        if item["status"] in {"PARTIAL", "CLAIMED_ONLY", "NOT_ASSESSED", "GAP"}
    ]
    return {
        "source": "application_ai_interview_v2",
        "posting_description": policy.get("posting_description", ""),
        "requirements_coverage": requirements_coverage,
        "resume_claims": resume_claims,
        "strengths": strengths,
        "concerns": concerns,
        "next_round_focus": next_round_focus,
        "fit_nudge": fit_nudge,
        "screening": {
            "decision": screening.get("decision", "PASS"),
            "score": screening.get("score"),
            "policy_version": run["rubric_version"],
            "constraint_gaps": screening.get("constraint_gaps", []),
            "minimum_criteria": screening.get("minimum_criteria", {}),
            "evidence": screening.get("evidence", []),
        },
        "interview": {
            "status": run["status"],
            "phase": run["phase"],
            "role_level": (policy.get("interview_settings") or {}).get("role_level", "MID"),
            "turn_count": len(turns),
            "weighted_score_status": "ADVISORY_UNCALIBRATED",
            "score_coverage_percent": score_coverage,
            "turns": _report_turns(turns),
            "model_recommendation": "HUMAN_REVIEW_REQUIRED",
            "human_decision_required": True,
        },
    }


async def generate_application_report(interview_id: int) -> None:
    run = await _db(interview_db.get_internal_by_id, interview_id)
    if run is None:
        raise interview_db.InterviewNotFoundError("AI interview not found")
    if run["status"] == "REPORT_READY":
        return
    if run["status"] != "REPORT_PENDING":
        raise interview_db.InterviewConflictError(f"Report cannot be generated from {run['status']}")

    policy = run["policy_snapshot"]
    turns = await _db(interview_db.list_turns_internal, interview_id)
    screening = run.get("screening_result") or {}
    competency_rows = _build_competency_scores(policy, turns)
    overall, score_coverage, _assessed_rows = _weighted_interview_score(policy, competency_rows)
    threshold = float(policy.get("pass_threshold", 6.0))
    requirements_coverage, resume_claims, must_have_statuses = _build_requirements_coverage(
        policy, screening, competency_rows, threshold
    )
    strengths, concerns = _assessment_highlights(turns)
    fit_nudge = _build_fit_nudge(overall, score_coverage, threshold, competency_rows, must_have_statuses)
    details = _build_report_details(
        run, turns, screening, policy, requirements_coverage, resume_claims,
        strengths, concerns, score_coverage, fit_nudge,
    )
    if run.get("evaluation_id") is None:
        await _db(interview_db.ensure_evaluation, interview_id)

    persisted = await _db(
        interview_db.persist_application_report,
        interview_id,
        competency_scores=competency_rows,
        overall_weighted_score=overall,
        recommendation="HUMAN_REVIEW_REQUIRED",
        interview_details=details,
    )
    if not persisted:
        logger.info("AI interview %s was cancelled before its report could be published", interview_id)
