"""
Tests for the hiring domain: profile vault, campaigns, postings, applications.

As with the identity suite, the cross-tenant tests here are the ones that
matter most — they assert that one company cannot read, modify, or even
confirm the existence of another company's campaigns, postings, or applicants.
"""

import pytest

import hiring_db as hdb
from rbac import SystemRole
from tests.test_identity import _auth, _create_org, _register


PASSWORD = "correct-horse-battery"


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def recruiter(client):
    """An org owner (who holds every recruiter capability) plus their org."""
    token = _register(client, "recruiter@acme.com", name="Rita Recruiter")
    org_id = _create_org(client, token, name="Acme", slug="acme")
    return {"token": token, "org_id": org_id}


@pytest.fixture
def candidate(client):
    """A registered candidate with a complete, applyable profile."""
    token = _register(client, "candidate@example.com", name="Cara Candidate")
    client.put(
        "/me/profile",
        json={
            "headline": "Backend Engineer",
            "summary": "Builds distributed systems.",
            "location": "Bangalore",
            "years_experience": 5,
        },
        headers=_auth(token),
    )
    client.put(
        "/me/profile/skills",
        json={"skills": [{"skill": "Python", "years": 5}, {"skill": "PostgreSQL", "years": 3}]},
        headers=_auth(token),
    )
    return {"token": token}


def _make_posting(client, recruiter, *, publish=True, questions=None, title="Backend Engineer"):
    org_id = recruiter["org_id"]
    headers = _auth(recruiter["token"], org_id)

    campaign = client.post(
        f"/orgs/{org_id}/campaigns",
        json={"name": "Q4 Hiring", "description": "Backend expansion"},
        headers=headers,
    ).json()

    posting = client.post(
        f"/orgs/{org_id}/postings",
        json={
            "campaign_id": campaign["id"],
            "title": title,
            "description": "Build things.",
            "location": "Bangalore",
            "remote_policy": "HYBRID",
            "min_experience": 3,
            "max_experience": 8,
            "required_skills": ["Python", "PostgreSQL"],
            "screening_questions": questions or [],
        },
        headers=headers,
    ).json()

    if publish:
        client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/status",
            json={"status": "PUBLISHED"},
            headers=headers,
        )
    return posting


# ── Profile vault ────────────────────────────────────────────────────


class TestProfileVault:
    def test_profile_is_created_then_updated_idempotently(self, client):
        token = _register(client, "vault@example.com")

        first = client.put(
            "/me/profile", json={"headline": "Engineer"}, headers=_auth(token)
        )
        assert first.status_code == 200
        assert first.json()["headline"] == "Engineer"

        second = client.put(
            "/me/profile", json={"headline": "Senior Engineer"}, headers=_auth(token)
        )
        assert second.status_code == 200
        assert second.json()["headline"] == "Senior Engineer"
        assert second.json()["id"] == first.json()["id"]

    def test_consent_is_stamped_on_creation(self, client):
        """Consent cannot be obtained retroactively, so it must be captured up front."""
        token = _register(client, "consent@example.com")
        body = client.put("/me/profile", json={"headline": "X"}, headers=_auth(token)).json()
        assert body["data_consent_at"] is not None
        assert body["data_consent_version"] == "v1"

    def test_profile_requires_authentication(self, client):
        assert client.get("/me/profile").status_code == 401

    def test_missing_profile_returns_404(self, client):
        token = _register(client, "noprofile@example.com")
        assert client.get("/me/profile", headers=_auth(token)).status_code == 404

    def test_experience_and_education_roundtrip(self, client, candidate):
        token = candidate["token"]
        client.post(
            "/me/profile/experience",
            json={
                "company": "Acme", "title": "Engineer",
                "start_date": "2021-01", "is_current": True,
            },
            headers=_auth(token),
        )
        client.post(
            "/me/profile/education",
            json={"institution": "State University", "degree": "BSc", "end_year": 2018},
            headers=_auth(token),
        )
        profile = client.get("/me/profile", headers=_auth(token)).json()
        assert len(profile["experiences"]) == 1
        assert len(profile["education"]) == 1

    def test_cannot_delete_another_users_experience(self, client, candidate):
        """Deletes are scoped by profile, so a guessed ID must not work."""
        other = _register(client, "other@example.com")
        client.put("/me/profile", json={"headline": "Other"}, headers=_auth(other))
        experience_id = client.post(
            "/me/profile/experience",
            json={"company": "Globex", "title": "Dev", "start_date": "2020-01"},
            headers=_auth(other),
        ).json()["id"]

        resp = client.delete(
            f"/me/profile/experience/{experience_id}", headers=_auth(candidate["token"])
        )
        assert resp.status_code == 404

        # And the row genuinely still exists for its real owner.
        assert len(client.get("/me/profile", headers=_auth(other)).json()["experiences"]) == 1

    def test_verified_skills_survive_a_profile_edit(self, client, candidate, isolated_db):
        """A profile edit must not be able to fabricate or erase a verified skill."""
        import candidate_db as cdb

        token = candidate["token"]
        profile = client.get("/me/profile", headers=_auth(token)).json()
        cdb.mark_skill_verified(profile["id"], "Python", "assessment:dsa-101")

        client.put(
            "/me/profile/skills",
            json={"skills": [{"skill": "Python", "years": 9}, {"skill": "Go", "years": 1}]},
            headers=_auth(token),
        )
        skills = {s["skill"]: s for s in client.get("/me/profile", headers=_auth(token)).json()["skills"]}
        assert bool(skills["Python"]["verified"]) is True
        assert skills["Python"]["verified_source"] == "assessment:dsa-101"
        # A newly claimed skill is not verified just because it was added.
        assert bool(skills["Go"]["verified"]) is False

    def test_salary_range_is_validated(self, client, candidate):
        resp = client.put(
            "/me/profile/preferences",
            json={"min_salary": 100, "max_salary": 50},
            headers=_auth(candidate["token"]),
        )
        assert resp.status_code == 400


