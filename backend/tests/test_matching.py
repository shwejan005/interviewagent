"""
Tests for Phase 2: matching, sourcing, referrals, analytics.

matching.py's scoring function is pure (no I/O), so TestScoreMatch exercises
it directly with hand-built fixtures rather than going through the API — this
is deliberately the fastest, most exhaustive way to pin down the scoring
behaviour, and it is what makes the weighting defensible: every claim about
how the score responds to a factor has a test attached to it.
"""

import pytest

from app.candidate import service as matching
from tests.test_hiring import _auth, _create_org, _make_posting, _register


# ── Pure scoring function ────────────────────────────────────────────


def _profile(years=5, updated_at=None):
    return {"years_experience": years, "updated_at": updated_at}


def _skills(*names, verified=None):
    verified = verified or set()
    return [{"skill": n, "verified": n in verified} for n in names]


def _posting(required_skills=None, min_exp=None, max_exp=None, location="Bangalore",
            remote_policy="ONSITE", salary_min=None, salary_max=None):
    return {
        "required_skills": required_skills or [],
        "min_experience": min_exp, "max_experience": max_exp,
        "location": location, "remote_policy": remote_policy,
        "salary_min": salary_min, "salary_max": salary_max,
    }


class TestScoreMatchSkills:
    def test_full_skill_overlap_scores_higher_than_partial(self):
        posting = _posting(required_skills=["Python", "PostgreSQL"])
        full = matching.score_match(_profile(), _skills("Python", "PostgreSQL"), None, posting)
        partial = matching.score_match(_profile(), _skills("Python"), None, posting)
        assert full["score"] > partial["score"]
        assert full["components"]["skills"] > partial["components"]["skills"]

    def test_missing_skills_are_named_in_the_explanation(self):
        posting = _posting(required_skills=["Python", "Kubernetes"])
        result = matching.score_match(_profile(), _skills("Python"), None, posting)
        assert "Kubernetes" in result["missing_skills"]
        assert "Kubernetes" in result["explanation"]

    def test_verified_skill_scores_higher_than_unverified(self):
        # Two required skills so a single match's base score (0.5) stays
        # below the 1.0 cap, letting the verified bonus actually show through.
        posting = _posting(required_skills=["Python", "Go"])
        verified = matching.score_match(
            _profile(), _skills("Python", verified={"Python"}), None, posting
        )
        unverified = matching.score_match(_profile(), _skills("Python"), None, posting)
        assert verified["components"]["skills"] > unverified["components"]["skills"]

    def test_no_required_skills_is_not_penalized(self):
        posting = _posting(required_skills=[])
        result = matching.score_match(_profile(), _skills(), None, posting)
        assert result["components"]["skills"] > 0.5

    def test_skill_matching_is_case_and_spacing_insensitive(self):
        posting = _posting(required_skills=["Node JS"])
        result = matching.score_match(_profile(), _skills("node  js"), None, posting)
        assert result["components"]["skills"] == 1.0


class TestScoreMatchExperience:
    def test_within_range_scores_full_marks(self):
        posting = _posting(min_exp=3, max_exp=8)
        result = matching.score_match(_profile(years=5), [], None, posting)
        assert result["components"]["experience"] == 1.0

    def test_under_qualified_is_penalized_proportionally(self):
        posting = _posting(min_exp=8, max_exp=12)
        junior = matching.score_match(_profile(years=1), [], None, posting)
        closer = matching.score_match(_profile(years=6), [], None, posting)
        assert junior["components"]["experience"] < closer["components"]["experience"]

    def test_over_qualified_is_penalized_more_gently_than_under_qualified(self):
        posting = _posting(min_exp=3, max_exp=5)
        over = matching.score_match(_profile(years=8), [], None, posting)
        under = matching.score_match(_profile(years=0), [], None, posting)
        assert over["components"]["experience"] > under["components"]["experience"]
        assert over["components"]["experience"] >= 0.3  # floored, not zeroed

    def test_missing_candidate_experience_is_neutral_not_zero(self):
        posting = _posting(min_exp=3, max_exp=8)
        result = matching.score_match(_profile(years=None), [], None, posting)
        assert 0 < result["components"]["experience"] < 1

    def test_no_requirement_stated_is_full_marks(self):
        posting = _posting(min_exp=None, max_exp=None)
        result = matching.score_match(_profile(years=1), [], None, posting)
        assert result["components"]["experience"] == 1.0


