"""
Route-level regression tests for the full interview pipeline.

These tests exercise the real FastAPI app (routes.py + database.py) through
TestClient, but never call a live LLM: every agent-calling function
(run_screening, run_technical_evaluation, ...) is monkeypatched on the
`routes` module with a deterministic fake. This keeps the suite fast, free,
and reproducible, while still proving the *orchestration* logic in
routes.py — status transitions, idempotency, authorization-shaped guards,
and PII projection — is correct.

For a slower, opt-in suite that exercises the real agents against a live
LLM endpoint, see docs/TESTING.md ("Live agent smoke test").
"""

from app.evaluation import controller as routes
from app.evaluation.runner import AgentOutputError


SENSITIVE_MARKER = "UNIQUE_RESUME_MARKER_DO_NOT_LEAK_9f31"


def _screening(decision="PASS", score=9.0):
    async def _fake(evaluation_id, resume, role):
        return {
            "round": 1,
            "decision": decision,
            "verdict": {
                "decision": decision, "score": score, "strengths": ["x"], "weaknesses": [],
                "reasoning": "r", "candidate_summary": "s", "skills_extracted": [],
                "experience_years": 5, "recommended_questions": ["q1"], "confidence": 0.9,
            },
            "verdict_text": "raw-screening",
            "score": score,
            "confidence": 0.9,
        }
    return _fake


async def _technical_questions(evaluation_id, resume):
    return {"round": 2, "questions": "1. Explain idempotency.\n2. Explain CAP theorem."}


def _technical_eval(decision="PASS", score=9.0):
    async def _fake(evaluation_id, resume, questions, answer):
        return {
            "round": 2,
            "decision": decision,
            "verdict": {
                "decision": decision, "score": score, "question_evaluations": [],
                "strengths": [], "weaknesses": [], "reasoning": "r",
                "coding_quality": None, "confidence": 0.9,
            },
            "verdict_text": "raw-technical",
            "score": score,
            "confidence": 0.9,
        }
    return _fake


async def _behavioral_question(evaluation_id, resume):
    return {"round": 3, "question": "Tell me about a time you owned an incident."}


def _behavioral_eval(decision="PASS", score=9.0):
    async def _fake(evaluation_id, resume, question, answer):
        return {
            "round": 3,
            "decision": decision,
            "verdict": {
                "decision": decision, "score": score, "star_evaluation": "good",
                "leadership": 8, "communication": 8, "teamwork": 8, "ownership": 8,
                "conflict_handling": 8, "culture_fit": 8, "strengths": [], "weaknesses": [],
                "reasoning": "r", "confidence": 0.9,
            },
            "verdict_text": "raw-behavioral",
            "score": score,
            "confidence": 0.9,
        }
    return _fake


async def _hiring_recommendation(evaluation_id):
    return {
        "round": 4,
        "decision": "HIRE",
        "verdict": {
            "decision": "HIRE", "score": 8.5, "detailed_recommendation": "r",
            "risks": [], "positives": [], "suggested_role": "Backend Developer",
            "growth_areas": [], "confidence": 0.9,
        },
        "verdict_text": "raw-recommendation",
        "score": 8.5,
        "confidence": 0.9,
    }


async def _hiring_committee(evaluation_id):
    return {
        "decision": "HIRE",
        "verdict": {
            "decision": "HIRE", "confidence": 0.93, "executive_summary": "Strong hire.",
            "round_summaries": [], "overall_assessment": "a", "recommendation": "Hire.",
            "hiring_risks": [], "strengths_summary": [], "weaknesses_summary": [],
        },
        "verdict_text": "raw-committee",
        "confidence": 0.93,
    }


def _patch_happy_path(monkeypatch):
    monkeypatch.setattr(routes, "run_screening", _screening())
    monkeypatch.setattr(routes, "run_technical_questions", _technical_questions)
    monkeypatch.setattr(routes, "run_technical_evaluation", _technical_eval())
    monkeypatch.setattr(routes, "run_behavioral_question", _behavioral_question)
    monkeypatch.setattr(routes, "run_behavioral_evaluation", _behavioral_eval())
    monkeypatch.setattr(routes, "run_hiring_recommendation", _hiring_recommendation)
    monkeypatch.setattr(routes, "run_hiring_committee", _hiring_committee)


