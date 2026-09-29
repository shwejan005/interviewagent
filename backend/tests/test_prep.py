"""Regression coverage for the safe, text-first preparation foundation."""

from tests.test_identity import _auth, _register


def test_prep_catalog_and_roadmap_are_user_scoped(client):
    token = _register(client, "prep-candidate@example.com")
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