class TestScoreMatchLocation:
    def test_remote_posting_ignores_location_by_default(self):
        posting = _posting(remote_policy="REMOTE")
        result = matching.score_match(_profile(), [], {"remote_preference": "ANY", "locations": []}, posting)
        assert result["components"]["location"] == 1.0

    def test_onsite_only_candidate_penalized_for_remote_posting(self):
        posting = _posting(remote_policy="REMOTE")
        result = matching.score_match(
            _profile(), [], {"remote_preference": "ONSITE", "locations": []}, posting
        )
        assert result["components"]["location"] < 0.5

    def test_remote_only_candidate_penalized_for_onsite_posting(self):
        posting = _posting(remote_policy="ONSITE", location="Bangalore")
        result = matching.score_match(
            _profile(), [], {"remote_preference": "REMOTE", "locations": ["Bangalore"]}, posting
        )
        assert result["components"]["location"] < 0.5

    def test_matching_preferred_location_scores_full_marks(self):
        posting = _posting(remote_policy="ONSITE", location="Bangalore")
        result = matching.score_match(
            _profile(), [], {"remote_preference": "ANY", "locations": ["Bangalore", "Pune"]}, posting
        )
        assert result["components"]["location"] == 1.0


class TestScoreMatchCompensation:
    def test_overlapping_ranges_score_well(self):
        posting = _posting(salary_min=1000000, salary_max=1500000)
        result = matching.score_match(
            _profile(), [], {"min_salary": 1200000, "max_salary": 1600000}, posting
        )
        assert result["components"]["compensation"] > 0.5

    def test_non_overlapping_ranges_score_poorly(self):
        posting = _posting(salary_min=500000, salary_max=700000)
        result = matching.score_match(
            _profile(), [], {"min_salary": 2000000, "max_salary": 2500000}, posting
        )
        assert result["components"]["compensation"] < 0.3

    def test_missing_data_on_either_side_is_neutral(self):
        posting = _posting(salary_min=None, salary_max=None)
        result = matching.score_match(_profile(), [], {"min_salary": 1000000}, posting)
        assert 0.3 < result["components"]["compensation"] < 0.8


class TestScoreMatchOverall:
    def test_score_is_bounded_zero_to_ten(self):
        posting = _posting(required_skills=["Rust"], min_exp=15, max_exp=20,
                           remote_policy="ONSITE", location="Nowhere")
        result = matching.score_match(
            _profile(years=0), [], {"remote_preference": "REMOTE", "locations": []}, posting
        )
        assert 0 <= result["score"] <= 10

    def test_perfect_candidate_scores_near_the_top(self):
        posting = _posting(
            required_skills=["Python", "PostgreSQL"], min_exp=3, max_exp=8,
            remote_policy="REMOTE",
        )
        result = matching.score_match(
            _profile(years=5),
            _skills("Python", "PostgreSQL", verified={"Python", "PostgreSQL"}),
            {"remote_preference": "ANY", "locations": []},
            posting,
        )
        assert result["score"] >= 8.5

    def test_explanation_is_never_empty(self):
        posting = _posting()
        result = matching.score_match(_profile(), [], None, posting)
        assert result["explanation"]


# ── API-level: recommendations, sourcing, referrals, analytics ──────


PASSWORD = "correct-horse-battery"


@pytest.fixture
def recruiter(client):
    token = _register(client, "recruiter@acme.com", name="Rita Recruiter")
    org_id = _create_org(client, token, name="Acme", slug="acme")
    return {"token": token, "org_id": org_id}


