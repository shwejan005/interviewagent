"""Regression coverage for organization invitations and interview scheduling."""

import base64
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from app.hiring import repository as hdb
from app.meetings.controller import _ice_server_configuration
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


def test_scheduling_scopes_participants_and_candidate_agenda(client, monkeypatch):
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
    client.put(
        "/me/profile/skills",
        json={"skills": [{"skill": "Python", "years": 1}]},
        headers=_auth(candidate),
    )
    posting = _make_posting(client, {"token": recruiter, "org_id": org_id})
    application_id = client.post(
        f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate)
    ).json()["application_id"]
    interviewer_id = client.get("/auth/me", headers=_auth(interviewer)).json()["user_id"]

    team = client.get(f"/orgs/{org_id}/team", headers=_auth(recruiter, org_id))
    assert team.status_code == 200, team.text
    assert {member["user_id"] for member in team.json()["members"]} >= {interviewer_id}
    profile_update = client.put(
        f"/orgs/{org_id}/members/{interviewer_id}/interview-profile",
        json={
            "job_title": "Senior Backend Engineer",
            "interview_skills": ["Python", "System design", "Python"],
            "timezone": "Asia/Kolkata",
            "weekly_capacity": 4,
            "available_for_interviews": True,
        },
        headers=_auth(interviewer, org_id),
    )
    assert profile_update.status_code == 200, profile_update.text
    saved_member = profile_update.json()["member"]
    assert saved_member["job_title"] == "Senior Backend Engineer"
    assert saved_member["interview_skills"] == ["Python", "System design"]
    assert saved_member["weekly_capacity"] == 4

    schedule_payload = {
        "title": "Technical interview",
        "scheduled_start": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "scheduled_end": (datetime.now(timezone.utc) + timedelta(minutes=65)).isoformat(),
        "timezone": "Asia/Kolkata",
        "meeting_url": "https://meet.example.com/audit",
        "interviewer_user_ids": [interviewer_id],
    }
    client.put(
        f"/orgs/{org_id}/members/{interviewer_id}/interview-profile",
        json={"job_title": "Senior Backend Engineer", "interview_skills": ["Python"], "weekly_capacity": 0, "available_for_interviews": True},
        headers=_auth(interviewer, org_id),
    )
    capacity_blocked = client.post(
        f"/orgs/{org_id}/applications/{application_id}/interviews",
        json=schedule_payload,
        headers=_auth(recruiter, org_id),
    )
    assert capacity_blocked.status_code == 409
    client.put(
        f"/orgs/{org_id}/members/{interviewer_id}/interview-profile",
        json={"job_title": "Senior Backend Engineer", "interview_skills": ["Python"], "weekly_capacity": 4, "available_for_interviews": True},
        headers=_auth(interviewer, org_id),
    )
    scheduled = client.post(
        f"/orgs/{org_id}/applications/{application_id}/interviews",
        json=schedule_payload,
        headers=_auth(recruiter, org_id),
    )
    assert scheduled.status_code == 201, scheduled.text
    interview = scheduled.json()
    assert {p["participant_role"] for p in interview["participants"]} == {"CANDIDATE", "INTERVIEWER"}

    candidate_agenda = client.get("/me/interviews", headers=_auth(candidate)).json()
    agenda_items = candidate_agenda["interviews"]
    human_agenda = next(item for item in agenda_items if item["kind"] == "HUMAN")
    assert human_agenda["posting_title"] == posting["title"]
    assert human_agenda["can_join"] is True
    assert human_agenda["join_href"] == "https://meet.example.com/audit"
    assert any(item.get("kind") == "AI" and item["status"] == "SCREENING_QUEUED" for item in agenda_items)

    turn_secret = "synthetic-test-turn-secret"
    monkeypatch.setenv("TURN_URLS", "turn:turn.example.invalid:3478?transport=udp,turns:turn.example.invalid:5349")
    monkeypatch.setenv("TURN_SHARED_SECRET", turn_secret)
    candidate_ticket = client.post(f"/me/interviews/{interview['id']}/join", headers=_auth(candidate))
    assert candidate_ticket.status_code == 200, candidate_ticket.text
    candidate_room_ticket = candidate_ticket.json()["ticket"]
    ice_servers = candidate_ticket.json()["ice_servers"]
    assert ice_servers[0]["urls"] == ["stun:stun.l.google.com:19302"]
    turn_server = ice_servers[1]
    assert turn_server["urls"] == ["turn:turn.example.invalid:3478?transport=udp", "turns:turn.example.invalid:5349"]
    assert turn_secret not in str(turn_server)
    username = turn_server["username"]
    expires_at = int(username.split(":", 1)[0])
    assert int(time.time()) + 9 * 60 <= expires_at <= int(time.time()) + 10 * 60
    expected_credential = base64.b64encode(
        hmac.new(turn_secret.encode(), username.encode(), hashlib.sha1).digest()
    ).decode("ascii")
    assert turn_server["credential"] == expected_credential
    interviewer_ticket = client.post(f"/me/interviews/{interview['id']}/join", headers=_auth(interviewer))
    assert interviewer_ticket.status_code == 200, interviewer_ticket.text
    outsider = _register(client, "schedule-outsider@example.com")
    assert client.post(f"/me/interviews/{interview['id']}/join", headers=_auth(outsider)).status_code == 404

    with client.websocket_connect(
        f"/ws/interviews/{interview['id']}",
        subprotocols=["evalia-meeting-v1", candidate_room_ticket],
    ) as candidate_socket:
        candidate_state = candidate_socket.receive_json()
        assert candidate_state["type"] == "room_state"
        assert candidate_state["participants"] == []
        with client.websocket_connect(
            f"/ws/interviews/{interview['id']}",
            subprotocols=["evalia-meeting-v1", interviewer_ticket.json()["ticket"]],
        ) as interviewer_socket:
            interviewer_state = interviewer_socket.receive_json()
            assert interviewer_state["type"] == "room_state"
            assert interviewer_state["participants"][0]["user_id"] == candidate_state["self_user_id"]
            peer_joined = candidate_socket.receive_json()
            assert peer_joined["type"] == "peer_joined"
            interviewer_id = client.get("/auth/me", headers=_auth(interviewer)).json()["user_id"]
            candidate_socket.send_json({"type": "offer", "to_user_id": interviewer_id, "sdp": {"type": "offer", "sdp": "candidate-sdp"}})
            relayed_offer = interviewer_socket.receive_json()
            assert relayed_offer["type"] == "offer"
            assert relayed_offer["from_user_id"] == candidate_state["self_user_id"]
            interviewer_socket.send_json({"type": "answer", "to_user_id": candidate_state["self_user_id"], "sdp": {"type": "answer", "sdp": "interviewer-sdp"}})
            relayed_answer = candidate_socket.receive_json()
            assert relayed_answer["type"] == "answer"
            assert relayed_answer["from_user_id"] == interviewer_id

    duplicate = client.post(
        f"/orgs/{org_id}/applications/{application_id}/interviews",
        json={
            "scheduled_start": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "scheduled_end": (datetime.now(timezone.utc) + timedelta(days=1, hours=1)).isoformat(),
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


def test_turn_urls_require_a_server_side_shared_secret():
    with pytest.raises(HTTPException) as error:
        _ice_server_configuration(
            7,
            12,
            now=1_800_000_000,
            turn_urls="turn:turn.example.invalid:3478",
            shared_secret="",
        )
    assert error.value.status_code == 503


def test_human_panel_scorecards_are_independent_and_return_to_recruiter_review(client, isolated_db):
    from app.interview_criteria.repository import ReportRepository

    recruiter = _register(client, "scorecard-owner@example.com")
    org_id = _create_org(client, recruiter, slug="scorecard-org")
    headers = _auth(recruiter, org_id)
    candidate = _register(client, "scorecard-candidate@example.com")
    client.put("/me/profile", json={"headline": "Candidate"}, headers=_auth(candidate))
    client.put("/me/profile/skills", json={"skills": [{"skill": "Python", "years": 5}]}, headers=_auth(candidate))
    interviewer_tokens = [_register(client, f"scorecard-interviewer-{i}@example.com") for i in (1, 2)]
    interviewer_ids = []
    for index, token in enumerate(interviewer_tokens, start=1):
        response = client.post(
            f"/orgs/{org_id}/members",
            json={"email": f"scorecard-interviewer-{index}@example.com", "role": str(SystemRole.INTERVIEWER)},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        interviewer_ids.append(client.get("/auth/me", headers=_auth(token)).json()["user_id"])
    posting = _make_posting(client, {"token": recruiter, "org_id": org_id})
    application_id = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate)).json()["application_id"]
    candidate_user_id = client.get("/auth/me", headers=_auth(candidate)).json()["user_id"]
    evaluation_id = isolated_db.create_evaluation(
        "Synthetic candidate resume",
        posting["title"],
        "Scorecard Candidate",
        org_id,
        candidate_user_id,
    )
    ReportRepository().upsert(
        application_id=application_id,
        evaluation_id=evaluation_id,
        posting_id=posting["id"],
        org_id=org_id,
        competency_scores=[],
        overall_weighted_score=None,
        recommendation="HUMAN_REVIEW_REQUIRED",
        rubric_version="posting-v1",
        interview_details={"fit_nudge": {"band": "MIXED", "suggested_action": "HOLD"}},
    )
    hdb.transition_application(application_id, org_id, "SCREENING", None, "Scorecard test setup.", True)
    hdb.transition_application(application_id, org_id, "PENDING_REVIEW", None, "Scorecard test setup.", True)
    hdb.transition_application(application_id, org_id, "TECHNICAL", None, "Promoted to human technical round.", False)
    scheduled = client.post(
        f"/orgs/{org_id}/applications/{application_id}/interviews",
        json={
            "title": "Technical interview",
            "scheduled_start": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "scheduled_end": (datetime.now(timezone.utc) + timedelta(minutes=65)).isoformat(),
            "timezone": "UTC",
            "interviewer_user_ids": interviewer_ids,
        },
        headers=headers,
    )
    assert scheduled.status_code == 201, scheduled.text
    interview_id = scheduled.json()["id"]
    with pytest.raises(hdb.InvalidTransitionError, match="Only an application awaiting review"):
        hdb.record_application_offer(application_id, org_id, 1, "Synthetic premature offer check.")
    scorecard_one = {
        "ratings": [{"key": key, "label": label, "score": 4, "evidence": f"Example evidence for {label}."} for key, label in (
            ("role_skills", "Role skills"), ("problem_solving", "Problem solving"),
        )],
        "recommendation": "ADVANCE",
        "notes": "Strong evidence in the areas discussed.",
    }
    missing_evidence = {**scorecard_one, "ratings": [{**rating, "evidence": ""} for rating in scorecard_one["ratings"]]}
    invalid_scorecard = client.post(
        f"/orgs/{org_id}/interviews/{interview_id}/scorecard",
        json=missing_evidence,
        headers=_auth(interviewer_tokens[0], org_id),
    )
    assert invalid_scorecard.status_code == 422

    first = client.post(
        f"/orgs/{org_id}/interviews/{interview_id}/scorecard",
        json=scorecard_one,
        headers=_auth(interviewer_tokens[0], org_id),
    )
    assert first.status_code == 200, first.text
    assert first.json()["complete"] is False
    hidden_for_peer = client.get(
        f"/orgs/{org_id}/interviews/{interview_id}/scorecards",
        headers=_auth(interviewer_tokens[0], org_id),
    ).json()
    assert hidden_for_peer["hidden_until_complete"] is True
    assert len(hidden_for_peer["scorecards"]) == 1
    hidden_for_recruiter = client.get(
        f"/orgs/{org_id}/interviews/{interview_id}/scorecards", headers=headers
    ).json()
    assert hidden_for_recruiter["scorecards"] == []

    scorecard_two = {**scorecard_one, "recommendation": "HOLD", "notes": "One area needs another probe."}
    second = client.post(
        f"/orgs/{org_id}/interviews/{interview_id}/scorecard",
        json=scorecard_two,
        headers=_auth(interviewer_tokens[1], org_id),
    )
    assert second.status_code == 200, second.text
    assert second.json()["complete"] is True
    assert hdb.get_application(application_id, org_id)["current_stage"] == "PENDING_REVIEW"
    complete_for_recruiter = client.get(
        f"/orgs/{org_id}/interviews/{interview_id}/scorecards", headers=headers
    ).json()
    assert complete_for_recruiter["hidden_until_complete"] is False
    assert len(complete_for_recruiter["scorecards"]) == 2
    assert {card["recommendation"] for card in complete_for_recruiter["scorecards"]} == {"ADVANCE", "HOLD"}
    offer_decision = client.post(
        f"/orgs/{org_id}/applications/{application_id}/decision",
        json={
            "action": "PROMOTE",
            "target_stage": "OFFER",
            "reason": "The completed panel supports an offer-stage review despite one hold recommendation.",
        },
        headers=headers,
    )
    assert offer_decision.status_code == 200, offer_decision.text
    assert offer_decision.json()["to_stage"] == "OFFER"
