"""Seed a realistic local Evalia workspace for development.

This command is intentionally SQLite-only and idempotent. It creates demo
accounts, a recruiter organization, candidate profiles, published jobs,
applications, and representative evaluation records without touching rows
that are not part of the demo dataset.

Run from the repository root with:

    python backend/seed_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import candidate_db as candidates  # noqa: E402
import database as db  # noqa: E402
import hiring_db as hiring  # noqa: E402
from security import hash_password  # noqa: E402


DEMO_LOGIN = "Evalia" + "Demo2026!"
DEMO_ORG_SLUG = "evalia-demo"
PLATFORM_ROLE = "Senior Platform Engineer"
DATA_ROLE = "Senior Data Engineer"
FRONTEND_ROLE = "Frontend Product Engineer"
ML_ROLE = "ML Platform Engineer"
AUSTIN_LOCATION = "Austin, TX"
NEW_YORK_LOCATION = "New York, NY"
SEATTLE_LOCATION = "Seattle, WA"


def _find_id(table: str, **filters: object) -> int | None:
    columns = list(filters)
    where = " AND ".join(f"{column} = ?" for column in columns)
    with db._get_conn() as (_, cur):
        cur.execute(
            f"SELECT id FROM {table} WHERE {where} LIMIT 1",
            tuple(filters[column] for column in columns),
        )
        row = cur.fetchone()
    return row["id"] if row else None


def _ensure_user(email: str, full_name: str) -> int:
    user = db.get_user_by_email(email)
    if user:
        return user["id"]
    return db.create_user(email, hash_password(DEMO_LOGIN), full_name)


def _ensure_organization() -> int:
    existing = _find_id("organizations", slug=DEMO_ORG_SLUG)
    if existing:
        return existing
    return db.create_organization("Evalia Demo Labs", DEMO_ORG_SLUG, plan="growth")


def _ensure_membership(org_id: int, user_id: int, role: str) -> None:
    if db.get_membership(user_id, org_id) is None:
        db.create_membership(org_id, user_id, role)


def _seed_profile(
    user_id: int,
    *,
    headline: str,
    summary: str,
    location: str,
    years_experience: float,
    resume_text: str,
    experiences: list[dict],
    education: list[dict],
    skills: list[dict],
    desired_roles: list[str],
) -> int:
    profile = candidates.get_profile_by_user(user_id)
    if profile is None:
        profile_id = candidates.create_profile(
            user_id,
            headline=headline,
            summary=summary,
            location=location,
            work_authorization="Authorized to work in the United States",
            years_experience=years_experience,
            is_discoverable=True,
            resume_text=resume_text,
        )
    else:
        profile_id = profile["id"]

    if not candidates.list_experiences(profile_id):
        for experience in experiences:
            candidates.add_experience(profile_id, **experience)
    if not candidates.list_education(profile_id):
        for entry in education:
            candidates.add_education(profile_id, **entry)

    candidates.set_skills(profile_id, skills)
    candidates.set_preferences(
        profile_id,
        desired_roles=desired_roles,
        locations=[location, "Remote"],
        remote_preference="HYBRID",
        min_salary=130000,
        max_salary=190000,
        currency="USD",
        notice_period_days=30,
    )
    candidates.record_consent(profile_id, "demo-v1")
    candidates.upsert_vault_answer(
        profile_id,
        "work_style",
        "I prefer small, cross-functional teams with clear ownership and frequent written communication.",
        "What kind of team environment helps you do your best work?",
    )
    return profile_id


def _ensure_campaign(org_id: int, recruiter_id: int) -> int:
    existing = _find_id("campaigns", org_id=org_id, name="Engineering Hiring 2026")
    if existing:
        return existing
    return hiring.create_campaign(
        org_id,
        "Engineering Hiring 2026",
        "Demo hiring campaign for platform and data engineering roles.",
        recruiter_id,
    )


def _ensure_posting(org_id: int, campaign_id: int, recruiter_id: int, payload: dict) -> int:
    existing = _find_id("job_postings", org_id=org_id, title=payload["title"])
    if existing:
        if payload.get("status") == hiring.PostingStatus.PUBLISHED:
            posting = hiring.get_posting(existing, org_id)
            if posting and posting["status"] != hiring.PostingStatus.PUBLISHED:
                hiring.set_posting_status(existing, org_id, hiring.PostingStatus.PUBLISHED)
        return existing
    posting_id = hiring.create_posting(
        org_id,
        campaign_id,
        payload["title"],
        recruiter_id,
        **{key: value for key, value in payload.items() if key != "title"},
    )
    if payload.get("status") == hiring.PostingStatus.PUBLISHED:
        hiring.set_posting_status(posting_id, org_id, hiring.PostingStatus.PUBLISHED)
    return posting_id


def _ensure_application(
    org_id: int,
    posting_id: int,
    candidate_id: int,
    profile_id: int,
    answers: list[dict],
) -> int:
    existing = _find_id(
        "applications",
        posting_id=posting_id,
        candidate_user_id=candidate_id,
    )
    if existing:
        return existing
    return hiring.create_application(
        org_id,
        posting_id,
        candidate_id,
        profile_id,
        candidates.build_application_snapshot(candidate_id),
        answers=answers,
    )


def _advance_application(application_id: int, org_id: int, recruiter_id: int, stages: list[str]) -> None:
    application = hiring.get_application(application_id, org_id)
    if application is None:
        return
    for stage in stages:
        if application["current_stage"] == stage:
            continue
        if not hiring.can_transition(application["current_stage"], stage):
            break
        hiring.transition_application(
            application_id,
            org_id,
            stage,
            recruiter_id,
            note="Seeded demo pipeline history",
        )
        application["current_stage"] = stage


def _link_evaluation(application_id: int, evaluation_id: int) -> None:
    with db._get_conn() as (_, cur):
        cur.execute(
            "UPDATE applications SET evaluation_id = ? WHERE id = ?",
            (evaluation_id, application_id),
        )


def _ensure_evaluation(candidate_name: str, role: str, **fields: object) -> int:
    evaluation_id = _find_id("evaluations", candidate_name=candidate_name, role=role)
    if evaluation_id is None:
        evaluation_id = db.create_evaluation(
            fields.pop("resume_text", "Demo resume"),
            role,
            candidate_name,
            fields.pop("org_id", None),
            fields.pop("owner_user_id", None),
        )
    if fields:
        db.update_evaluation(evaluation_id, **fields)
    return evaluation_id


def _ensure_verdict(
    evaluation_id: int,
    agent_type: str,
    round_number: int,
    verdict: dict,
) -> None:
    if db.get_verdict_by_round(evaluation_id, round_number) is not None:
        return
    decision = verdict.get("decision")
    score = verdict.get("score")
    confidence = verdict.get("confidence")
    db.save_verdict(
        evaluation_id,
        agent_type,
        round_number,
        verdict,
        json.dumps(verdict),
        score=score,
        decision=decision,
        confidence=confidence,
    )


def _seed_complete_evaluation(org_id: int, owner_user_id: int) -> int:
    evaluation_id = _ensure_evaluation(
        "Leo Martins",
        DATA_ROLE,
        resume_text="Leo Martins is a senior data engineer with eight years of experience building reliable streaming and analytics platforms.",
        org_id=org_id,
        owner_user_id=owner_user_id,
        status="COMPLETE",
        current_round=5,
        overall_score=8.7,
        final_decision="HIRE",
    )
    verdicts = [
        (
            "screening",
            {"decision": "PASS", "score": 9.0, "strengths": ["Strong Python and SQL background", "Relevant streaming systems experience"], "weaknesses": ["Limited people-management experience"], "reasoning": "The resume maps closely to the senior data platform role.", "candidate_summary": "Senior data engineer with strong platform ownership experience.", "skills_extracted": ["Python", "SQL", "Kafka", "Spark", "AWS"], "experience_years": 8, "recommended_questions": ["How do you design an idempotent streaming pipeline?", "How do you manage schema evolution?"], "confidence": 0.94},
        ),
        (
            "technical",
            {"decision": "PASS", "score": 8.4, "question_evaluations": [{"question": "Design an idempotent streaming pipeline.", "correctness": 9, "depth": 8, "clarity": 8, "assessment": "Explained replay handling, keys, and checkpointing clearly."}], "strengths": ["Deep systems reasoning", "Practical trade-off awareness"], "weaknesses": ["Could quantify operational costs more precisely"], "reasoning": "The answer demonstrated production-level technical judgment.", "coding_quality": 8.0, "confidence": 0.89},
        ),
        (
            "behavioral",
            {"decision": "PASS", "score": 8.8, "star_evaluation": "Described a migration from batch to streaming with clear ownership and measurable impact.", "leadership": 8.0, "communication": 9.0, "teamwork": 9.0, "ownership": 9.0, "conflict_handling": 8.0, "culture_fit": 9.0, "strengths": ["Communicates trade-offs well", "Takes ownership during incidents"], "weaknesses": ["Could delegate earlier in high-pressure situations"], "reasoning": "The response was specific, reflective, and grounded in a real outcome.", "confidence": 0.91},
        ),
        (
            "hiring_recommendation",
            {"decision": "HIRE", "score": 8.7, "detailed_recommendation": f"Hire for {DATA_ROLE}. Leo brings strong platform fundamentals and credible production experience.", "risks": ["May need support ramping into formal mentorship"], "positives": ["Excellent streaming background", "Strong cross-functional communication"], "suggested_role": DATA_ROLE, "growth_areas": ["Technical mentorship", "Cost-aware architecture planning"], "confidence": 0.9},
        ),
        (
            "hiring_committee",
            {"decision": "HIRE", "confidence": 0.92, "executive_summary": "Consistent evidence across all rounds supports a senior-level hire.", "round_summaries": [{"round_name": "Screening", "decision": "PASS", "score": 9.0, "key_finding": "Strong role alignment"}, {"round_name": "Technical", "decision": "PASS", "score": 8.4, "key_finding": "Production-grade reasoning"}, {"round_name": "Behavioral", "decision": "PASS", "score": 8.8, "key_finding": "Clear ownership and communication"}], "overall_assessment": "High-confidence hire for the data platform team.", "recommendation": "Proceed with a Senior Data Engineer offer.", "hiring_risks": ["Mentorship expectations should be explicit"], "strengths_summary": ["Systems depth", "Ownership", "Communication"], "weaknesses_summary": ["Limited formal people management"],},
        ),
    ]
    for round_number, (agent_type, verdict) in enumerate(verdicts, start=1):
        _ensure_verdict(evaluation_id, agent_type, round_number, verdict)
    return evaluation_id


def _seed_in_progress_evaluation(org_id: int, owner_user_id: int) -> int:
    evaluation_id = _ensure_evaluation(
        "Maya Chen",
        PLATFORM_ROLE,
        resume_text="Maya Chen is a platform engineer with six years of experience in Kubernetes, Go, and cloud infrastructure.",
        org_id=org_id,
        owner_user_id=owner_user_id,
        status="IN_PROGRESS",
        current_round=2,
    )
    _ensure_verdict(
        evaluation_id,
        "screening",
        1,
        {"decision": "PASS", "score": 8.2, "strengths": ["Kubernetes operations", "Infrastructure automation"], "weaknesses": ["Limited public cloud cost ownership"], "reasoning": "Strong match for the platform engineering role.", "candidate_summary": "Platform engineer with a practical reliability focus.", "skills_extracted": ["Go", "Kubernetes", "Terraform", "AWS"], "experience_years": 6, "recommended_questions": ["How would you design multi-region failover?", "How do you control Kubernetes costs?"], "confidence": 0.86},
    )
    if db.get_questions(evaluation_id, 2) is None:
        db.save_questions(evaluation_id, 2, "1. How would you design multi-region failover?\n2. How do you control Kubernetes costs?")
    if db.get_answer(evaluation_id, 1) is None:
        db.save_answer(evaluation_id, 1, "I start with service-level objectives, define the failure domains, and test failover paths continuously.")
    return evaluation_id


def _seed_rejected_evaluation(org_id: int, owner_user_id: int) -> int:
    evaluation_id = _ensure_evaluation(
        "Jordan Patel",
        "Backend Developer",
        resume_text="Jordan Patel has two years of backend development experience and is growing into production systems work.",
        org_id=org_id,
        owner_user_id=owner_user_id,
        status="REJECTED",
        current_round=1,
        overall_score=4.8,
        final_decision="REJECT",
    )
    _ensure_verdict(
        evaluation_id,
        "screening",
        1,
        {"decision": "FAIL", "score": 4.8, "strengths": ["Solid application fundamentals"], "weaknesses": ["Role requires deeper distributed systems experience"], "reasoning": "The current experience level is below the senior backend requirement.", "candidate_summary": "Promising early-career backend developer.", "skills_extracted": ["Python", "FastAPI", "PostgreSQL"], "experience_years": 2, "recommended_questions": [], "confidence": 0.88},
    )
    return evaluation_id


def seed_demo() -> dict[str, object]:
    db.init_db()
    if db.USE_POSTGRES:
        raise RuntimeError("Demo seeding is restricted to local SQLite; DATABASE_URL is set.")

    recruiter_id = _ensure_user("recruiter.demo@evalia.local", "Avery Morgan")
    operations_recruiter_id = _ensure_user("recruiter.ops@evalia.local", "Priya Shah")
    maya_id = _ensure_user("maya.chen@evalia.local", "Maya Chen")
    leo_id = _ensure_user("leo.martins@evalia.local", "Leo Martins")
    samira_id = _ensure_user("samira.okafor@evalia.local", "Samira Okafor")
    devon_id = _ensure_user("devon.ross@evalia.local", "Devon Ross")
    org_id = _ensure_organization()
    _ensure_membership(org_id, recruiter_id, "org_owner")
    _ensure_membership(org_id, operations_recruiter_id, "recruiter")

    maya_profile_id = _seed_profile(
        maya_id,
        headline=PLATFORM_ROLE,
        summary="Platform engineer focused on reliable developer infrastructure, Kubernetes operations, and pragmatic automation.",
        location=AUSTIN_LOCATION,
        years_experience=6,
        resume_text="Maya Chen has six years of experience building Go services, Kubernetes platforms, and Terraform automation for high-growth teams.",
        experiences=[{"company": "Northstar Cloud", "title": "Platform Engineer", "location": AUSTIN_LOCATION, "start_date": "2021-04", "is_current": True, "description": "Built Kubernetes platform tooling and deployment automation."}, {"company": "Orbit Systems", "title": "Site Reliability Engineer", "location": AUSTIN_LOCATION, "start_date": "2018-07", "end_date": "2021-03", "description": "Improved service reliability and incident response."}],
        education=[{"institution": "University of Texas at Austin", "degree": "B.S.", "field": "Computer Science", "start_year": 2014, "end_year": 2018}],
        skills=[{"skill": "Go", "years": 5}, {"skill": "Kubernetes", "years": 5, "verified": True}, {"skill": "Terraform", "years": 4}, {"skill": "AWS", "years": 5}],
        desired_roles=[PLATFORM_ROLE, "Site Reliability Engineer"],
    )
    leo_profile_id = _seed_profile(
        leo_id,
        headline=DATA_ROLE,
        summary="Data engineer specializing in streaming platforms, warehouse reliability, and measurable pipeline performance.",
        location=NEW_YORK_LOCATION,
        years_experience=8,
        resume_text="Leo Martins has eight years of experience with Python, Kafka, Spark, SQL, and AWS data platforms.",
        experiences=[{"company": "SignalWorks", "title": DATA_ROLE, "location": NEW_YORK_LOCATION, "start_date": "2020-02", "is_current": True, "description": "Owned streaming ingestion and analytical data products."}, {"company": "Metric Labs", "title": "Data Engineer", "location": NEW_YORK_LOCATION, "start_date": "2017-06", "end_date": "2020-01", "description": "Built batch and streaming data pipelines."}],
        education=[{"institution": "Northeastern University", "degree": "M.S.", "field": "Data Science", "start_year": 2015, "end_year": 2017}],
        skills=[{"skill": "Python", "years": 8, "verified": True}, {"skill": "Kafka", "years": 6, "verified": True}, {"skill": "Spark", "years": 6}, {"skill": "SQL", "years": 8}, {"skill": "AWS", "years": 7}],
        desired_roles=[DATA_ROLE, "Staff Data Engineer"],
    )
    samira_profile_id = _seed_profile(
        samira_id,
        headline=FRONTEND_ROLE,
        summary="Frontend engineer who builds accessible, fast product experiences with strong design-system discipline.",
        location=SEATTLE_LOCATION,
        years_experience=5,
        resume_text="Samira Okafor has five years of experience building TypeScript and React applications for customer-facing products.",
        experiences=[{"company": "Canvas Health", "title": "Frontend Engineer", "location": SEATTLE_LOCATION, "start_date": "2021-08", "is_current": True, "description": "Built accessible product workflows with TypeScript and React."}],
        education=[{"institution": "University of Washington", "degree": "B.S.", "field": "Human Centered Design", "start_year": 2015, "end_year": 2019}],
        skills=[{"skill": "TypeScript", "years": 5}, {"skill": "React", "years": 5}, {"skill": "Next.js", "years": 3}, {"skill": "Accessibility", "years": 4}],
        desired_roles=[FRONTEND_ROLE, "Senior Frontend Engineer"],
    )
    devon_profile_id = _seed_profile(
        devon_id,
        headline=ML_ROLE,
        summary="Machine learning platform engineer focused on reliable model serving, evaluation, and developer tooling.",
        location="Remote",
        years_experience=7,
        resume_text="Devon Ross has seven years of experience building Python services, model serving platforms, and ML observability.",
        experiences=[{"company": "BrightScale AI", "title": "ML Platform Engineer", "location": "Remote", "start_date": "2019-09", "is_current": True, "description": "Built model deployment and evaluation infrastructure."}],
        education=[{"institution": "Georgia Tech", "degree": "M.S.", "field": "Computer Science", "start_year": 2016, "end_year": 2018}],
        skills=[{"skill": "Python", "years": 7}, {"skill": "Docker", "years": 6}, {"skill": "Kubernetes", "years": 4}, {"skill": "MLflow", "years": 3}],
        desired_roles=[ML_ROLE, "Machine Learning Engineer"],
    )

    campaign_id = _ensure_campaign(org_id, recruiter_id)
    posting_definitions = [
        {"title": PLATFORM_ROLE, "description": "Own the internal platform that helps engineering teams ship reliable services.", "location": AUSTIN_LOCATION, "remote_policy": "HYBRID", "min_experience": 5, "max_experience": 10, "salary_min": 155000, "salary_max": 190000, "currency": "USD", "required_skills": ["Go", "Kubernetes", "Terraform", "AWS"], "screening_questions": ["Describe a platform reliability improvement you led."], "status": hiring.PostingStatus.PUBLISHED},
        {"title": DATA_ROLE, "description": "Build dependable streaming and analytical data systems for product teams.", "location": NEW_YORK_LOCATION, "remote_policy": "REMOTE", "min_experience": 5, "max_experience": 12, "salary_min": 165000, "salary_max": 205000, "currency": "USD", "required_skills": ["Python", "Kafka", "Spark", "SQL"], "screening_questions": ["Tell us about a data pipeline you made idempotent."], "status": hiring.PostingStatus.PUBLISHED},
        {"title": "Staff Backend Engineer", "description": "Lead architecture for APIs and distributed backend services.", "location": "Remote", "remote_policy": "REMOTE", "min_experience": 8, "max_experience": 15, "salary_min": 190000, "salary_max": 235000, "currency": "USD", "required_skills": ["Python", "PostgreSQL", "Distributed Systems"], "screening_questions": ["How do you evolve a public API safely?"], "status": hiring.PostingStatus.DRAFT},
        {"title": FRONTEND_ROLE, "description": "Shape polished, accessible workflows used by thousands of customers.", "location": SEATTLE_LOCATION, "remote_policy": "HYBRID", "min_experience": 3, "max_experience": 8, "salary_min": 140000, "salary_max": 180000, "currency": "USD", "required_skills": ["TypeScript", "React", "Next.js", "Accessibility"], "screening_questions": ["How do you make a complex workflow accessible?"], "status": hiring.PostingStatus.PUBLISHED},
        {"title": ML_ROLE, "description": "Build the infrastructure that moves machine learning models from experiment to production.", "location": "Remote", "remote_policy": "REMOTE", "min_experience": 4, "max_experience": 10, "salary_min": 160000, "salary_max": 215000, "currency": "USD", "required_skills": ["Python", "Docker", "Kubernetes", "MLflow"], "screening_questions": ["How would you monitor model quality after deployment?"], "status": hiring.PostingStatus.PUBLISHED},
        {"title": "Application Security Engineer", "description": "Partner with product teams to make secure delivery a default engineering habit.", "location": "Boston, MA", "remote_policy": "HYBRID", "min_experience": 4, "max_experience": 10, "salary_min": 150000, "salary_max": 200000, "currency": "USD", "required_skills": ["Threat Modeling", "Python", "Cloud Security", "OWASP"], "screening_questions": ["Walk through a threat model for a new API."], "status": hiring.PostingStatus.PUBLISHED},
        {"title": "Senior Product Engineer", "description": "Work across the stack to turn customer problems into dependable product capabilities.", "location": "Chicago, IL", "remote_policy": "HYBRID", "min_experience": 4, "max_experience": 9, "salary_min": 145000, "salary_max": 185000, "currency": "USD", "required_skills": ["TypeScript", "Python", "PostgreSQL", "Product Thinking"], "screening_questions": ["Describe a product trade-off you made with incomplete information."], "status": hiring.PostingStatus.PUBLISHED},
        {"title": "Site Reliability Lead", "description": "Set reliability strategy and help teams operate critical services with confidence.", "location": "Denver, CO", "remote_policy": "REMOTE", "min_experience": 7, "max_experience": 14, "salary_min": 175000, "salary_max": 225000, "currency": "USD", "required_skills": ["SRE", "Kubernetes", "Observability", "Incident Management"], "screening_questions": ["How do you use an error budget to guide priorities?"], "status": hiring.PostingStatus.PUBLISHED},
        {"title": "Mobile Engineer", "description": "Build thoughtful mobile experiences for a growing customer community.", "location": "New York, NY", "remote_policy": "ONSITE", "min_experience": 3, "max_experience": 8, "salary_min": 135000, "salary_max": 175000, "currency": "USD", "required_skills": ["Swift", "Kotlin", "Mobile Testing"], "screening_questions": ["How do you design reliable offline behavior?"], "status": hiring.PostingStatus.PUBLISHED},
    ]
    postings = {
        posting["title"]: _ensure_posting(org_id, campaign_id, recruiter_id, posting)
        for posting in posting_definitions
    }
    platform_posting_id = postings[PLATFORM_ROLE]
    data_posting_id = postings[DATA_ROLE]

    maya_platform_app = _ensure_application(org_id, platform_posting_id, maya_id, maya_profile_id, [{"question_key": "reliability", "question_text": "Describe a platform reliability improvement you led.", "answer_text": "I introduced service ownership and SLO dashboards, then used the error budget to prioritize the highest-impact fixes."}])
    leo_data_app = _ensure_application(org_id, data_posting_id, leo_id, leo_profile_id, [{"question_key": "idempotency", "question_text": "Tell us about a data pipeline you made idempotent.", "answer_text": "I used stable event keys and checkpoint-aware writes so replaying a partition could not duplicate warehouse records."}])
    maya_data_app = _ensure_application(org_id, data_posting_id, maya_id, maya_profile_id, [])
    samira_frontend_app = _ensure_application(org_id, postings[FRONTEND_ROLE], samira_id, samira_profile_id, [])
    devon_ml_app = _ensure_application(org_id, postings[ML_ROLE], devon_id, devon_profile_id, [])
    _advance_application(maya_platform_app, org_id, recruiter_id, ["SCREENING", "TECHNICAL"])
    _advance_application(leo_data_app, org_id, recruiter_id, ["SCREENING", "TECHNICAL", "BEHAVIORAL", "INTERVIEW", "OFFER", "HIRED"])
    _advance_application(samira_frontend_app, org_id, recruiter_id, ["SCREENING"])

    complete_id = _seed_complete_evaluation(org_id, recruiter_id)
    in_progress_id = _seed_in_progress_evaluation(org_id, recruiter_id)
    rejected_id = _seed_rejected_evaluation(org_id, recruiter_id)
    _link_evaluation(leo_data_app, complete_id)
    _link_evaluation(maya_platform_app, in_progress_id)

    return {
        "database": str(Path(db._SQLITE_PATH).resolve()),
        "demo_password": DEMO_LOGIN,
        "accounts": {
            "recruiter_owner": "recruiter.demo@evalia.local",
            "recruiter_member": "recruiter.ops@evalia.local",
            "candidates": ["maya.chen@evalia.local", "leo.martins@evalia.local", "samira.okafor@evalia.local", "devon.ross@evalia.local"],
            "shared_password": DEMO_LOGIN,
        },
        "organization_id": org_id,
        "application_ids": [maya_platform_app, leo_data_app, maya_data_app, samira_frontend_app, devon_ml_app],
        "evaluation_ids": [complete_id, in_progress_id, rejected_id],
    }


if __name__ == "__main__":
    result = seed_demo()
    print(json.dumps(result, indent=2))