# ── Campaigns & postings ─────────────────────────────────────────────


class TestCampaignsAndPostings:
    def test_create_campaign_and_posting(self, client, recruiter):
        posting = _make_posting(client, recruiter, publish=False)
        assert posting["status"] == "DRAFT"
        assert posting["auto_reject_enabled"] is False

    def test_auto_reject_defaults_to_disabled(self, client, recruiter):
        """Automated rejection is an opt-in regulated act. See DECISIONS.md D-10."""
        posting = _make_posting(client, recruiter, publish=False)
        assert posting["auto_reject_enabled"] is False

    def test_draft_postings_are_not_on_the_public_board(self, client, recruiter):
        _make_posting(client, recruiter, publish=False, title="Secret Role")
        board = client.get("/jobs").json()
        assert all(p["title"] != "Secret Role" for p in board["postings"])

    def test_publishing_exposes_the_posting(self, client, recruiter):
        _make_posting(client, recruiter, publish=True, title="Public Role")
        board = client.get("/jobs").json()
        assert any(p["title"] == "Public Role" for p in board["postings"])

    def test_job_board_is_browsable_without_an_account(self, client, recruiter):
        """Requiring login to browse jobs would defeat the acquisition funnel."""
        _make_posting(client, recruiter, publish=True)
        assert client.get("/jobs").status_code == 200

    def test_posting_cannot_attach_to_another_orgs_campaign(self, client, recruiter):
        other = _register(client, "other-org@example.com")
        other_org = _create_org(client, other, name="Globex", slug="globex")
        other_campaign = client.post(
            f"/orgs/{other_org}/campaigns",
            json={"name": "Theirs", "description": ""},
            headers=_auth(other, other_org),
        ).json()

        resp = client.post(
            f"/orgs/{recruiter['org_id']}/postings",
            json={"campaign_id": other_campaign["id"], "title": "Sneaky"},
            headers=_auth(recruiter["token"], recruiter["org_id"]),
        )
        assert resp.status_code == 404

    def test_experience_range_is_validated(self, client, recruiter):
        org_id = recruiter["org_id"]
        headers = _auth(recruiter["token"], org_id)
        campaign = client.post(
            f"/orgs/{org_id}/campaigns", json={"name": "C", "description": ""}, headers=headers
        ).json()
        resp = client.post(
            f"/orgs/{org_id}/postings",
            json={"campaign_id": campaign["id"], "title": "T",
                  "min_experience": 10, "max_experience": 2},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_search_filters_by_query_and_remote_policy(self, client, recruiter):
        _make_posting(client, recruiter, publish=True, title="Rust Engineer")
        assert client.get("/jobs", params={"q": "rust"}).json()["total"] == 1
        assert client.get("/jobs", params={"q": "cobol"}).json()["total"] == 0
        assert client.get("/jobs", params={"remote_policy": "REMOTE"}).json()["total"] == 0


# ── Applying ─────────────────────────────────────────────────────────


class TestApplying:
    def test_apply_and_track(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        resp = client.post(
            f"/jobs/{posting['id']}/apply", json={"answers": []},
            headers=_auth(candidate["token"]),
        )
        assert resp.status_code == 201

        tracker = client.get("/me/applications", headers=_auth(candidate["token"])).json()
        assert len(tracker["applications"]) == 1
        assert tracker["applications"][0]["posting_title"] == "Backend Engineer"
        assert tracker["applications"][0]["org_name"] == "Acme"

    def test_cannot_apply_twice(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        headers = _auth(candidate["token"])
        assert client.post(f"/jobs/{posting['id']}/apply", json={}, headers=headers).status_code == 201
        assert client.post(f"/jobs/{posting['id']}/apply", json={}, headers=headers).status_code == 409

    def test_withdrawing_allows_reapplying(self, client, recruiter, candidate):
        """The uniqueness index excludes withdrawn rows precisely so this works."""
        posting = _make_posting(client, recruiter)
        headers = _auth(candidate["token"])
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=headers
        ).json()["application_id"]

        client.post(f"/me/applications/{application_id}/withdraw", headers=headers)
        assert client.post(f"/jobs/{posting['id']}/apply", json={}, headers=headers).status_code == 201

    def test_cannot_apply_without_a_profile(self, client, recruiter):
        posting = _make_posting(client, recruiter)
        token = _register(client, "profileless@example.com")
        resp = client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(token))
        assert resp.status_code == 400

    def test_cannot_apply_to_an_unpublished_posting(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter, publish=False)
        resp = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        )
        assert resp.status_code == 404

    def test_missing_required_answer_is_rejected(self, client, recruiter, candidate):
        posting = _make_posting(
            client, recruiter,
            questions=[{"key": "why_us", "text": "Why us?", "required": True}],
        )
        resp = client.post(
            f"/jobs/{posting['id']}/apply", json={"answers": []},
            headers=_auth(candidate["token"]),
        )
        assert resp.status_code == 400
        assert "why_us" in resp.json()["detail"]


