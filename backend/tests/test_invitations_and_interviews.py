"""Regression coverage for organization invitations and interview scheduling."""

from urllib.parse import parse_qs, urlparse

from tests.test_hiring import _auth, _create_org, _make_posting, _register
from app.shared.rbac import SystemRole


def test_invitation_acceptance_adds_matching_user_to_org(client):
    owner = _register(client, "invite-owner@example.com")
    org_id = _create_org(client, owner, slug="invite-org")

    invite = client.post(
        f"/orgs/{org_id}/invitations",
        json={"email": "invited@example.com", "role": str(SystemRole.RECRUITER)},
        headers=_auth(owner, org_id),
    )
    assert invite.status_code == 201, invite.text
    token = parse_qs(urlparse(invite.json()["invite_url"]).query)["token"][0]

    invited = _register(client, "invited@example.com")
    accepted = client.post(
        "/auth/invitations/accept",
        json={"token": token},
        headers=_auth(invited),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["org_id"] == org_id

    actor = client.get("/auth/me", headers=_auth(invited, org_id)).json()
    assert actor["active_role"] == str(SystemRole.RECRUITER)


def test_invitation_cannot_be_accepted_by_a_different_email(client):
    owner = _register(client, "invite-owner-2@example.com")
    org_id = _create_org(client, owner, slug="invite-org-2")
    invite = client.post(
        f"/orgs/{org_id}/invitations",
        json={"email": "right@example.com", "role": str(SystemRole.RECRUITER)},
        headers=_auth(owner, org_id),
    )
    token = parse_qs(urlparse(invite.json()["invite_url"]).query)["token"][0]
    wrong_user = _register(client, "wrong@example.com")

    response = client.post(
        "/auth/invitations/accept",
        json={"token": token},
        headers=_auth(wrong_user),
    )
    assert response.status_code == 403


def test_scheduling_scopes_participants_and_candidate_agenda(client):
    recruiter = _register(client, "schedule-owner@example.com")
    org_id = _create_org(client, recruiter, slug="schedule-org")
    interviewer = _register(client, "schedule-interviewer@example.com")
    add_member = client.post(
        f"/orgs/{org_id}/members",
        json={"email": "schedule-interviewer@example.com", "role": str(SystemRole.INTERVIEWER)},
        headers=_auth(recruiter, org_id),
    )
    assert add_member.status_code == 201, add_member.text
    candidate = _register(client, "schedule-candidate@example.com")
    client.put("/me/profile", json={"headline": "Candidate"}, headers=_auth(candidate))
    posting = _make_posting(client, {"token": recruiter, "org_id": org_id})
    application_id = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate)
    ).json()["application_id"]
    interviewer_id = client.get("/auth/me", headers=_auth(interviewer)).json()["user_id"]

    scheduled = client.post(
        f"/orgs/{org_id}/applications/{application_id}/interviews",
        json={
            "title": "Technical interview",
            "scheduled_start": "2026-10-01T10:00:00+00:00",
            "scheduled_end": "2026-10-01T11:00:00+00:00",
            "timezone": "Asia/Kolkata",
            "meeting_url": "https://meet.example.com/audit",
            "interviewer_user_ids": [interviewer_id],
        },
        headers=_auth(recruiter, org_id),
    )
    assert scheduled.status_code == 201, scheduled.text
    interview = scheduled.json()
    assert {p["participant_role"] for p in interview["participants"]} == {"CANDIDATE", "INTERVIEWER"}

    candidate_agenda = client.get("/me/interviews", headers=_auth(candidate)).json()
    assert len(candidate_agenda["interviews"]) == 1
    assert candidate_agenda["interviews"][0]["posting_title"] == posting["title"]

    duplicate = client.post(
        f"/orgs/{org_id}/applications/{application_id}/interviews",
        json={
            "scheduled_start": "2026-10-02T10:00:00+00:00",
            "scheduled_end": "2026-10-02T11:00:00+00:00",
            "interviewer_user_ids": [interviewer_id],
        },
        headers=_auth(recruiter, org_id),
    )
    assert duplicate.status_code == 409

    cancelled = client.post(
        f"/orgs/{org_id}/interviews/{interview['id']}/cancel",
        headers=_auth(recruiter, org_id),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
