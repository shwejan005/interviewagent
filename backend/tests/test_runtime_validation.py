"""End-to-end API journeys for the organized backend packages."""

from app.candidate import repository as candidate_repository
from app.hiring import repository as hiring_repository
from app.interview_criteria.service import ReportService
from tests.test_hiring import _make_posting
from tests.test_identity import _auth, _create_org, _register
from tests.test_routes import _patch_happy_path


def test_candidate_resume_parse_import_and_readback(client):
    token = _register(client, "runtime-candidate@example.com")
    headers = _auth(token)

    assert client.get("/me/profile").status_code == 401
    denied = client.post(
        "/me/resume/parse",
        files={"file": ("resume.txt", b"Ada Candidate\nPython backend engineer", "text/plain")},
    )
    assert denied.status_code == 401

    parsed_response = client.post(
        "/me/resume/parse",
        files={
            "file": (
                "resume.txt",
                b"Ada Candidate\nPython backend engineer\nSkills: Python, PostgreSQL",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert parsed_response.status_code == 200, parsed_response.text
    parsed = parsed_response.json()
    assert parsed["resume_document_id"] > 0
    assert parsed["char_count"] > 0

    imported = client.post(
        "/me/resume/import",
        json={
            "headline": "Edited Backend Engineer",
            "summary": "Reviewed and confirmed profile",
            "location": "Remote",
            "phone": "+1 555 0100",
            "work_authorization": "Authorized",
            "years_experience": 6,
            "resume_text": "Confirmed resume text",
            "skills": [{"skill": "Python", "years": 6}],
            "work_experiences": [
                {
                    "company": "Example Systems",
                    "title": "Backend Engineer",
                    "location": "Remote",
                    "start_date": "2020-01",
                    "end_date": None,
                    "is_current": True,
                    "description": "Built APIs",
                }
            ],
            "education": [
                {
                    "institution": "State University",
                    "degree": "B.Tech",
                    "field": "Computer Science",
                    "start_year": 2014,
                    "end_year": 2018,
                }
            ],
        },
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    profile = client.get("/me/profile", headers=headers)
    assert profile.status_code == 200
    body = profile.json()
    assert body["headline"] == "Edited Backend Engineer"
    assert body["skills"][0]["skill"] == "Python"
    assert body["experiences"][0]["company"] == "Example Systems"
    assert body["education"][0]["institution"] == "State University"


def test_recruiter_criteria_and_report_round_trip(client, isolated_db):
    recruiter_token = _register(client, "runtime-recruiter@example.com")
    org_id = _create_org(client, recruiter_token, slug="runtime-org")
    recruiter_headers = _auth(recruiter_token, org_id)
    candidate_token = _register(client, "runtime-applicant@example.com")
    candidate_headers = _auth(candidate_token)
    client.put(
        "/me/profile",
        json={"headline": "Backend Engineer", "resume_text": "Python PostgreSQL experience"},
        headers=candidate_headers,
    )
    posting = _make_posting(client, {"token": recruiter_token, "org_id": org_id})

    assert client.get(
        f"/orgs/{org_id}/postings/{posting['id']}/criteria",
    ).status_code == 401
    criteria_response = client.put(
        f"/orgs/{org_id}/postings/{posting['id']}/criteria",
        json={
            "competencies": [
                {"key": "technical_skills", "label": "Technical skills", "weight": 60, "description": ""},
                {"key": "communication", "label": "Communication", "weight": 40, "description": ""},
            ],
            "custom_questions": ["Describe a difficult tradeoff."],
            "pass_threshold": 6.0,
        },
        headers=recruiter_headers,
    )
    assert criteria_response.status_code == 200, criteria_response.text
    assert criteria_response.json()["competencies"][0]["weight"] == 60

    application_response = client.post(
        f"/jobs/{posting['id']}/apply",
        json={},
        headers=candidate_headers,
    )
    assert application_response.status_code == 201, application_response.text
    application_id = application_response.json()["application_id"]
    candidate_user_id = client.get("/auth/me", headers=candidate_headers).json()["user_id"]
    profile = candidate_repository.get_profile_by_user(candidate_user_id)
    evaluation_id = isolated_db.create_evaluation(
        "Python PostgreSQL experience", "Backend Engineer", "Runtime Applicant", org_id, candidate_user_id
    )
    hiring_repository.attach_evaluation(application_id, org_id, evaluation_id)
    for round_number, agent_type, score, text in (
        (1, "screening", 7.0, "Good screening fit."),
        (2, "technical", 8.5, "Strong technical skills."),
        (3, "behavioral", 7.5, "Clear communication and teamwork."),
    ):
        isolated_db.save_verdict(
            evaluation_id=evaluation_id,
            agent_type=agent_type,
            round_number=round_number,
            verdict_json={"decision": "PASS"},
            verdict_text=text,
            score=score,
            decision="PASS",
            confidence=0.9,
        )
    isolated_db.update_evaluation(
        evaluation_id,
        status="COMPLETE",
        current_round=5,
        final_decision="HIRE",
    )
    assert profile["id"] > 0
    assert ReportService().generate_from_evaluation(evaluation_id) is not None

    report_response = client.get(
        f"/orgs/{org_id}/applications/{application_id}/report",
        headers=recruiter_headers,
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["recommendation"] == "HIRE"
    assert report["overall_weighted_score"] == 8.1


def test_full_interview_pipeline_persists_final_decision(client, isolated_db, monkeypatch):
    _patch_happy_path(monkeypatch)
    assert client.get("/auth/me").status_code == 401

    start = client.post(
        "/start",
        json={"resume": "Runtime resume", "role": "Backend Developer", "candidate_name": "Runtime Candidate"},
    )
    assert start.status_code == 200, start.text
    evaluation_id = start.json()["evaluation_id"]

    round_two = client.post(
        f"/round/2/answer?evaluation_id={evaluation_id}",
        json={"answer": "A structured technical answer"},
    )
    assert round_two.status_code == 200, round_two.text
    round_three = client.post(
        f"/round/3/answer?evaluation_id={evaluation_id}",
        json={"answer": "A structured behavioral answer"},
    )
    assert round_three.status_code == 200, round_three.text

    final = client.get(f"/final-decision?evaluation_id={evaluation_id}")
    assert final.status_code == 200, final.text
    assert final.json()["decision"] == "HIRE"
    persisted = isolated_db.get_evaluation(evaluation_id)
    assert persisted["status"] == "COMPLETE"
    assert len(isolated_db.get_verdicts(evaluation_id)) == 5
