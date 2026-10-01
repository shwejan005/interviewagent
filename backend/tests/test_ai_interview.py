"""End-to-end tests for application-submit screening and candidate AI interviews."""

import asyncio

import pytest

from app.ai_interview import service as ai_service
from app.ai_interview import repository as interview_db
from app.ai_interview.dto import (
    AnswerAssessment,
    ApplicationScreeningAssessment,
    InterviewQuestion,
    InterviewQuestionPlan,
    ScreeningEvidence,
)
from app.config import database as db
from app.hiring import repository as hdb
from app.worker.job_worker import run_once
from tests.test_hiring import _make_posting
from tests.test_identity import _auth, _create_org, _register


@pytest.fixture
def ai_recruiter(client):
    token = _register(client, "ai-pipeline-recruiter@example.com", name="Pipeline Recruiter")
    org_id = _create_org(client, token, slug="ai-pipeline-org")
    return {"token": token, "org_id": org_id}


@pytest.fixture
def ai_candidate(client):
    token = _register(client, "ai-pipeline-candidate@example.com", name="Pipeline Candidate")
    client.put(
        "/me/profile",
        json={
            "headline": "Backend Engineer",
            "summary": "Builds reliable services.",
            "years_experience": 5,
        },
        headers=_auth(token),
    )
    client.put(
        "/me/profile/skills",
        json={"skills": [{"skill": "Python", "years": 5}, {"skill": "PostgreSQL", "years": 3}]},
        headers=_auth(token),
    )
    return {"token": token}


def _question_plan(policy):
    competencies = policy["competencies"]
    technical_key = next((item["key"] for item in competencies if item["key"] != "behavioral_communication"), competencies[0]["key"])
    behavioral_key = next((item["key"] for item in competencies if item["key"] == "behavioral_communication"), competencies[-1]["key"])
    return InterviewQuestionPlan(
        technical_questions=[
            InterviewQuestion(competency_key=technical_key, question="Technical core one: explain a reliable API design.", difficulty=2),
            InterviewQuestion(competency_key=technical_key, question="Technical core two: how would you debug a slow query?", difficulty=2),
        ],
        behavioral_questions=[
            InterviewQuestion(competency_key=behavioral_key, question="Behavioral core one: describe a team disagreement.", difficulty=2),
            InterviewQuestion(competency_key=behavioral_key, question="Behavioral core two: describe a time you took ownership.", difficulty=2),
        ],
    )


async def _drain_until(client, application_id, token, predicate, *, max_jobs=12):
    for _ in range(max_jobs):
        state = client.get(f"/me/applications/{application_id}/ai-interview", headers=_auth(token))
        assert state.status_code == 200, state.text
        if predicate(state.json()):
            return state.json()
        found = await run_once("ai-interview-test-worker")
        if not found:
            break
    state = client.get(f"/me/applications/{application_id}/ai-interview", headers=_auth(token))
    assert state.status_code == 200, state.text
    assert predicate(state.json()), f"Interview did not reach expected state; last state: {state.json()}"
    return state.json()


def test_application_submission_queues_screening_atomically(client, isolated_db, ai_recruiter, ai_candidate):
    posting = _make_posting(client, ai_recruiter)
    response = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"]))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "SCREENING_QUEUED"

    application = hdb.get_application(body["application_id"], ai_recruiter["org_id"])
    assert application["current_stage"] == "APPLIED"
    assert application["ai_interview_status"] == "SCREENING_QUEUED"
    job = isolated_db.get_job_by_idempotency_key(f"application-screening:{body['application_id']}")
    assert job is not None
    assert job["job_type"] == "application_screening"
    assert job["tenant_key"] == f"org:{ai_recruiter['org_id']}"
    interview_id = job["payload"]["interview_id"]
    run = isolated_db.get_job(job["id"])
    assert run["payload"]["application_id"] == body["application_id"]
    assert isolated_db.get_job_by_idempotency_key(f"application-screening:{body['application_id']}")["payload"]["interview_id"] == interview_id

    duplicate = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"]))
    assert duplicate.status_code == 409
    assert isolated_db.get_job_by_idempotency_key(f"application-screening:{body['application_id']}")["id"] == job["id"]