# ── The "fill it once" mechanic ──────────────────────────────────────


class TestAnswerVault:
    def test_answers_are_saved_and_prefilled_on_the_next_application(
        self, client, recruiter, candidate
    ):
        """This is the core retention mechanic: application two is cheaper
        than application one."""
        questions = [{"key": "notice_period", "text": "Notice period?", "required": True}]
        first = _make_posting(client, recruiter, questions=questions, title="Role One")
        headers = _auth(candidate["token"])

        # First application: the question is new, so it must be answered.
        form = client.get(f"/jobs/{first['id']}/application-form", headers=headers).json()
        assert form["unanswered_count"] == 1
        assert form["questions"][0]["is_prefilled"] is False

        client.post(
            f"/jobs/{first['id']}/apply",
            json={"answers": [{"question_key": "notice_period", "answer_text": "30 days"}]},
            headers=headers,
        )

        # Second posting asking the same question is now pre-filled.
        second = _make_posting(client, recruiter, questions=questions, title="Role Two")
        form = client.get(f"/jobs/{second['id']}/application-form", headers=headers).json()
        assert form["unanswered_count"] == 0
        assert form["questions"][0]["prefilled_answer"] == "30 days"

        # ...and can be submitted with no answers at all.
        assert client.post(
            f"/jobs/{second['id']}/apply", json={"answers": []}, headers=headers
        ).status_code == 201

    def test_opting_out_of_saving_leaves_the_vault_untouched(
        self, client, recruiter, candidate
    ):
        questions = [{"key": "secret_q", "text": "Sensitive?", "required": True}]
        posting = _make_posting(client, recruiter, questions=questions)
        headers = _auth(candidate["token"])

        client.post(
            f"/jobs/{posting['id']}/apply",
            json={
                "answers": [{"question_key": "secret_q", "answer_text": "private"}],
                "save_answers_to_vault": False,
            },
            headers=headers,
        )
        other = _make_posting(client, recruiter, questions=questions, title="Other")
        form = client.get(f"/jobs/{other['id']}/application-form", headers=headers).json()
        assert form["questions"][0]["is_prefilled"] is False


# ── Application state machine ────────────────────────────────────────


