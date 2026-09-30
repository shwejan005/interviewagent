"""Regression coverage for the safe, text-first preparation foundation."""

from tests.test_identity import _auth, _register


def test_prep_catalog_and_roadmap_are_user_scoped(client):
    token = _register(client, "prep-candidate@example.com")
    catalog = client.get("/prep/catalog", headers=_auth(token))
    assert catalog.status_code == 200
    assert any(topic["slug"] == "arrays" for topic in catalog.json()["topics"])
    assert any(problem["slug"] == "two-sum" for problem in catalog.json()["problems"])
    assert all(topic["slug"] != "system-design" for topic in catalog.json()["topics"])
    two_sum = next(problem for problem in catalog.json()["problems"] if problem["slug"] == "two-sum")
    assert two_sum["constraints"]
    assert two_sum["test_cases"]
    assert "python" in two_sum["available_languages"]

    topics = client.get("/prep/topics", headers=_auth(token))
    assert topics.status_code == 200
    assert any(topic["slug"] == "arrays" for topic in topics.json()["topics"])

    roadmap = client.post(
        "/prep/roadmaps",
        json={"target_role": "Backend Developer", "topic_slugs": ["arrays", "hashing"]},
        headers=_auth(token),
    )
    assert roadmap.status_code == 201, roadmap.text
    body = roadmap.json()
    assert [node["topic_slug"] for node in body["nodes"]] == ["arrays", "hashing"]

    other = _register(client, "prep-other@example.com")
    assert client.get(f"/prep/roadmaps/{body['id']}", headers=_auth(other)).status_code == 404


def test_prep_progress_awards_xp_without_claiming_verified_skill(client):
    token = _register(client, "prep-progress@example.com")
    roadmap = client.post(
        "/prep/roadmaps",
        json={"target_role": "AI Engineer", "topic_slugs": ["arrays"]},
        headers=_auth(token),
    ).json()
    node_id = roadmap["nodes"][0]["id"]

    completed = client.post(
        f"/prep/roadmaps/{roadmap['id']}/nodes/{node_id}/complete",
        headers=_auth(token),
    )
    assert completed.status_code == 200
    stats = client.get("/prep/me/stats", headers=_auth(token)).json()
    assert stats["xp"] == 10

    problem = client.get("/prep/problems?topic=arrays", headers=_auth(token)).json()["problems"][0]
    submission = client.post(
        f"/prep/problems/{problem['id']}/submissions",
        json={"answer_text": "Use a hash map and explain the invariant."},
        headers=_auth(token),
    )
    assert submission.status_code == 201
    assert submission.json()["verified"] is False
    assert "was executed" in submission.json()["note"]


def test_code_execution_fails_closed_without_a_configured_sandbox(client, monkeypatch):
    monkeypatch.delenv("JUDGE0_URL", raising=False)
    token = _register(client, "prep-execution@example.com")

    response = client.post(
        "/prep/execute",
        json={"language": "python", "source_code": "print('hello')"},
        headers=_auth(token),
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_problem_execution_uses_database_cases_and_records_history(client, monkeypatch):
    from app.prep import controller as prep_routes
    code_runner = prep_routes.code_runner

    token = _register(client, "prep-code-history@example.com")
    problem = next(
        problem for problem in client.get("/prep/catalog", headers=_auth(token)).json()["problems"]
        if problem["slug"] == "two-sum"
    )
    captured = {}

    def fake_execute_problem(**kwargs):
        captured.update(kwargs)
        return {
            "language": "python",
            "status": "Accepted",
            "passed": True,
            "passed_tests": 1,
            "total_tests": 1,
            "tests": [{"id": problem["test_cases"][0]["id"], "title": "Basic pair", "passed": True}],
            "stdout": "[0,1]\n",
            "stderr": "",
            "compile_output": "",
            "time": "0.01",
            "memory": 3000,
        }

    monkeypatch.setattr(code_runner, "execute_problem", fake_execute_problem)
    response = client.post(
        "/prep/execute",
        json={
            "problem_id": problem["id"],
            "test_case_id": problem["test_cases"][0]["id"],
            "language": "python",
            "source_code": "class Solution: pass",
            "mode": "run",
        },
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert captured["test_cases"][0]["id"] == problem["test_cases"][0]["id"]
    history = client.get(f"/prep/problems/{problem['id']}/submissions", headers=_auth(token))
    assert history.status_code == 200
    assert history.json()["submissions"][0]["status"] == "Accepted"
    dashboard = client.get("/prep/me/dashboard", headers=_auth(token))
    assert dashboard.status_code == 200
    assert dashboard.json()["solved_problems"] == 1


def test_goal_drives_generated_roadmap_and_problem_nodes(client, monkeypatch):
    from app.prep import controller as prep_routes

    token = _register(client, "prep-roadmap-goal@example.com")
    goal = client.put(
        "/prep/goals",
        json={
            "target_role": "Backend Engineer",
            "daily_minutes": 30,
            "days_per_week": 4,
            "current_level": "BEGINNER",
            "focus_topics": ["arrays"],
        },
        headers=_auth(token),
    )
    assert goal.status_code == 200, goal.text

    monkeypatch.setattr(
        prep_routes.prep_ai,
        "generate_roadmap_plan",
        lambda goal, topics, problems: {
            "title": "Backend Engineer foundations",
            "summary": "A compact arrays-first plan.",
            "problem_slugs": ["two-sum", "deduplicate-events"],
            "weekly_focus": ["Hash maps", "Complexity explanations"],
            "daily_schedule": [],
            "generated_by": "llm",
        },
    )
    generated = client.post("/prep/roadmaps/generate", headers=_auth(token))
    assert generated.status_code == 201, generated.text
    roadmap = generated.json()["roadmap"]
    assert roadmap["generated_by"] == "llm"
    assert [node["item_type"] for node in roadmap["nodes"]] == ["PROBLEM", "PROBLEM"]
    assert all(node["problem_id"] for node in roadmap["nodes"])


def test_reviewer_packet_records_attributed_action(client, isolated_db):
    token = _register(client, "reviewer-candidate@example.com")
    user_id = client.get("/auth/me", headers=_auth(token)).json()["user_id"]
    evaluation_id = isolated_db.create_evaluation(
        resume_text="Synthetic resume",
        role="Backend Engineer",
        candidate_name="Synthetic Candidate",
        owner_user_id=user_id,
    )

    packet = client.get(f"/review/evaluations/{evaluation_id}", headers=_auth(token))
    assert packet.status_code == 200, packet.text
    assert packet.json()["rubric_version"] == "backend-v1"

    action = client.post(
        f"/review/evaluations/{evaluation_id}/actions",
        json={"action": "ESCALATE", "note": "Need human confirmation of the evidence."},
        headers=_auth(token),
    )
    assert action.status_code == 200, action.text
    assert action.json()["review_state"] == "ESCALATE"