def test_clear_screen_pass_creates_ready_candidate_interview_and_human_review_report(
    client, isolated_db, ai_recruiter, ai_candidate, monkeypatch
):
    posting = _make_posting(client, ai_recruiter)
    org_id = ai_recruiter["org_id"]
    recruiter_headers = _auth(ai_recruiter["token"], org_id)
    client.put(
        f"/orgs/{org_id}/postings/{posting['id']}/criteria",
        json={
            "competencies": [
                {"key": "technical_skills", "label": "Python technical reasoning", "weight": 80, "description": "Reason about backend system correctness and reliability."},
                {"key": "behavioral_communication", "label": "Behavioral communication and collaboration", "weight": 20, "description": "Concrete collaboration and ownership evidence."},
            ],
            "custom_questions": [],
            "pass_threshold": 6,
            "interview_settings": {
                "role_level": "MID",
                "technical_question_count": 2,
                "behavioral_question_count": 2,
                "max_followups_per_question": 1,
            },
        },
        headers=recruiter_headers,
    )
    application_response = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"]))
    assert application_response.status_code == 201, application_response.text
    application_id = application_response.json()["application_id"]

    async def fake_screen(**_kwargs):
        return ApplicationScreeningAssessment(
            decision="PASS",
            score=8.5,
            evidence=[
                ScreeningEvidence(criterion_key="required_skill_1", status="MET", source="PROFILE", quote="Python", rationale="Listed in candidate skills."),
                ScreeningEvidence(criterion_key="required_skill_2", status="MET", source="PROFILE", quote="PostgreSQL", rationale="Listed in candidate skills."),
            ],
            strengths=["Python and PostgreSQL skills are present."],
            gaps=[],
            summary="The submitted evidence meets the published job-related criteria.",
        ), "{}"

    assessment_calls = []

    async def fake_assess(*, question, difficulty, **_kwargs):
        assessment_calls.append(question)
        follow_up = "How did you verify that approach worked?" if question.startswith("Technical core one") else None
        return AnswerAssessment(
            score=8,
            evidence_quote="I designed a reliable service",
            summary="The answer gives a concrete, job-related example.",
            strengths=["Explained an implementation choice."],
            gaps=[],
            follow_up_question=follow_up,
            next_difficulty=min(3, difficulty + 1),
        ), "{}"

    monkeypatch.setattr(ai_service.llm, "screen_application", fake_screen)
    monkeypatch.setattr(ai_service, "build_question_plan", lambda policy, role: _question_plan(policy).model_dump(mode="json"))
    monkeypatch.setattr(ai_service.llm, "assess_answer", fake_assess)

    ready = asyncio.run(_drain_until(
        client,
        application_id,
        ai_candidate["token"],
        lambda state: state["status"] == "INTERVIEW_READY",
    ))
    assert ready["phase"] == "TECHNICAL"
    assert ready["role_level"] == "MID"
    assert ready["consent_required"] is True
    assert ready["current_question"]["question_type"] == "CORE"
    assert hdb.get_application(application_id, org_id)["current_stage"] == "AI_INTERVIEW"
    screening_job = isolated_db.get_job_by_idempotency_key(f"application-screening:{application_id}")
    assert screening_job is not None
    ready_notification = isolated_db.get_job_by_idempotency_key(
        f"application-ai-ready-notification:{application_id}:{screening_job['payload']['interview_id']}"
    )
    assert ready_notification is not None

    foreign_candidate = _register(client, "ai-pipeline-outsider@example.com", name="Other Candidate")
    assert client.get(
        f"/me/applications/{application_id}/ai-interview", headers=_auth(foreign_candidate)
    ).status_code == 404

    notice = ready["candidate_notice_version"]
    bad_start = client.post(
        f"/me/applications/{application_id}/ai-interview/start",
        json={"accepted": True, "notice_version": "old-version", "modality": "TEXT"},
        headers=_auth(ai_candidate["token"]),
    )
    assert bad_start.status_code == 409
    started = client.post(
        f"/me/applications/{application_id}/ai-interview/start",
        json={"accepted": True, "notice_version": notice, "modality": "TEXT"},
        headers=_auth(ai_candidate["token"]),
    )
    assert started.status_code == 200, started.text
    question = started.json()["current_question"]
    assert question["question_text"].startswith("Technical core one")

    answer_text = "I designed a reliable service and tested the failure modes."
    submitted = client.post(
        f"/me/applications/{application_id}/ai-interview/answers",
        json={"turn_id": question["id"], "answer": answer_text},
        headers=_auth(ai_candidate["token"]),
    )
    assert submitted.status_code == 202, submitted.text
    duplicate = client.post(
        f"/me/applications/{application_id}/ai-interview/answers",
        json={"turn_id": question["id"], "answer": answer_text},
        headers=_auth(ai_candidate["token"]),
    )
    assert duplicate.status_code == 202, duplicate.text
    assert duplicate.json()["duplicate"] is True
    conflicting = client.post(
        f"/me/applications/{application_id}/ai-interview/answers",
        json={"turn_id": question["id"], "answer": "A different answer."},
        headers=_auth(ai_candidate["token"]),
    )
    assert conflicting.status_code == 409

    state = client.get(f"/me/applications/{application_id}/ai-interview", headers=_auth(ai_candidate["token"])).json()
    assert state["status"] == "ANSWER_PROCESSING"
    follow_up = asyncio.run(_drain_until(
        client,
        application_id,
        ai_candidate["token"],
        lambda value: value["status"] == "INTERVIEW_IN_PROGRESS" and value["current_question"] and value["current_question"]["question_type"] == "FOLLOW_UP",
    ))
    assert follow_up["current_question"]["difficulty"] in (1, 2, 3)
    assert len(assessment_calls) == 1

    # Complete the bounded follow-up and all remaining technical/behavioral turns.
    current = follow_up
    for _ in range(10):
        if current["status"] == "REPORT_PENDING":
            break
        turn = current["current_question"]
        assert turn is not None, current
        answer = "I designed a reliable service and tested the failure modes."
        result = client.post(
            f"/me/applications/{application_id}/ai-interview/answers",
            json={"turn_id": turn["id"], "answer": answer},
            headers=_auth(ai_candidate["token"]),
        )
        assert result.status_code == 202, result.text
        current = asyncio.run(_drain_until(
            client,
            application_id,
            ai_candidate["token"],
            lambda value: value["status"] != "ANSWER_PROCESSING",
        ))
    assert current["status"] == "REPORT_PENDING", current

    final_state = asyncio.run(_drain_until(
        client,
        application_id,
        ai_candidate["token"],
        lambda value: value["status"] == "REPORT_READY",
    ))
    assert final_state["phase"] == "COMPLETE"
    app = hdb.get_application(application_id, org_id)
    assert app["current_stage"] == "PENDING_REVIEW"
    assert app["status"] == "IN_PROGRESS"
    assert isolated_db.get_evaluation(app["evaluation_id"])["status"] == "COMPLETE"

    report_response = client.get(f"/orgs/{org_id}/applications/{application_id}/report", headers=recruiter_headers)
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["recommendation"] == "HUMAN_REVIEW_REQUIRED"
    assert report["interview_details"]["interview"]["human_decision_required"] is True
    assert len(report["interview_details"]["interview"]["turns"]) == 5
    assert report["overall_weighted_score"] is None
    recruiter_session = client.get(
        f"/orgs/{org_id}/applications/{application_id}/ai-interview", headers=recruiter_headers
    )
    assert recruiter_session.status_code == 200, recruiter_session.text
    assert recruiter_session.json()["role_level"] == "MID"
    evaluation_id = hdb.get_application(application_id, org_id)["evaluation_id"]
    assert client.get(f"/evaluations/{evaluation_id}", headers=_auth(ai_candidate["token"])).status_code == 404
    generic_list = client.get("/evaluations", headers=_auth(ai_candidate["token"])).json()["evaluations"]
    assert evaluation_id not in {item["id"] for item in generic_list}

    unassigned_recruiter = _register(client, "ai-unassigned@example.com", name="Unassigned Recruiter")
    added = client.post(
        f"/orgs/{org_id}/members",
        json={"email": "ai-unassigned@example.com", "role": "recruiter"},
        headers=recruiter_headers,
    )
    assert added.status_code == 201, added.text
    unassigned_headers = _auth(unassigned_recruiter, org_id)
    assert client.get(
        f"/orgs/{org_id}/applications/{application_id}/ai-interview", headers=unassigned_headers
    ).status_code == 404
    assert client.get(f"/evaluations/{evaluation_id}", headers=unassigned_headers).status_code == 404