class TestApplicationStateMachine:
    def test_valid_transitions_are_allowed(self):
        assert hdb.can_transition("APPLIED", "SCREENING")
        assert hdb.can_transition("SCREENING", "TECHNICAL")
        assert hdb.can_transition("OFFER", "HIRED")

    def test_invalid_transitions_are_rejected(self):
        assert not hdb.can_transition("APPLIED", "HIRED")
        assert not hdb.can_transition("APPLIED", "OFFER")
        assert not hdb.can_transition("REJECTED", "SCREENING")
        assert not hdb.can_transition("HIRED", "REJECTED")

    def test_terminal_stages_have_no_exits(self):
        for stage in ("HIRED", "REJECTED", "WITHDRAWN"):
            assert not any(hdb.can_transition(stage, other) for other in hdb.ApplicationStage)

    def test_pending_review_can_go_either_way(self):
        """A human must be able to override an adverse automated recommendation."""
        assert hdb.can_transition("PENDING_REVIEW", "TECHNICAL")
        assert hdb.can_transition("PENDING_REVIEW", "REJECTED")

    def test_recruiter_can_advance_an_application(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]

        org_id = recruiter["org_id"]
        resp = client.post(
            f"/orgs/{org_id}/applications/{application_id}/transition",
            json={"to_stage": "SCREENING", "note": "Looks promising"},
            headers=_auth(recruiter["token"], org_id),
        )
        assert resp.status_code == 200
        assert resp.json()["to_stage"] == "SCREENING"

    def test_illegal_transition_returns_409(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]

        org_id = recruiter["org_id"]
        resp = client.post(
            f"/orgs/{org_id}/applications/{application_id}/transition",
            json={"to_stage": "HIRED"},
            headers=_auth(recruiter["token"], org_id),
        )
        assert resp.status_code == 409

    def test_candidate_sees_stage_changes_in_their_timeline(
        self, client, recruiter, candidate
    ):
        posting = _make_posting(client, recruiter)
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]

        org_id = recruiter["org_id"]
        client.post(
            f"/orgs/{org_id}/applications/{application_id}/transition",
            json={"to_stage": "SCREENING", "note": "internal note - do not leak"},
            headers=_auth(recruiter["token"], org_id),
        )

        detail = client.get(
            f"/me/applications/{application_id}", headers=_auth(candidate["token"])
        ).json()
        assert detail["application"]["current_stage"] == "SCREENING"
        # Internal recruiter notes must not reach the candidate.
        assert "internal note" not in str(detail["timeline"])


# ── Tenant isolation (CI gate) ───────────────────────────────────────


class TestHiringTenantIsolation:
    @pytest.fixture
    def two_orgs(self, client, candidate):
        acme_token = _register(client, "acme-rec@example.com")
        acme_org = _create_org(client, acme_token, name="Acme", slug="acme-iso")
        globex_token = _register(client, "globex-rec@example.com")
        globex_org = _create_org(client, globex_token, name="Globex", slug="globex-iso")

        acme = {"token": acme_token, "org_id": acme_org}
        posting = _make_posting(client, acme, title="Acme Role")
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]

        return {
            "acme": acme, "globex": {"token": globex_token, "org_id": globex_org},
            "posting_id": posting["id"], "application_id": application_id,
        }

    def test_cannot_list_another_orgs_campaigns(self, client, two_orgs):
        resp = client.get(
            f"/orgs/{two_orgs['acme']['org_id']}/campaigns",
            headers=_auth(two_orgs["globex"]["token"], two_orgs["acme"]["org_id"]),
        )
        assert resp.status_code == 404

    def test_cannot_read_another_orgs_posting(self, client, two_orgs):
        resp = client.get(
            f"/orgs/{two_orgs['acme']['org_id']}/postings/{two_orgs['posting_id']}",
            headers=_auth(two_orgs["globex"]["token"], two_orgs["acme"]["org_id"]),
        )
        assert resp.status_code == 404

    def test_cannot_read_another_orgs_applicants(self, client, two_orgs):
        resp = client.get(
            f"/orgs/{two_orgs['acme']['org_id']}/postings/{two_orgs['posting_id']}/applications",
            headers=_auth(two_orgs["globex"]["token"], two_orgs["acme"]["org_id"]),
        )
        assert resp.status_code == 404

    def test_cannot_transition_another_orgs_application(self, client, two_orgs):
        resp = client.post(
            f"/orgs/{two_orgs['acme']['org_id']}/applications/{two_orgs['application_id']}/transition",
            json={"to_stage": "REJECTED"},
            headers=_auth(two_orgs["globex"]["token"], two_orgs["acme"]["org_id"]),
        )
        assert resp.status_code == 404

    def test_globex_cannot_reach_the_application_through_its_own_org_id(self, client, two_orgs):
        """Using their own org context against another tenant's resource ID."""
        resp = client.get(
            f"/orgs/{two_orgs['globex']['org_id']}/applications/{two_orgs['application_id']}",
            headers=_auth(two_orgs["globex"]["token"], two_orgs["globex"]["org_id"]),
        )
        assert resp.status_code == 404

    def test_owning_org_can_still_read_its_own_applicants(self, client, two_orgs):
        """Positive control: isolation tests must not pass by denying everything."""
        resp = client.get(
            f"/orgs/{two_orgs['acme']['org_id']}/postings/{two_orgs['posting_id']}/applications",
            headers=_auth(two_orgs["acme"]["token"], two_orgs["acme"]["org_id"]),
        )
        assert resp.status_code == 200
        assert len(resp.json()["applications"]) == 1

    def test_candidate_cannot_read_another_candidates_application(
        self, client, two_orgs
    ):
        intruder = _register(client, "intruder@example.com")
        resp = client.get(
            f"/me/applications/{two_orgs['application_id']}", headers=_auth(intruder)
        )
        assert resp.status_code == 404