@pytest.fixture
def candidate(client):
    token = _register(client, "candidate@example.com", name="Cara Candidate")
    client.put(
        "/me/profile",
        json={
            "headline": "Backend Engineer", "location": "Bangalore",
            "years_experience": 5, "is_discoverable": True,
        },
        headers=_auth(token),
    )
    client.put(
        "/me/profile/skills",
        json={"skills": [{"skill": "Python", "years": 5}, {"skill": "PostgreSQL", "years": 3}]},
        headers=_auth(token),
    )
    return {"token": token}


class TestRecommendedJobs:
    def test_recommendations_are_ranked_and_explained(self, client, recruiter, candidate):
        _make_posting(client, recruiter, title="Strong Match")
        resp = client.get("/me/recommended-jobs", headers=_auth(candidate["token"]))
        assert resp.status_code == 200
        recs = resp.json()["recommendations"]
        assert len(recs) == 1
        assert recs[0]["title"] == "Strong Match"
        assert "explanation" in recs[0]

    def test_applied_postings_are_excluded_from_recommendations(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        )
        recs = client.get("/me/recommended-jobs", headers=_auth(candidate["token"])).json()
        assert recs["recommendations"] == []

    def test_no_profile_returns_no_recommendations_not_an_error(self, client, recruiter):
        _make_posting(client, recruiter)
        token = _register(client, "noprofile@example.com")
        resp = client.get("/me/recommended-jobs", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["recommendations"] == []


class TestCandidateSourcing:
    def test_non_discoverable_candidates_never_appear(self, client, recruiter):
        token = _register(client, "private@example.com")
        client.put(
            "/me/profile",
            json={"headline": "Private Candidate", "is_discoverable": False},
            headers=_auth(token),
        )
        org_id = recruiter["org_id"]
        result = client.get(
            f"/orgs/{org_id}/candidates/search", headers=_auth(recruiter["token"], org_id)
        ).json()
        assert all(p["full_name"] != "" for p in result["profiles"])
        names = [p["email"] for p in result["profiles"]]
        assert "private@example.com" not in names

    def test_discoverable_candidate_appears_in_search(self, client, recruiter, candidate):
        org_id = recruiter["org_id"]
        result = client.get(
            f"/orgs/{org_id}/candidates/search", headers=_auth(recruiter["token"], org_id)
        ).json()
        assert result["total"] == 1

    def test_search_is_audited_as_sensitive_read(self, client, recruiter, candidate, isolated_db):
        org_id = recruiter["org_id"]
        client.get(f"/orgs/{org_id}/candidates/search", headers=_auth(recruiter["token"], org_id))
        searches = [
            e for e in isolated_db.list_audit_events(limit=50)
            if e["action"] == "candidate.searched"
        ]
        assert len(searches) == 1
        assert searches[0]["tier"] == 3

    def test_recommended_candidates_ranked_against_posting(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        resp = client.get(
            f"/orgs/{org_id}/postings/{posting['id']}/recommended-candidates",
            headers=_auth(recruiter["token"], org_id),
        )
        assert resp.status_code == 200
        assert len(resp.json()["candidates"]) == 1

    def test_already_applied_candidates_excluded_from_recommendations(
        self, client, recruiter, candidate
    ):
        posting = _make_posting(client, recruiter)
        client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"]))
        org_id = recruiter["org_id"]
        resp = client.get(
            f"/orgs/{org_id}/postings/{posting['id']}/recommended-candidates",
            headers=_auth(recruiter["token"], org_id),
        )
        assert resp.json()["candidates"] == []

    def test_interviewer_cannot_search_candidates(self, client, recruiter):
        from app.shared.rbac import SystemRole

        token = _register(client, "interviewer2@acme.com")
        client.post(
            f"/orgs/{recruiter['org_id']}/members",
            json={"email": "interviewer2@acme.com", "role": str(SystemRole.INTERVIEWER)},
            headers=_auth(recruiter["token"], recruiter["org_id"]),
        )
        resp = client.get(
            f"/orgs/{recruiter['org_id']}/candidates/search",
            headers=_auth(token, recruiter["org_id"]),
        )
        assert resp.status_code == 403


class TestReferrals:
    def test_recruiter_refers_a_registered_candidate(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        resp = client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/referrals",
            json={"candidate_email": "candidate@example.com", "note": "Strong fit"},
            headers=_auth(recruiter["token"], org_id),
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "PENDING"

    def test_candidate_sees_the_referral_in_their_inbox(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/referrals",
            json={"candidate_email": "candidate@example.com"},
            headers=_auth(recruiter["token"], org_id),
        )
        inbox = client.get("/me/referrals", headers=_auth(candidate["token"])).json()
        assert len(inbox["referrals"]) == 1
        assert inbox["referrals"][0]["posting_title"] == posting["title"]

    def test_duplicate_pending_referral_is_rejected(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        headers = _auth(recruiter["token"], org_id)
        payload = {"candidate_email": "candidate@example.com"}
        assert client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/referrals", json=payload, headers=headers
        ).status_code == 201
        assert client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/referrals", json=payload, headers=headers
        ).status_code == 409

    def test_accepting_a_referral_creates_an_application_with_referral_source(
        self, client, recruiter, candidate
    ):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        referral = client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/referrals",
            json={"candidate_email": "candidate@example.com"},
            headers=_auth(recruiter["token"], org_id),
        ).json()

        resp = client.post(
            f"/me/referrals/{referral['id']}/apply", json={},
            headers=_auth(candidate["token"]),
        )
        assert resp.status_code == 201

        tracker = client.get("/me/applications", headers=_auth(candidate["token"])).json()
        assert len(tracker["applications"]) == 1

    def test_declining_a_referral_prevents_reapplying_through_it(
        self, client, recruiter, candidate
    ):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        referral = client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/referrals",
            json={"candidate_email": "candidate@example.com"},
            headers=_auth(recruiter["token"], org_id),
        ).json()

        assert client.post(
            f"/me/referrals/{referral['id']}/decline", headers=_auth(candidate["token"])
        ).status_code == 200
        assert client.post(
            f"/me/referrals/{referral['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).status_code == 409

    def test_cannot_action_someone_elses_referral(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        referral = client.post(
            f"/orgs/{org_id}/postings/{posting['id']}/referrals",
            json={"candidate_email": "candidate@example.com"},
            headers=_auth(recruiter["token"], org_id),
        ).json()

        intruder = _register(client, "intruder2@example.com")
        resp = client.post(
            f"/me/referrals/{referral['id']}/decline", headers=_auth(intruder)
        )
        assert resp.status_code == 404

    def test_interviewer_cannot_create_referrals(self, client, recruiter, candidate):
        from app.shared.rbac import SystemRole

        token = _register(client, "interviewer3@acme.com")
        client.post(
            f"/orgs/{recruiter['org_id']}/members",
            json={"email": "interviewer3@acme.com", "role": str(SystemRole.INTERVIEWER)},
            headers=_auth(recruiter["token"], recruiter["org_id"]),
        )
        posting = _make_posting(client, recruiter)
        resp = client.post(
            f"/orgs/{recruiter['org_id']}/postings/{posting['id']}/referrals",
            json={"candidate_email": "candidate@example.com"},
            headers=_auth(token, recruiter["org_id"]),
        )
        assert resp.status_code == 403


class TestAnalytics:
    def test_funnel_counts_applications_reaching_each_stage(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]
        client.post(
            f"/orgs/{org_id}/applications/{application_id}/transition",
            json={"to_stage": "SCREENING"},
            headers=_auth(recruiter["token"], org_id),
        )

        funnel = client.get(
            f"/orgs/{org_id}/analytics/funnel", headers=_auth(recruiter["token"], org_id)
        ).json()
        by_stage = {s["stage"]: s["reached"] for s in funnel["funnel"]}
        assert by_stage["APPLIED"] == 1
        assert by_stage["SCREENING"] == 1
        assert by_stage["TECHNICAL"] == 0

    def test_plain_recruiter_cannot_read_analytics(self, client, recruiter):
        """Analytics is gated at org-wide read, one level above a plain recruiter."""
        from app.shared.rbac import SystemRole

        token = _register(client, "recruiter2@acme.com")
        client.post(
            f"/orgs/{recruiter['org_id']}/members",
            json={"email": "recruiter2@acme.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(recruiter["token"], recruiter["org_id"]),
        )
        resp = client.get(
            f"/orgs/{recruiter['org_id']}/analytics/funnel",
            headers=_auth(token, recruiter["org_id"]),
        )
        assert resp.status_code == 403

    def test_selection_rates_reports_a_ratio_without_protected_characteristics(
        self, client, recruiter, candidate
    ):
        """The endpoint must work using only fields already on file (source /
        experience band) — it must never require or accept demographic input."""
        posting = _make_posting(client, recruiter)
        client.post(f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"]))
        org_id = recruiter["org_id"]

        result = client.get(
            f"/orgs/{org_id}/analytics/selection-rates",
            headers=_auth(recruiter["token"], org_id),
        ).json()
        assert result["segment_by"] == "source"
        assert "DIRECT" in result["segments"]
        assert "note" in result

    def test_invalid_segment_is_rejected(self, client, recruiter):
        org_id = recruiter["org_id"]
        resp = client.get(
            f"/orgs/{org_id}/analytics/selection-rates?segment_by=gender",
            headers=_auth(recruiter["token"], org_id),
        )
        assert resp.status_code == 422  # rejected by the query pattern before reaching the handler

    def test_overview_aggregates_trend_stage_source_and_leaderboards(self, client, recruiter, candidate):
        posting = _make_posting(client, recruiter)
        org_id = recruiter["org_id"]
        application_id = client.post(
            f"/jobs/{posting['id']}/apply", json={}, headers=_auth(candidate["token"])
        ).json()["application_id"]
        for stage in ("SCREENING", "TECHNICAL", "BEHAVIORAL", "INTERVIEW", "OFFER", "HIRED"):
            client.post(
                f"/orgs/{org_id}/applications/{application_id}/transition",
                json={"to_stage": stage},
                headers=_auth(recruiter["token"], org_id),
            )

        overview = client.get(
            f"/orgs/{org_id}/analytics/overview", headers=_auth(recruiter["token"], org_id)
        ).json()

        assert overview["totals"]["applications"] == 1
        assert overview["totals"]["hired"] == 1
        assert overview["totals"]["avg_time_to_hire_days"] is not None
        assert len(overview["trend"]) == 30
        assert any(day["hires"] == 1 for day in overview["trend"])
        stage_names = {row["stage"] for row in overview["stage_distribution"]}
        assert "HIRED" in stage_names
        assert overview["source_breakdown"][0]["source"] == "DIRECT"
        assert overview["campaign_performance"][0]["applications"] == 1
        assert overview["top_postings"][0]["posting_id"] == posting["id"]

    def test_overview_is_gated_same_as_funnel(self, client, recruiter):
        from app.shared.rbac import SystemRole

        token = _register(client, "recruiter3@acme.com")
        client.post(
            f"/orgs/{recruiter['org_id']}/members",
            json={"email": "recruiter3@acme.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(recruiter["token"], recruiter["org_id"]),
        )
        resp = client.get(
            f"/orgs/{recruiter['org_id']}/analytics/overview",
            headers=_auth(token, recruiter["org_id"]),
        )
        assert resp.status_code == 403


class TestPhase2TenantIsolation:
    def test_cannot_search_another_orgs_candidates_search_endpoint(self, client, recruiter, candidate):
        other = _register(client, "other-rec@example.com")
        other_org = _create_org(client, other, name="Globex", slug="globex-p2")
        resp = client.get(
            f"/orgs/{recruiter['org_id']}/candidates/search",
            headers=_auth(other, recruiter["org_id"]),
        )
        assert resp.status_code == 404

    def test_cannot_read_another_orgs_analytics(self, client, recruiter):
        other = _register(client, "other-rec2@example.com")
        other_org = _create_org(client, other, name="Globex", slug="globex-p2b")
        resp = client.get(
            f"/orgs/{recruiter['org_id']}/analytics/funnel",
            headers=_auth(other, recruiter["org_id"]),
        )
        assert resp.status_code == 404