def test_report_persistence_does_not_rewind_a_recruiter_advanced_application(
    client, isolated_db, ai_recruiter, ai_candidate
):
    posting = _make_posting(client, ai_recruiter)
    application_id = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"])
    ).json()["application_id"]
    run = interview_db.get_internal(application_id)
    evaluation_id = interview_db.ensure_evaluation(run["id"])

    for stage in (hdb.ApplicationStage.SCREENING, hdb.ApplicationStage.AI_INTERVIEW, hdb.ApplicationStage.INTERVIEW):
        hdb.transition_application(application_id, ai_recruiter["org_id"], str(stage), None)

    p = db._ph()
    with db._get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'REPORT_PENDING', phase = 'COMPLETE' WHERE id = {p}",
            (run["id"],),
        )

    assert interview_db.persist_application_report(
        run["id"],
        competency_scores=[],
        overall_weighted_score=None,
        recommendation="HUMAN_REVIEW_REQUIRED",
        interview_details={"source": "test"},
    ) is True
    assert hdb.get_application(application_id, ai_recruiter["org_id"])["current_stage"] == "INTERVIEW"
    assert isolated_db.get_evaluation(evaluation_id)["status"] == "COMPLETE"
    state = interview_db.get_internal(application_id)
    assert state["status"] == "REPORT_READY"


