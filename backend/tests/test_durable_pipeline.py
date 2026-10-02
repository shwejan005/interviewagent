"""Regression coverage for additive durable interview commands."""

import asyncio

from app.config import database as db
from app.evaluation import pipeline as durable_pipeline
from app.worker.job_worker import run_once
from tests.test_identity import _auth, _register


def test_v1_screening_admission_returns_202_and_worker_advances_pipeline(client, isolated_db, monkeypatch):
    async def fake_screening(evaluation_id, resume, role):
        return {
            "round": 1,
            "decision": "PASS",
            "verdict": {"decision": "PASS", "score": 8.0},
            "verdict_text": "pass",
            "score": 8.0,
            "confidence": 0.8,
        }

    async def fake_questions(evaluation_id, resume):
        return {"round": 2, "questions": "Explain the design."}

    monkeypatch.setattr(durable_pipeline, "run_screening", fake_screening)
    monkeypatch.setattr(durable_pipeline, "run_technical_questions", fake_questions)

    response = client.post(
        "/v1/evaluations",
        json={"resume": "synthetic resume", "role": "Backend Developer"},
        headers={"Idempotency-Key": "durable-test-1"},
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    job = isolated_db.get_job(payload["job_id"])
    assert job["status"] == "PENDING"

    assert asyncio.run(run_once("worker-test")) is True
    evaluation = isolated_db.get_evaluation(payload["evaluation_id"])
    assert evaluation["current_round"] == 2
    assert isolated_db.get_job(payload["job_id"])["status"] == "COMPLETED"


def test_v1_authenticated_evaluation_is_not_visible_to_another_user(client, isolated_db, monkeypatch):
    owner = _register(client, "durable-owner@example.com")
    other = _register(client, "durable-other@example.com")
    response = client.post(
        "/v1/evaluations",
        json={"resume": "synthetic resume", "role": "Backend Developer"},
        headers={**_auth(owner), "Idempotency-Key": "durable-owner-1"},
    )
    evaluation_id = response.json()["evaluation_id"]

    denied = client.get(f"/v1/evaluations/{evaluation_id}", headers=_auth(other))
    assert denied.status_code in (401, 404)
