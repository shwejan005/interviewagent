"""
Tests for the identity, RBAC, tenancy, and audit foundation.

The tenant-isolation tests in TestTenantIsolation are the most important in
this file. They are the executable form of the guarantee that two companies
using Evalia cannot see each other's data, and they are intended to run as a
CI gate — a failure here is a data breach, not a bug.
"""

import pytest

import database as db
import security
from rbac import Capability, SystemRole, capabilities_for_role


def _register(client, email, password="correct-horse-battery", name="Test User"):
    resp = client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def _auth(token, org_id=None):
    headers = {"Authorization": f"Bearer {token}"}
    if org_id is not None:
        headers["X-Org-Id"] = str(org_id)
    return headers


def _create_org(client, token, name="Acme", slug="acme"):
    resp = client.post("/orgs", json={"name": name, "slug": slug}, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ── Password hashing ─────────────────────────────────────────────────


class TestPasswordHashing:
    def test_roundtrip(self):
        h = security.hash_password("a-sufficiently-long-password")
        assert security.verify_password("a-sufficiently-long-password", h)

    def test_wrong_password_rejected(self):
        h = security.hash_password("a-sufficiently-long-password")
        assert not security.verify_password("something-else-entirely", h)

    def test_hash_is_salted(self):
        """Identical passwords must not produce identical hashes."""
        assert security.hash_password("same-password-here") != security.hash_password("same-password-here")

    def test_long_passwords_are_not_truncated(self):
        """bcrypt truncates at 72 bytes; the SHA-256 pre-hash must prevent that.

        Without pre-hashing, these two distinct passwords would collide because
        they share a 72-byte prefix.
        """
        base = "x" * 72
        h = security.hash_password(base + "AAAA")
        assert not security.verify_password(base + "BBBB", h)

    def test_malformed_stored_hash_denies_rather_than_raising(self):
        assert not security.verify_password("any-password-at-all", "not-a-bcrypt-hash")


# ── Tokens ───────────────────────────────────────────────────────────


class TestTokens:
    def test_roundtrip(self):
        token = security.create_access_token(4242)
        assert security.decode_access_token(token) == 4242

    def test_tampered_token_rejected(self):
        token = security.create_access_token(1)
        with pytest.raises(security.TokenError):
            security.decode_access_token(token[:-4] + "AAAA")

    def test_expired_token_rejected(self):
        from datetime import timedelta

        token = security.create_access_token(1, ttl=timedelta(seconds=-1))
        with pytest.raises(security.TokenError):
            security.decode_access_token(token)

    def test_garbage_rejected(self):
        with pytest.raises(security.TokenError):
            security.decode_access_token("not-a-token")


# ── Registration & login ─────────────────────────────────────────────


class TestRegistrationAndLogin:
    def test_register_then_login(self, client):
        _register(client, "alice@example.com")
        resp = client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": "correct-horse-battery"},
        )
        assert resp.status_code == 200
        assert resp.json()["token_type"] == "bearer"

    def test_duplicate_email_rejected(self, client):
        _register(client, "dupe@example.com")
        resp = client.post(
            "/auth/register",
            json={"email": "dupe@example.com", "password": "correct-horse-battery"},
        )
        assert resp.status_code == 409

    def test_email_is_case_insensitive_for_uniqueness(self, client):
        _register(client, "Case@Example.com")
        resp = client.post(
            "/auth/register",
            json={"email": "case@example.COM", "password": "correct-horse-battery"},
        )
        assert resp.status_code == 409

    def test_short_password_rejected(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "short@example.com", "password": "tiny"},
        )
        assert resp.status_code == 422

    def test_invalid_email_rejected(self, client):
        resp = client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "correct-horse-battery"},
        )
        assert resp.status_code == 422

    def test_wrong_password_and_unknown_email_are_indistinguishable(self, client):
        """Login must not act as an account-enumeration oracle."""
        _register(client, "real@example.com")
        wrong_password = client.post(
            "/auth/login", json={"email": "real@example.com", "password": "wrong-password-x"}
        )
        unknown_email = client.post(
            "/auth/login", json={"email": "ghost@example.com", "password": "wrong-password-x"}
        )
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json()["detail"] == unknown_email.json()["detail"]

    def test_me_requires_authentication(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_me_rejects_malformed_header(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401

    def test_new_account_is_a_candidate_with_no_memberships(self, client):
        token = _register(client, "fresh@example.com")
        body = client.get("/auth/me", headers=_auth(token)).json()
        assert body["active_role"] == str(SystemRole.CANDIDATE)
        assert body["memberships"] == []
        assert str(Capability.APPLICATION_SUBMIT) in body["capabilities"]
        # A candidate must never hold recruiter powers.
        assert str(Capability.CANDIDATE_SEARCH) not in body["capabilities"]


# ── Organizations & membership ───────────────────────────────────────


class TestOrganizations:
    def test_creator_becomes_owner(self, client):
        token = _register(client, "owner@example.com")
        org_id = _create_org(client, token)
        body = client.get("/auth/me", headers=_auth(token, org_id)).json()
        assert body["active_role"] == str(SystemRole.ORG_OWNER)
        assert body["active_org_id"] == org_id

    def test_duplicate_slug_rejected(self, client):
        token_a = _register(client, "a@example.com")
        token_b = _register(client, "b@example.com")
        _create_org(client, token_a, slug="taken")
        resp = client.post(
            "/orgs", json={"name": "Other", "slug": "taken"}, headers=_auth(token_b)
        )
        assert resp.status_code == 409

    def test_invalid_slug_rejected(self, client):
        token = _register(client, "slug@example.com")
        resp = client.post(
            "/orgs", json={"name": "Bad", "slug": "Not A Slug!"}, headers=_auth(token)
        )
        assert resp.status_code == 422

    def test_add_member_with_role(self, client):
        owner = _register(client, "owner2@example.com")
        _register(client, "recruiter@example.com")
        org_id = _create_org(client, owner, slug="org2")

        resp = client.post(
            f"/orgs/{org_id}/members",
            json={"email": "recruiter@example.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(owner, org_id),
        )
        assert resp.status_code == 201
        members = client.get(f"/orgs/{org_id}/members", headers=_auth(owner, org_id)).json()
        assert len(members["members"]) == 2

    def test_cannot_add_unregistered_user(self, client):
        owner = _register(client, "owner3@example.com")
        org_id = _create_org(client, owner, slug="org3")
        resp = client.post(
            f"/orgs/{org_id}/members",
            json={"email": "nobody@example.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(owner, org_id),
        )
        assert resp.status_code == 404

    def test_invalid_role_rejected(self, client):
        owner = _register(client, "owner4@example.com")
        _register(client, "member4@example.com")
        org_id = _create_org(client, owner, slug="org4")
        resp = client.post(
            f"/orgs/{org_id}/members",
            json={"email": "member4@example.com", "role": "supreme_leader"},
            headers=_auth(owner, org_id),
        )
        assert resp.status_code == 400

    def test_candidate_role_cannot_be_assigned_to_an_org(self, client):
        """CANDIDATE is not an org-scoped role and must be refused here."""
        owner = _register(client, "owner5@example.com")
        _register(client, "member5@example.com")
        org_id = _create_org(client, owner, slug="org5")
        resp = client.post(
            f"/orgs/{org_id}/members",
            json={"email": "member5@example.com", "role": str(SystemRole.CANDIDATE)},
            headers=_auth(owner, org_id),
        )
        assert resp.status_code == 400

    def test_cannot_remove_the_only_owner(self, client):
        owner = _register(client, "solo@example.com")
        org_id = _create_org(client, owner, slug="solo")
        me = client.get("/auth/me", headers=_auth(owner, org_id)).json()
        resp = client.delete(
            f"/orgs/{org_id}/members/{me['user_id']}", headers=_auth(owner, org_id)
        )
        assert resp.status_code == 409

    def test_cannot_demote_the_only_owner(self, client):
        owner = _register(client, "solo2@example.com")
        org_id = _create_org(client, owner, slug="solo2")
        me = client.get("/auth/me", headers=_auth(owner, org_id)).json()
        resp = client.patch(
            f"/orgs/{org_id}/members/{me['user_id']}",
            json={"role": str(SystemRole.RECRUITER)},
            headers=_auth(owner, org_id),
        )
        assert resp.status_code == 409


# ── Capability enforcement ───────────────────────────────────────────


class TestCapabilities:
    def test_recruiter_cannot_manage_members(self, client):
        owner = _register(client, "owner6@example.com")
        recruiter = _register(client, "recruiter6@example.com")
        org_id = _create_org(client, owner, slug="org6")
        client.post(
            f"/orgs/{org_id}/members",
            json={"email": "recruiter6@example.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(owner, org_id),
        )
        # A recruiter lacks ORG_MEMBER_INVITE.
        resp = client.post(
            f"/orgs/{org_id}/members",
            json={"email": "owner6@example.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(recruiter, org_id),
        )
        assert resp.status_code == 403

    def test_interviewer_capabilities_are_narrow(self):
        caps = capabilities_for_role(str(SystemRole.INTERVIEWER))
        assert Capability.INTERVIEW_CONDUCT in caps
        # An interviewer must not be able to browse the wider candidate pool.
        assert Capability.CANDIDATE_SEARCH not in caps
        assert Capability.APPLICATION_REJECT not in caps

    def test_candidate_has_no_recruiter_capabilities(self):
        caps = capabilities_for_role(str(SystemRole.CANDIDATE))
        for forbidden in (
            Capability.CANDIDATE_SEARCH,
            Capability.APPLICATION_ADVANCE,
            Capability.CAMPAIGN_CREATE,
            Capability.AUDIT_READ,
        ):
            assert forbidden not in caps

    def test_platform_admin_has_every_capability(self):
        caps = capabilities_for_role(str(SystemRole.PLATFORM_ADMIN))
        assert set(caps) == set(Capability)

    def test_owner_is_a_superset_of_admin(self):
        owner = capabilities_for_role(str(SystemRole.ORG_OWNER))
        admin = capabilities_for_role(str(SystemRole.ORG_ADMIN))
        assert admin.issubset(owner)
        assert Capability.ORG_DELETE in owner and Capability.ORG_DELETE not in admin


# ── Tenant isolation (CI gate) ───────────────────────────────────────


class TestTenantIsolation:
    """Two organizations must be completely invisible to each other."""

    @pytest.fixture
    def two_orgs(self, client):
        alice = _register(client, "alice@acme.com")
        bob = _register(client, "bob@globex.com")
        acme = _create_org(client, alice, name="Acme", slug="acme")
        globex = _create_org(client, bob, name="Globex", slug="globex")
        return {"alice": alice, "bob": bob, "acme": acme, "globex": globex}

    def test_cannot_read_another_orgs_settings(self, client, two_orgs):
        resp = client.get(
            f"/orgs/{two_orgs['globex']}", headers=_auth(two_orgs["alice"], two_orgs["globex"])
        )
        assert resp.status_code == 404

    def test_cannot_list_another_orgs_members(self, client, two_orgs):
        resp = client.get(
            f"/orgs/{two_orgs['globex']}/members",
            headers=_auth(two_orgs["alice"], two_orgs["globex"]),
        )
        assert resp.status_code == 404

    def test_cannot_add_members_to_another_org(self, client, two_orgs):
        resp = client.post(
            f"/orgs/{two_orgs['globex']}/members",
            json={"email": "alice@acme.com", "role": str(SystemRole.ORG_ADMIN)},
            headers=_auth(two_orgs["alice"], two_orgs["globex"]),
        )
        assert resp.status_code == 404

    def test_cross_tenant_denial_is_404_not_403(self, client, two_orgs):
        """403 would confirm the resource exists, enabling ID enumeration."""
        resp = client.get(
            f"/orgs/{two_orgs['globex']}", headers=_auth(two_orgs["alice"], two_orgs["globex"])
        )
        assert resp.status_code == 404
        assert "permission" not in resp.json()["detail"].lower()

    def test_own_org_still_accessible(self, client, two_orgs):
        """The isolation tests must not pass merely because everything is denied."""
        resp = client.get(
            f"/orgs/{two_orgs['acme']}", headers=_auth(two_orgs["alice"], two_orgs["acme"])
        )
        assert resp.status_code == 200
        assert resp.json()["slug"] == "acme"

    def test_membership_in_one_org_grants_nothing_in_another(self, client, two_orgs):
        me = client.get("/auth/me", headers=_auth(two_orgs["alice"], two_orgs["acme"])).json()
        assert me["active_role"] == str(SystemRole.ORG_OWNER)
        assert [m["org_id"] for m in me["memberships"]] == [two_orgs["acme"]]


# ── Audit trail ──────────────────────────────────────────────────────


class TestAuditTrail:
    def test_registration_and_login_are_audited(self, client, isolated_db):
        _register(client, "audited@example.com")
        client.post(
            "/auth/login",
            json={"email": "audited@example.com", "password": "correct-horse-battery"},
        )
        actions = {e["action"] for e in isolated_db.list_audit_events(limit=50)}
        assert "user.registered" in actions
        assert "user.login.succeeded" in actions

    def test_failed_login_is_audited_as_denied(self, client, isolated_db):
        _register(client, "failaudit@example.com")
        client.post(
            "/auth/login",
            json={"email": "failaudit@example.com", "password": "definitely-wrong"},
        )
        failures = [
            e for e in isolated_db.list_audit_events(limit=50)
            if e["action"] == "user.login.failed"
        ]
        assert len(failures) == 1
        assert failures[0]["outcome"] == "DENIED"

    def test_authorization_denial_is_audited(self, client, isolated_db):
        owner = _register(client, "owner7@example.com")
        recruiter = _register(client, "recruiter7@example.com")
        org_id = _create_org(client, owner, slug="org7")
        client.post(
            f"/orgs/{org_id}/members",
            json={"email": "recruiter7@example.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(owner, org_id),
        )
        client.post(
            f"/orgs/{org_id}/members",
            json={"email": "owner7@example.com", "role": str(SystemRole.RECRUITER)},
            headers=_auth(recruiter, org_id),
        )
        denials = [
            e for e in isolated_db.list_audit_events(limit=50)
            if e["action"] == "authz.denied"
        ]
        assert denials, "an authorization failure must leave an audit record"

    def test_hash_chain_is_valid(self, client, isolated_db):
        _register(client, "chain1@example.com")
        _register(client, "chain2@example.com")
        token = _register(client, "chain3@example.com")
        _create_org(client, token, slug="chainorg")

        result = isolated_db.verify_audit_chain()
        assert result["valid"] is True
        assert result["events_checked"] >= 4

    def test_tampering_breaks_the_chain(self, client, isolated_db):
        """An edited audit row must be detectable."""
        _register(client, "tamper1@example.com")
        _register(client, "tamper2@example.com")

        events = isolated_db.list_audit_events(limit=10)
        target = events[-1]
        with isolated_db._get_conn() as (conn, cur):
            cur.execute(
                f"UPDATE audit_events SET action = {isolated_db._ph()} WHERE id = {isolated_db._ph()}",
                ("user.registered.TAMPERED", target["id"]),
            )

        result = isolated_db.verify_audit_chain()
        assert result["valid"] is False
        assert result["broken_at_id"] == target["id"]

    def test_deleting_an_event_breaks_the_chain(self, client, isolated_db):
        _register(client, "del1@example.com")
        _register(client, "del2@example.com")
        _register(client, "del3@example.com")

        events = isolated_db.list_audit_events(limit=10)
        middle = events[len(events) // 2]
        with isolated_db._get_conn() as (conn, cur):
            cur.execute(
                f"DELETE FROM audit_events WHERE id = {isolated_db._ph()}", (middle["id"],)
            )

        assert isolated_db.verify_audit_chain()["valid"] is False


# ── Role seeding ─────────────────────────────────────────────────────


class TestRoleSeeding:
    def test_all_system_roles_are_seeded(self, isolated_db):
        for role in SystemRole:
            assert isolated_db.get_role_by_name(str(role)) is not None

    def test_seeding_is_idempotent(self, isolated_db):
        isolated_db.init_db()
        isolated_db.init_db()
        with isolated_db._get_conn() as (conn, cur):
            cur.execute("SELECT COUNT(*) AS c FROM roles")
            assert cur.fetchone()["c"] == len(SystemRole)


# ── Evaluation ownership retrofit ────────────────────────────────────


class TestEvaluationOwnership:
    """The existing pipeline must keep working unauthenticated, and must
    attribute ownership when credentials are present."""

    @staticmethod
    def _patch_agents(monkeypatch):
        import routes
        from tests.test_routes import (
            _behavioral_question, _screening, _technical_questions,
        )

        monkeypatch.setattr(routes, "run_screening", _screening())
        monkeypatch.setattr(routes, "run_technical_questions", _technical_questions)
        monkeypatch.setattr(routes, "run_behavioral_question", _behavioral_question)

    def test_unauthenticated_start_still_works_and_is_unowned(
        self, client, isolated_db, monkeypatch
    ):
        self._patch_agents(monkeypatch)
        resp = client.post(
            "/start",
            json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"},
        )
        assert resp.status_code == 200
        row = isolated_db.get_evaluation(resp.json()["evaluation_id"])
        assert row["org_id"] is None
        assert row["owner_user_id"] is None

    def test_authenticated_start_records_owner(self, client, isolated_db, monkeypatch):
        self._patch_agents(monkeypatch)
        token = _register(client, "candidate@example.com")
        me = client.get("/auth/me", headers=_auth(token)).json()

        resp = client.post(
            "/start",
            json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        row = isolated_db.get_evaluation(resp.json()["evaluation_id"])
        assert row["owner_user_id"] == me["user_id"]

    def test_org_scoped_start_records_org(self, client, isolated_db, monkeypatch):
        self._patch_agents(monkeypatch)
        token = _register(client, "recruiter-eval@example.com")
        org_id = _create_org(client, token, slug="evalorg")

        resp = client.post(
            "/start",
            json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"},
            headers=_auth(token, org_id),
        )
        assert resp.status_code == 200
        row = isolated_db.get_evaluation(resp.json()["evaluation_id"])
        assert row["org_id"] == org_id

    def test_authenticated_start_is_audited(self, client, isolated_db, monkeypatch):
        self._patch_agents(monkeypatch)
        token = _register(client, "audited-eval@example.com")
        client.post(
            "/start",
            json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"},
            headers=_auth(token),
        )
        actions = {e["action"] for e in isolated_db.list_audit_events(limit=50)}
        assert "evaluation.created" in actions

    def test_invalid_token_does_not_break_unauthenticated_path(self, client, monkeypatch):
        """A bad token must degrade to anonymous, not 500."""
        self._patch_agents(monkeypatch)
        resp = client.post(
            "/start",
            json={"resume": "r", "role": "Backend Developer", "candidate_name": "Jane"},
            headers={"Authorization": "Bearer garbage-token"},
        )
        assert resp.status_code == 200