def test_late_report_is_discarded_after_terminal_rejection(client, ai_recruiter, ai_candidate):
    posting = _make_posting(client, ai_recruiter)
    application_id = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"])
    ).json()["application_id"]
    run = interview_db.get_internal(application_id)
    interview_db.ensure_evaluation(run["id"])
    hdb.transition_application(
        application_id, ai_recruiter["org_id"], str(hdb.ApplicationStage.REJECTED), None
    )

    p = db._ph()
    with db._get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'REPORT_PENDING', phase = 'COMPLETE' WHERE id = {p}",
            (run["id"],),
        )

    assert interview_db.persist_application_report(
        run["id"],
        competency_scores=[],
        overall_weighted_score=None,
        recommendation="HUMAN_REVIEW_REQUIRED",
        interview_details={"source": "test"},
    ) is False
    assert hdb.get_application(application_id, ai_recruiter["org_id"])["current_stage"] == "REJECTED"
    assert interview_db.get_internal(application_id)["status"] == "CANCELLED"


def test_withdrawal_cancels_pending_report_before_it_is_persisted(
    client, ai_recruiter, ai_candidate
):
    posting = _make_posting(client, ai_recruiter)
    application_id = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"])
    ).json()["application_id"]
    run = interview_db.get_internal(application_id)
    interview_db.ensure_evaluation(run["id"])

    p = db._ph()
    with db._get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE application_ai_interviews SET status = 'REPORT_PENDING', phase = 'COMPLETE' WHERE id = {p}",
            (run["id"],),
        )

    withdrawn = client.post(
        f"/me/applications/{application_id}/withdraw", headers=_auth(ai_candidate["token"])
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert interview_db.persist_application_report(
        run["id"],
        competency_scores=[],
        overall_weighted_score=None,
        recommendation="HUMAN_REVIEW_REQUIRED",
        interview_details={"source": "test"},
    ) is False
    assert hdb.get_application(application_id, ai_recruiter["org_id"])["current_stage"] == "WITHDRAWN"
    assert interview_db.get_internal(application_id)["status"] == "CANCELLED"
    with db._get_conn() as (conn, cur):
        cur.execute(f"SELECT application_id FROM application_interview_reports WHERE application_id = {p}", (application_id,))
        assert cur.fetchone() is None


def test_borderline_screening_goes_to_human_review_without_an_interview(
    client, isolated_db, ai_recruiter, ai_candidate, monkeypatch
):
    posting = _make_posting(client, ai_recruiter)
    response = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"]))
    application_id = response.json()["application_id"]

    async def borderline(**_kwargs):
        return ApplicationScreeningAssessment(
            decision="REVIEW_REQUIRED",
            score=5,
            evidence=[ScreeningEvidence(criterion_key="required_skill_1", status="UNCLEAR", rationale="Evidence needs human review.")],
            strengths=[],
            gaps=["Evidence is not conclusive."],
            summary="Needs a person to review the missing evidence.",
        ), "{}"

    def should_not_plan(*_args, **_kwargs):
        raise AssertionError("A borderline screening result must not start an interview")

    monkeypatch.setattr(ai_service.llm, "screen_application", borderline)
    monkeypatch.setattr(ai_service, "build_question_plan", should_not_plan)
    assert asyncio.run(run_once("ai-interview-borderline-worker")) is True

    state = client.get(f"/me/applications/{application_id}/ai-interview", headers=_auth(ai_candidate["token"])).json()
    assert state["status"] == "REVIEW_REQUIRED"
    assert state["consent_required"] is False
    app = hdb.get_application(application_id, ai_recruiter["org_id"])
    assert app["current_stage"] == "PENDING_REVIEW"
    assert app["status"] == "IN_PROGRESS"
    assert isolated_db.get_job_by_idempotency_key(f"application-ai-ready-notification:{application_id}:1") is None


def test_screening_pass_with_a_fabricated_skill_quote_requires_human_review(
    client, isolated_db, ai_recruiter, ai_candidate, monkeypatch
):
    posting = _make_posting(client, ai_recruiter)
    application_id = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"])).json()["application_id"]

    async def fabricated_evidence(**_kwargs):
        return ApplicationScreeningAssessment(
            decision="PASS",
            score=9,
            evidence=[
                ScreeningEvidence(criterion_key="required_skill_1", status="MET", source="PROFILE", quote="Kubernetes", rationale="Claimed skill."),
                ScreeningEvidence(criterion_key="required_skill_2", status="MET", source="PROFILE", quote="PostgreSQL", rationale="Listed skill."),
            ],
            summary="Strong match.",
        ), "{}"

    def should_not_plan(*_args, **_kwargs):
        raise AssertionError("Fabricated evidence must not prepare an interview")

    monkeypatch.setattr(ai_service.llm, "screen_application", fabricated_evidence)
    monkeypatch.setattr(ai_service, "build_question_plan", should_not_plan)
    assert asyncio.run(run_once("ai-interview-fabricated-evidence-worker")) is True

    state = client.get(f"/me/applications/{application_id}/ai-interview", headers=_auth(ai_candidate["token"])).json()
    assert state["status"] == "REVIEW_REQUIRED"
    assert hdb.get_application(application_id, ai_recruiter["org_id"])["current_stage"] == "PENDING_REVIEW"
    assert isolated_db.get_job_by_idempotency_key(f"application-ai-ready-notification:{application_id}:1") is None


def test_candidate_withdrawal_cancels_queued_ai_screening_and_scrubs_resume(
    client, isolated_db, ai_recruiter, ai_candidate, monkeypatch
):
    posting = _make_posting(client, ai_recruiter)
    application_id = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"])).json()["application_id"]

    async def should_not_screen(**_kwargs):
        raise AssertionError("Withdrawn applications must not be sent to the screening model")

    monkeypatch.setattr(ai_service.llm, "screen_application", should_not_screen)
    withdrawn = client.post(f"/me/applications/{application_id}/withdraw", headers=_auth(ai_candidate["token"]))
    assert withdrawn.status_code == 200
    screen_job = isolated_db.get_job_by_idempotency_key(f"application-screening:{application_id}")
    assert screen_job["status"] == "CANCELLED"
    run = interview_db.get_internal(application_id)
    assert run["status"] == "CANCELLED"
    assert run["screening_input"] == {}
    assert asyncio.run(run_once("ai-interview-withdrawn-worker")) is False


def test_human_reviewer_can_approve_a_screening_exception_with_audited_reason(
    client, isolated_db, ai_recruiter, ai_candidate, monkeypatch
):
    posting = _make_posting(client, ai_recruiter)
    org_id = ai_recruiter["org_id"]
    recruiter_headers = _auth(ai_recruiter["token"], org_id)
    application_id = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"])
    ).json()["application_id"]

    async def needs_review(**_kwargs):
        return ApplicationScreeningAssessment(
            decision="REVIEW_REQUIRED",
            score=5,
            evidence=[ScreeningEvidence(criterion_key="required_skill_1", status="UNCLEAR", rationale="The resume evidence is ambiguous.")],
            gaps=["A recruiter should inspect the work example."],
            summary="One required skill needs human review.",
        ), "{}"

    monkeypatch.setattr(ai_service.llm, "screen_application", needs_review)
    assert asyncio.run(run_once("ai-interview-human-override-worker")) is True
    status = client.get(f"/me/applications/{application_id}/ai-interview", headers=_auth(ai_candidate["token"]))
    assert status.json()["status"] == "REVIEW_REQUIRED"

    missing_reason = client.post(
        f"/orgs/{org_id}/applications/{application_id}/ai-interview/approve-screening-exception",
        json={"reason": "ok"},
        headers=recruiter_headers,
    )
    assert missing_reason.status_code == 422

    approved = client.post(
        f"/orgs/{org_id}/applications/{application_id}/ai-interview/approve-screening-exception",
        json={"reason": "Reviewed the missing evidence and confirmed relevant Python work."},
        headers=recruiter_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "INTERVIEW_READY"
    assert hdb.get_application(application_id, org_id)["current_stage"] == "AI_INTERVIEW"
    ready = client.get(f"/me/applications/{application_id}/ai-interview", headers=_auth(ai_candidate["token"]))
    assert ready.status_code == 200
    assert ready.json()["consent_required"] is True


def test_other_org_cannot_read_application_interview_or_report(client, ai_recruiter, ai_candidate):
    posting = _make_posting(client, ai_recruiter)
    application_id = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(ai_candidate["token"])
    ).json()["application_id"]
    outsider = _register(client, "ai-other-org@example.com")
    other_org = _create_org(client, outsider, slug="ai-other-org")
    headers = _auth(outsider, other_org)
    assert client.get(
        f"/orgs/{ai_recruiter['org_id']}/applications/{application_id}/ai-interview", headers=headers
    ).status_code == 404
    assert client.get(
        f"/orgs/{ai_recruiter['org_id']}/applications/{application_id}/report", headers=headers
    ).status_code == 404


def test_apply_requires_resume_or_a_minimal_manual_profile(client, ai_recruiter):
    token = _register(client, "ai-profileless@example.com", name="No Profile")
    client.put("/me/profile", json={"headline": ""}, headers=_auth(token))
    posting = _make_posting(client, ai_recruiter)
    response = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(token))
    assert response.status_code == 400
    assert "missing_profile_fields" in response.json()["detail"]

    client.put("/me/profile", json={"headline": "Junior Python Developer"}, headers=_auth(token))
    client.put("/me/profile/skills", json={"skills": [{"skill": "Python"}]}, headers=_auth(token))
    accepted = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(token))
    assert accepted.status_code == 201, accepted.text