# ── Capability enforcement ───────────────────────────────────────────


class TestHiringCapabilities:
    @pytest.fixture
    def interviewer(self, client, recruiter):
        token = _register(client, "interviewer@acme.com")
        client.post(
            f"/orgs/{recruiter['org_id']}/members",
            json={"email": "interviewer@acme.com", "role": str(SystemRole.INTERVIEWER)},
            headers=_auth(recruiter["token"], recruiter["org_id"]),
        )
        return token

    def test_interviewer_cannot_create_campaigns(self, client, recruiter, interviewer):
        resp = client.post(
            f"/orgs/{recruiter['org_id']}/campaigns",
            json={"name": "Nope", "description": ""},
            headers=_auth(interviewer, recruiter["org_id"]),
        )
        assert resp.status_code == 403

    def test_interviewer_cannot_advance_applications(
        self, client, recruiter, candidate, interviewer
    ):
        posting = _make_posting(client, recruiter)
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]

        resp = client.post(
            f"/orgs/{recruiter['org_id']}/applications/{application_id}/transition",
            json={"to_stage": "SCREENING"},
            headers=_auth(interviewer, recruiter["org_id"]),
        )
        assert resp.status_code == 403

    def test_candidate_cannot_use_recruiter_endpoints(self, client, recruiter, candidate):
        resp = client.get(
            f"/orgs/{recruiter['org_id']}/campaigns",
            headers=_auth(candidate["token"], recruiter["org_id"]),
        )
        # Not a member of that org at all, so existence is denied.
        assert resp.status_code == 404


# ── Audit coverage ───────────────────────────────────────────────────


class TestHiringAudit:
    def test_key_hiring_actions_are_audited(self, client, recruiter, candidate, isolated_db):
        posting = _make_posting(client, recruiter)
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]
        org_id = recruiter["org_id"]
        client.post(
            f"/orgs/{org_id}/applications/{application_id}/transition",
            json={"to_stage": "SCREENING"},
            headers=_auth(recruiter["token"], org_id),
        )

        actions = {e["action"] for e in isolated_db.list_audit_events(limit=100)}
        for expected in (
            "campaign.created", "posting.created", "posting.published",
            "application.submitted", "application.advanced",
        ):
            assert expected in actions, f"missing audit event: {expected}"

    def test_rejection_is_audited_at_tier_1(self, client, recruiter, candidate, isolated_db):
        """A rejection is an adverse decision about a person, however routine."""
        posting = _make_posting(client, recruiter)
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]
        org_id = recruiter["org_id"]
        client.post(
            f"/orgs/{org_id}/applications/{application_id}/transition",
            json={"to_stage": "REJECTED", "note": "Not a fit"},
            headers=_auth(recruiter["token"], org_id),
        )

        rejections = [
            e for e in isolated_db.list_audit_events(limit=100)
            if e["action"] == "application.rejected"
        ]
        assert len(rejections) == 1
        assert rejections[0]["tier"] == 1

    def test_recruiter_reading_candidate_data_is_audited(
        self, client, recruiter, candidate, isolated_db
    ):
        posting = _make_posting(client, recruiter)
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]
        org_id = recruiter["org_id"]
        client.get(
            f"/orgs/{org_id}/applications/{application_id}",
            headers=_auth(recruiter["token"], org_id),
        )

        views = [
            e for e in isolated_db.list_audit_events(limit=100)
            if e["action"] == "application.viewed"
        ]
        assert len(views) == 1
        assert views[0]["tier"] == 3

    def test_audit_chain_survives_a_full_hiring_flow(
        self, client, recruiter, candidate, isolated_db
    ):
        posting = _make_posting(client, recruiter)
        client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"]))
        assert isolated_db.verify_audit_chain()["valid"] is True
