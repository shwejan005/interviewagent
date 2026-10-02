"""Data export and deletion regression coverage."""

from tests.test_identity import _auth, _create_org, _register
from tests.test_hiring import _make_posting
from app.ai_interview import repository as ai_interview_db
from app.config import database as db


def _create_application_with_ai_interview(client, candidate_token):
    recruiter_token = _register(client, "privacy-recruiter@example.com", name="Privacy Recruiter")
    org_id = _create_org(client, recruiter_token, slug="privacy-interview-org")
    posting = _make_posting(client, {"token": recruiter_token, "org_id": org_id})
    client.put(
        "/me/profile",
        json={"headline": "Synthetic Engineer", "years_experience": 5},
        headers=_auth(candidate_token),
    )
    client.put(
        "/me/profile/skills",
        json={"skills": [{"skill": "Python", "years": 5}]},
        headers=_auth(candidate_token),
    )
    response = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate_token)
    )
    assert response.status_code == 201, response.text
    return org_id, response.json()["application_id"]


def _add_synthetic_ai_turn(application_id, org_id, candidate_user_id):
    run = ai_interview_db.get_internal(application_id, org_id)
    assert run is not None
    p = db._ph()
    with db._get_conn() as (conn, cur):
        cur.execute(
            f"UPDATE application_ai_interviews SET consent_version = {p}, consent_at = {db._now_sql()} WHERE id = {p}",
            ("ai-interview-test-v1", run["id"]),
        )
        cur.execute(
            f"INSERT INTO application_ai_interview_turns "
            f"(interview_id, application_id, org_id, candidate_user_id, sequence_no, phase, competency_key, "
            f"question_text, draft_answer_text, answer_text, answer_source) "
            f"VALUES ({p}, {p}, {p}, {p}, 1, 'TECHNICAL', 'python', {p}, {p}, {p}, 'VOICE')",
            (
                run["id"], application_id, org_id, candidate_user_id,
                "Synthetic question?", "Unsubmitted draft.", "Synthetic transcript answer.",
            ),
        )
    return run


def test_user_export_is_authenticated_and_contains_user_scoped_sections(client):
    token = _register(client, "export-user@example.com", name="Export User")
    client.put("/me/profile", json={"headline": "Engineer"}, headers=_auth(token))

    response = client.get("/auth/me/export", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["export_version"] == "user-data-v1"
    assert body["user"]["email"] == "export-user@example.com"
    assert body["profile"]["headline"] == "Engineer"
    assert "password_hash" not in body["user"]


def test_user_export_includes_owned_ai_interview_consent_drafts_and_transcript(client):
    token = _register(client, "export-ai-user@example.com", name="AI Export User")
    user_id = client.get("/auth/me", headers=_auth(token)).json()["user_id"]
    org_id, application_id = _create_application_with_ai_interview(client, token)
    _add_synthetic_ai_turn(application_id, org_id, user_id)

    response = client.get("/auth/me/export", headers=_auth(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["ai_interviews"]) == 1
    exported_run = body["ai_interviews"][0]
    assert exported_run["application_id"] == application_id
    assert exported_run["consent_version"] == "ai-interview-test-v1"
    assert exported_run["turns"][0]["draft_answer_text"] == "Unsubmitted draft."
    assert exported_run["turns"][0]["answer_text"] == "Synthetic transcript answer."
    assert exported_run["turns"][0]["answer_source"] == "VOICE"
    assert "assessment_json" not in exported_run["turns"][0]
    assert "screening_input_json" not in exported_run


def test_last_org_owner_cannot_delete_account(client):
    token = _register(client, "owner-delete@example.com")
    _create_org(client, token, slug="owner-delete-org")

    response = client.delete("/auth/me", headers=_auth(token))

    assert response.status_code == 409


def test_account_deletion_anonymizes_identity_and_removes_profile(client):
    token = _register(client, "delete-user@example.com")
    client.put(
        "/me/profile",
        json={"headline": "Private profile", "resume_text": "PRIVATE_DELETE_MARKER"},
        headers=_auth(token),
    )

    deleted = client.delete("/auth/me", headers=_auth(token))

    assert deleted.status_code == 204
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401


def test_account_deletion_removes_ai_interview_data_and_cancels_pending_screening(client):
    token = _register(client, "delete-ai-user@example.com", name="Delete AI User")
    client.put(
        "/me/profile",
        json={"headline": "Private profile", "resume_text": "PRIVATE_DELETE_MARKER"},
        headers=_auth(token),
    )
    user_id = client.get("/auth/me", headers=_auth(token)).json()["user_id"]
    org_id, application_id = _create_application_with_ai_interview(client, token)
    run = _add_synthetic_ai_turn(application_id, org_id, user_id)
    screening_job = db.get_job_by_idempotency_key(f"application-screening:{application_id}")
    assert screening_job is not None
    report_notification_id = db.enqueue_job(
        "application_interview_report_ready_notification",
        {"application_id": application_id, "interview_id": run["id"], "org_id": org_id},
        idempotency_key=f"application-ai-report-ready-notification:{application_id}:{run['id']}",
        tenant_key=f"org:{org_id}",
    )

    deleted = client.delete("/auth/me", headers=_auth(token))

    assert deleted.status_code == 204
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401
    assert ai_interview_db.get_internal(application_id, org_id) is None
    cancelled_job = db.get_job(screening_job["id"])
    assert cancelled_job["status"] == "CANCELLED"
    assert db.get_job(report_notification_id)["status"] == "CANCELLED"
