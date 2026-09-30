"""Regression tests for audit findings fixed in the platform hardening pass."""

import pytest
from app.config import database as db
from app.hiring import repository as hdb
from app.candidate import service as matching
from tests.test_hiring import _make_posting
from tests.test_identity import _auth, _create_org, _register


@pytest.fixture
def recruiter(client):
    token = _register(client, "hardening-recruiter@example.com")
    return {"token": token, "org_id": _create_org(client, token, slug="hardening-org")}


@pytest.fixture
def candidate(client):
    token = _register(client, "hardening-candidate@example.com")
    client.put(
        "/me/profile",
        json={"headline": "Backend Engineer", "is_discoverable": True},
        headers=_auth(token),
    )
    return {"token": token}


def test_tenant_owned_legacy_evaluation_requires_owner_or_org_scope(client, isolated_db):
    owner = _register(client, "evaluation-owner@example.com")
    other = _register(client, "evaluation-other@example.com")
    org_id = _create_org(client, owner, slug="evaluation-org")
    owner_id = client.get("/auth/me", headers=_auth(owner)).json()["user_id"]
    evaluation_id = isolated_db.create_evaluation(
        "private resume", "Backend Developer", "Candidate", org_id, owner_id
    )

    assert client.get(f"/evaluations/{evaluation_id}").status_code == 401
    assert client.get(
        f"/evaluations/{evaluation_id}", headers=_auth(other, org_id)
    ).status_code in (401, 404)
    assert client.get(
        f"/evaluations/{evaluation_id}", headers=_auth(owner, org_id)
    ).status_code == 200


def test_recruiter_search_projection_excludes_private_profile_fields(client, recruiter, candidate):
    client.put(
        "/me/profile",
        json={
            "phone": "+91-555-0100",
            "work_authorization": "private-work-status",
            "resume_text": "PRIVATE_RESUME_MARKER",
            "is_discoverable": True,
        },
        headers=_auth(candidate["token"]),
    )
    result = client.get(
        f"/orgs/{recruiter['org_id']}/candidates/search",
        headers=_auth(recruiter["token"], recruiter["org_id"]),
    )
    assert result.status_code == 200
    body = result.json()
    assert "PRIVATE_RESUME_MARKER" not in str(body)
    assert "phone" not in body["profiles"][0]
    assert "work_authorization" not in body["profiles"][0]


def test_plain_recruiter_cannot_read_unassigned_campaign(client):
    owner = _register(client, "assignment-owner@example.com")
    org_id = _create_org(client, owner, slug="assignment-org")
    campaign = client.post(
        f"/orgs/{org_id}/campaigns",
        json={"name": "Owner campaign"},
        headers=_auth(owner, org_id),
    ).json()
    recruiter = _register(client, "assignment-recruiter@example.com")
    added = client.post(
        f"/orgs/{org_id}/members",
        json={"email": "assignment-recruiter@example.com", "role": "recruiter"},
        headers=_auth(owner, org_id),
    )
    assert added.status_code == 201

    response = client.get(
        f"/orgs/{org_id}/campaigns/{campaign['id']}",
        headers=_auth(recruiter, org_id),
    )
    assert response.status_code == 404

    assigned = client.post(
        f"/orgs/{org_id}/campaigns/{campaign['id']}/members",
        json={"user_id": client.get("/auth/me", headers=_auth(recruiter)).json()["user_id"]},
        headers=_auth(owner, org_id),
    )
    assert assigned.status_code == 204
    assert client.get(
        f"/orgs/{org_id}/campaigns/{campaign['id']}",
        headers=_auth(recruiter, org_id),
    ).status_code == 200


def test_matching_accepts_a_minimum_only_experience_requirement():
    result = matching.score_match(
        {"years_experience": 5, "updated_at": None},
        [],
        None,
        {"required_skills": [], "min_experience": 3, "max_experience": None},
    )
    assert result["components"]["experience"] == 1.0


def test_zero_selection_segment_is_not_ignored(isolated_db):
    with isolated_db._get_conn() as (conn, cur):
        cur.execute("INSERT INTO organizations (name, slug) VALUES (?, ?)", ("Bias Org", "bias-org"))
        org_id = cur.lastrowid
        cur.execute("INSERT INTO users (email, email_normalized, password_hash) VALUES (?, ?, ?)", ("selected@example.com", "selected@example.com", "unused"))
        selected_user_id = cur.lastrowid
        cur.execute("INSERT INTO users (email, email_normalized, password_hash) VALUES (?, ?, ?)", ("rejected@example.com", "rejected@example.com", "unused"))
        rejected_user_id = cur.lastrowid
        cur.execute("INSERT INTO campaigns (org_id, name) VALUES (?, ?)", (org_id, "Bias Campaign"))
        campaign_id = cur.lastrowid
        cur.execute("INSERT INTO job_postings (org_id, campaign_id, title) VALUES (?, ?, ?)", (org_id, campaign_id, "Role"))
        posting_id = cur.lastrowid
        cur.execute(
            "INSERT INTO applications (org_id, posting_id, candidate_user_id, profile_snapshot, current_stage, status, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (org_id, posting_id, selected_user_id, "{}", "HIRED", "HIRED", "DIRECT"),
        )
        cur.execute(
            "INSERT INTO applications (org_id, posting_id, candidate_user_id, profile_snapshot, current_stage, status, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (org_id, posting_id, rejected_user_id, "{}", "REJECTED", "REJECTED", "REFERRAL"),
        )

    result = hdb.get_selection_rates(org_id, "source")
    assert result["adverse_impact_ratio"] == 0.0
    assert result["flag_adverse_impact"] is True
