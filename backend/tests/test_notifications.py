"""Regression tests for the persisted, user-scoped notification inbox."""

from app.config import database as db
from app.shared.notification_repository import create_notification
from tests.test_identity import _auth, _register


def test_notifications_are_private_and_read_state_is_user_scoped(client):
    owner_token = _register(client, "inbox-owner@example.com")
    other_token = _register(client, "inbox-other@example.com")
    owner_id = db.get_user_by_email("inbox-owner@example.com")["id"]

    notification_id = create_notification(
        owner_id,
        "AI_INTERVIEW_READY",
        "Interview step ready",
        "Review the next step.",
        href="/ai-interview/15",
        dedupe_key="inbox-test:application:15",
    )

    owner_inbox = client.get("/me/notifications", headers=_auth(owner_token))
    other_inbox = client.get("/me/notifications", headers=_auth(other_token))
    assert owner_inbox.status_code == 200
    assert owner_inbox.json()["unread_count"] == 1
    assert owner_inbox.json()["notifications"][0]["id"] == notification_id
    assert other_inbox.json()["notifications"] == []
    assert other_inbox.json()["unread_count"] == 0

    assert client.post(
        f"/me/notifications/{notification_id}/read", headers=_auth(other_token)
    ).status_code == 404
    assert client.post(
        f"/me/notifications/{notification_id}/read", headers=_auth(owner_token)
    ).status_code == 200
    assert client.get("/me/notifications", headers=_auth(owner_token)).json()["unread_count"] == 0


def test_notification_creation_is_idempotent_and_rejects_external_hrefs(client):
    token = _register(client, "inbox-dedupe@example.com")
    user_id = db.get_user_by_email("inbox-dedupe@example.com")["id"]
    first_id = create_notification(
        user_id,
        "APPLICATION_UPDATE",
        "Application update",
        href="https://attacker.example",
        dedupe_key="same-event",
    )
    second_id = create_notification(
        user_id,
        "APPLICATION_UPDATE",
        "Application update",
        href="/jobs",
        dedupe_key="same-event",
    )
    assert first_id == second_id

    inbox = client.get("/me/notifications", headers=_auth(token)).json()
    assert len(inbox["notifications"]) == 1
    assert inbox["notifications"][0]["href"] == "/notifications"


def test_mark_all_only_updates_the_current_user(client):
    token = _register(client, "inbox-all@example.com")
    user_id = db.get_user_by_email("inbox-all@example.com")["id"]
    for index in range(3):
        create_notification(user_id, "TEST", f"Test {index}", dedupe_key=f"all:{index}")

    response = client.post("/me/notifications/read-all", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["marked_read"] == 3
    assert client.get("/me/notifications", headers=_auth(token)).json()["unread_count"] == 0
