"""Data export and deletion regression coverage."""

from tests.test_identity import _auth, _create_org, _register


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
