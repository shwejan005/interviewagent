"""Tests for the interview_criteria domain: recruiter-defined per-posting
competencies (with default-derivation from required_skills), the report
generation heuristic, and the finalize_evaluation hook that generates a
report automatically once a linked evaluation completes.
"""

import asyncio

import pytest

from app.candidate import repository as cdb
from app.hiring import repository as hdb
from app.interview_criteria.service import ReportService
from tests.test_hiring import _make_posting
from tests.test_identity import _auth, _create_org, _register


@pytest.fixture
def recruiter(client):
    token = _register(client, "criteria-recruiter@example.com")
    org_id = _create_org(client, token, slug="criteria-org")
    return {"token": token, "org_id": org_id}


@pytest.fixture
def candidate(client):
    token = _register(client, "criteria-candidate@example.com")
    client.put("/me/profile", json={"headline": "Backend Engineer"}, headers=_auth(token))
    return {"token": token}


def _criteria_payload():
    return {
        "competencies": [
            {"key": "technical_skills", "label": "Technical problem-solving", "weight": 60, "description": ""},
            {"key": "communication", "label": "Communication and teamwork", "weight": 40, "description": ""},
        ],
        "custom_questions": ["Tell me about a challenge you faced."],
        "pass_threshold": 6.0,
    }


class TestCriteriaCrud:
    def test_get_criteria_defaults_from_posting_required_skills(self, client, recruiter):
        posting = _make_posting(client, recruiter)
        resp = client.get(
            f"/orgs/{recruiter['org_id']}/postings/{posting['id']}/criteria",
            headers=_auth(recruiter["token"], recruiter["org_id"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert {c["label"] for c in body["competencies"]} == {
            "Python",
            "PostgreSQL",
            "Behavioral communication and collaboration",
        }
        assert sum(c["weight"] for c in body["competencies"]) == pytest.approx(100)
        assert body["interview_settings"]["role_level"] == "MID"
        assert body["updated_at"] == ""

    def test_put_criteria_persists_and_is_returned_on_get(self, client, recruiter):
        posting = _make_posting(client, recruiter)
        headers = _auth(recruiter["token"], recruiter["org_id"])

        put_resp = client.put(
            f"/orgs/{recruiter['org_id']}/postings/{posting['id']}/criteria",
            json=_criteria_payload(),
            headers=headers,
        )
        assert put_resp.status_code == 200, put_resp.text
        assert put_resp.json()["pass_threshold"] == 6.0
        assert put_resp.json()["updated_at"] != ""

        get_resp = client.get(
            f"/orgs/{recruiter['org_id']}/postings/{posting['id']}/criteria",
            headers=headers,
        )
        assert get_resp.json()["competencies"][0]["label"] == "Technical problem-solving"

    def test_criteria_are_tenant_scoped(self, client, recruiter):
        posting = _make_posting(client, recruiter)
        outsider_token = _register(client, "criteria-outsider@example.com")
        outsider_org = _create_org(client, outsider_token, slug="criteria-outsider-org")

        resp = client.get(
            f"/orgs/{recruiter['org_id']}/postings/{posting['id']}/criteria",
            headers=_auth(outsider_token, outsider_org),
        )
        assert resp.status_code == 404


class TestReportGeneration:
    def _link_evaluation_to_application(self, client, isolated_db, recruiter, candidate, posting):
        org_id = recruiter["org_id"]
        candidate_user_id = client.get("/auth/me", headers=_auth(candidate["token"])).json()["user_id"]
        profile = cdb.get_profile_by_user(candidate_user_id)
        application_id = hdb.create_application(org_id, posting["id"], candidate_user_id, profile["id"], {})
        evaluation_id = isolated_db.create_evaluation(
            "resume text", "Backend Engineer", "Cara Candidate", org_id, candidate_user_id
        )
        hdb.attach_evaluation(application_id, org_id, evaluation_id)
        return application_id, evaluation_id

    def _save_round_verdicts(self, isolated_db, evaluation_id):
        isolated_db.save_verdict(
            evaluation_id=evaluation_id, agent_type="screening", round_number=1,
            verdict_json={"decision": "PASS"}, verdict_text="Solid resume fit.",
            score=7.0, decision="PASS", confidence=0.8,
        )
        isolated_db.save_verdict(
            evaluation_id=evaluation_id, agent_type="technical", round_number=2,
            verdict_json={"decision": "PASS"}, verdict_text="Strong technical answers.",
            score=8.5, decision="PASS", confidence=0.9,
        )
        isolated_db.save_verdict(
            evaluation_id=evaluation_id, agent_type="behavioral", round_number=3,
            verdict_json={"decision": "PASS"}, verdict_text="Great teamwork stories.",
            score=7.5, decision="PASS", confidence=0.85,
        )

    def test_report_scores_competencies_by_keyword_matched_round(self, client, isolated_db, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        headers = _auth(recruiter["token"], org_id)
        client.put(f"/orgs/{org_id}/postings/{posting['id']}/criteria", json=_criteria_payload(), headers=headers)

        application_id, evaluation_id = self._link_evaluation_to_application(
            client, isolated_db, recruiter, candidate, posting
        )
        self._save_round_verdicts(isolated_db, evaluation_id)
        isolated_db.update_evaluation(evaluation_id, status="COMPLETE", current_round=5, final_decision="HIRE")

        report = ReportService().generate_from_evaluation(evaluation_id)
        assert report is not None
        assert report.recommendation == "HIRE"

        scores = {c["key"]: c for c in report.competency_scores}
        assert scores["technical_skills"]["score"] == 8.5
        assert scores["communication"]["score"] == 7.5
        assert report.overall_weighted_score == round((8.5 * 60 + 7.5 * 40) / 100, 2)

        resp = client.get(f"/orgs/{org_id}/applications/{application_id}/report", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["recommendation"] == "HIRE"

    def test_missing_report_returns_friendly_404(self, client, isolated_db, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        headers = _auth(recruiter["token"], org_id)
        application_id, _ = self._link_evaluation_to_application(client, isolated_db, recruiter, candidate, posting)

        resp = client.get(f"/orgs/{org_id}/applications/{application_id}/report", headers=headers)
        assert resp.status_code == 404

    def test_report_generation_is_a_noop_without_criteria(self, client, isolated_db, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        _, evaluation_id = self._link_evaluation_to_application(client, isolated_db, recruiter, candidate, posting)
        self._save_round_verdicts(isolated_db, evaluation_id)
        isolated_db.update_evaluation(evaluation_id, status="COMPLETE", current_round=5, final_decision="HIRE")

        assert ReportService().generate_from_evaluation(evaluation_id) is None

    def test_report_generation_is_a_noop_for_unlinked_evaluation(self, isolated_db):
        evaluation_id = isolated_db.create_evaluation("resume", "Backend Engineer", "Unlinked")
        assert ReportService().generate_from_evaluation(evaluation_id) is None


class TestFinalizeEvaluationHook:
    def test_finalize_evaluation_generates_report_as_a_side_effect(self, client, isolated_db, recruiter, candidate):
        from app.evaluation import service as finalization

        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        headers = _auth(recruiter["token"], org_id)
        client.put(f"/orgs/{org_id}/postings/{posting['id']}/criteria", json=_criteria_payload(), headers=headers)

        candidate_user_id = client.get("/auth/me", headers=_auth(candidate["token"])).json()["user_id"]
        profile = cdb.get_profile_by_user(candidate_user_id)
        application_id = hdb.create_application(org_id, posting["id"], candidate_user_id, profile["id"], {})
        evaluation_id = isolated_db.create_evaluation(
            "resume text", "Backend Engineer", "Cara Candidate", org_id, candidate_user_id
        )
        hdb.attach_evaluation(application_id, org_id, evaluation_id)

        TestReportGeneration()._save_round_verdicts(isolated_db, evaluation_id)
        isolated_db.update_evaluation(evaluation_id, current_round=4)

        async def fake_recommendation(_eid):
            return {
                "decision": "HIRE", "confidence": 0.9,
                "verdict": {"decision": "HIRE"}, "verdict_text": "Recommend hire.", "score": 8.0,
            }

        async def fake_committee(_eid):
            return {
                "decision": "HIRE", "confidence": 0.9,
                "verdict": {"decision": "HIRE"}, "verdict_text": "Committee agrees.",
            }

        result = asyncio.run(finalization.finalize_evaluation(evaluation_id, fake_recommendation, fake_committee))
        assert result["status"] == "COMPLETE"

        report = ReportService().get(application_id)
        assert report is not None
        assert report.recommendation == "HIRE"

    def test_finalize_evaluation_without_a_linked_application_still_completes(self, isolated_db):
        """The generic/anonymous evaluation flow (no application link) must
        keep working exactly as before — report generation is skipped, not
        an error."""
        from app.evaluation import service as finalization

        evaluation_id = isolated_db.create_evaluation("resume", "Backend Engineer", "Unlinked")
        isolated_db.save_verdict(
            evaluation_id=evaluation_id, agent_type="screening", round_number=1,
            verdict_json={"decision": "PASS"}, verdict_text="fit", score=7.0, decision="PASS", confidence=0.8,
        )
        isolated_db.update_evaluation(evaluation_id, current_round=4)

        async def fake_recommendation(_eid):
            return {"decision": "HIRE", "confidence": 0.9, "verdict": {"decision": "HIRE"}, "verdict_text": "ok", "score": 8.0}

        async def fake_committee(_eid):
            return {"decision": "HIRE", "confidence": 0.9, "verdict": {"decision": "HIRE"}, "verdict_text": "ok"}

        result = asyncio.run(finalization.finalize_evaluation(evaluation_id, fake_recommendation, fake_committee))
        assert result["status"] == "COMPLETE"