class TestHappyPath:
    def test_full_pipeline_reaches_hire(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)

        start = client.post(
            "/start",
            json={"resume": f"Resume {SENSITIVE_MARKER}", "role": "Backend Developer", "candidate_name": "Jane"},
        )
        assert start.status_code == 200
        body = start.json()
        assert body["status"] == "IN_PROGRESS"
        eval_id = body["evaluation_id"]

        r2 = client.post(f"/round/2/answer?evaluation_id={eval_id}", json={"answer": "answer 2"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "IN_PROGRESS"

        r3 = client.post(f"/round/3/answer?evaluation_id={eval_id}", json={"answer": "answer 3"})
        assert r3.status_code == 200
        assert r3.json()["status"] == "COMPLETE"

        final_1 = client.get(f"/final-decision?evaluation_id={eval_id}")
        assert final_1.status_code == 200
        assert final_1.json()["decision"] == "HIRE"
        assert final_1.json()["overall_score"] == round((9.0 + 9.0 + 9.0) / 3, 1)

        # Idempotent replay: calling again must return the identical persisted
        # result rather than re-invoking (and re-billing) the agents.
        final_2 = client.get(f"/final-decision?evaluation_id={eval_id}")
        assert final_2.status_code == 200
        assert final_2.json()["decision"] == final_1.json()["decision"]
        assert final_2.json()["overall_score"] == final_1.json()["overall_score"]

    def test_completed_evaluation_rejects_further_answers(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)
        eval_id = client.post(
            "/start", json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"}
        ).json()["evaluation_id"]
        client.post(f"/round/2/answer?evaluation_id={eval_id}", json={"answer": "a"})
        client.post(f"/round/3/answer?evaluation_id={eval_id}", json={"answer": "a"})
        client.get(f"/final-decision?evaluation_id={eval_id}")

        resp = client.post(f"/round/2/answer?evaluation_id={eval_id}", json={"answer": "late"})
        assert resp.status_code == 400


class TestRejectionShortCircuit:
    def test_screening_fail_rejects_without_running_later_agents(self, client, monkeypatch):
        monkeypatch.setattr(routes, "run_screening", _screening(decision="FAIL", score=2.0))

        def _boom(*args, **kwargs):
            raise AssertionError("later-stage agent must not run after an early rejection")

        monkeypatch.setattr(routes, "run_technical_questions", _boom)
        monkeypatch.setattr(routes, "run_hiring_recommendation", _boom)
        monkeypatch.setattr(routes, "run_hiring_committee", _boom)

        start = client.post(
            "/start", json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"}
        )
        body = start.json()
        assert body["status"] == "REJECTED"
        eval_id = body["evaluation_id"]

        final = client.get(f"/final-decision?evaluation_id={eval_id}")
        assert final.status_code == 200
        assert final.json()["decision"] == "REJECT"
        assert final.json()["status"] == "REJECTED"

    def test_technical_fail_rejects_before_behavioral_round(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)
        monkeypatch.setattr(routes, "run_technical_evaluation", _technical_eval(decision="FAIL", score=1.0))

        eval_id = client.post(
            "/start", json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"}
        ).json()["evaluation_id"]

        r2 = client.post(f"/round/2/answer?evaluation_id={eval_id}", json={"answer": "weak answer"})
        assert r2.json()["status"] == "REJECTED"

        r3 = client.post(f"/round/3/answer?evaluation_id={eval_id}", json={"answer": "a"})
        assert r3.status_code == 400


class TestInvalidAgentOutputNeverBecomesADecision:
    def test_screening_invalid_output_returns_502_and_records_invalid_output(self, client, monkeypatch):
        async def _raise(evaluation_id, resume, role):
            raise AgentOutputError("not valid json", "not valid json")

        monkeypatch.setattr(routes, "run_screening", _raise)

        resp = client.post(
            "/start", json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"}
        )
        assert resp.status_code == 502

        # The evaluation row was created before the agent ran; find it via the
        # list endpoint and confirm the recorded decision is a distinct
        # execution-failure marker, never PASS/FAIL/BORDERLINE.
        listing = client.get("/evaluations").json()
        assert listing["total"] == 1
        eval_id = listing["evaluations"][0]["id"]

        detail = client.get(f"/evaluations/{eval_id}").json()
        assert len(detail["verdicts"]) == 1
        assert detail["verdicts"][0]["decision"] == "INVALID_OUTPUT"


class TestGuardsAndErrorHandling:
    def test_unknown_evaluation_returns_404(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)
        resp = client.post("/round/2/answer?evaluation_id=999999", json={"answer": "a"})
        assert resp.status_code == 404

    def test_submitting_wrong_round_returns_409(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)
        eval_id = client.post(
            "/start", json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"}
        ).json()["evaluation_id"]
        # Evaluation is at round 2; submitting round 3 first must be rejected.
        resp = client.post(f"/round/3/answer?evaluation_id={eval_id}", json={"answer": "a"})
        assert resp.status_code == 409

    def test_duplicate_round_submission_returns_409(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)
        eval_id = client.post(
            "/start", json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"}
        ).json()["evaluation_id"]
        first = client.post(f"/round/2/answer?evaluation_id={eval_id}", json={"answer": "a"})
        assert first.status_code == 200

        # Manually reset current_round to simulate a duplicate/replayed request
        # against a round whose canonical verdict already exists.
        from app.config import database as db
        db.update_evaluation(eval_id, current_round=2, status="IN_PROGRESS")

        second = client.post(f"/round/2/answer?evaluation_id={eval_id}", json={"answer": "a"})
        assert second.status_code == 409

    def test_empty_resume_returns_400(self, client):
        resp = client.post(
            "/start", json={"resume": "   ", "role": "Backend Developer", "candidate_name": "Jane"}
        )
        assert resp.status_code == 400

    def test_invalid_role_returns_400(self, client):
        resp = client.post(
            "/start", json={"resume": "r", "role": "Not A Real Role", "candidate_name": "Jane"}
        )
        assert resp.status_code == 400

    def test_final_decision_before_round_3_returns_400(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)
        eval_id = client.post(
            "/start", json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"}
        ).json()["evaluation_id"]
        resp = client.get(f"/final-decision?evaluation_id={eval_id}")
        assert resp.status_code == 400


class TestPiiSafety:
    def test_list_and_detail_never_include_resume_text(self, client, monkeypatch):
        _patch_happy_path(monkeypatch)
        client.post(
            "/start",
            json={"resume": f"Resume body {SENSITIVE_MARKER}", "role": "Backend Developer", "candidate_name": "Jane"},
        )

        listing = client.get("/evaluations")
        assert SENSITIVE_MARKER not in listing.text

        eval_id = listing.json()["evaluations"][0]["id"]
        detail = client.get(f"/evaluations/{eval_id}")
        assert SENSITIVE_MARKER not in detail.text

        report = client.get(f"/evaluations/{eval_id}/report")
        assert SENSITIVE_MARKER not in report.text
