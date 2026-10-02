"""Tests for the resume domain: upload/parse (heuristic fallback path, since
the configured LLM points at an unreachable local proxy in tests — this is
intentional and mirrors how prep_ai's LLM-with-fallback path is tested) and
profile import (wholesale replace semantics).
"""

import io

from tests.test_identity import _auth, _register

PASSWORD = "correct-horse-battery"

_SAMPLE_RESUME_TEXT = (
    "Priya Sharma\n"
    "Senior Backend Engineer\n"
    "priya.sharma@example.com | +1-415-555-0100\n\n"
    "Experienced Python and PostgreSQL developer with 6 years of experience "
    "building distributed systems and REST APIs.\n\n"
    "Skills: Python, PostgreSQL, Docker, Kubernetes\n"
)


def _upload_resume(client, token, *, filename="resume.txt", content=_SAMPLE_RESUME_TEXT, content_type="text/plain"):
    return client.post(
        "/me/resume/parse",
        files={"file": (filename, io.BytesIO(content.encode("utf-8")), content_type)},
        headers=_auth(token),
    )


class TestResumeParse:
    def test_parse_requires_authentication(self, client):
        resp = client.post(
            "/me/resume/parse",
            files={"file": ("resume.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert resp.status_code == 401

    def test_parse_falls_back_to_heuristic_and_extracts_skills(self, client):
        token = _register(client, "resume-parse@example.com")
        resp = _upload_resume(client, token)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["parsed_by"] == "heuristic"
        assert body["raw_text"] == _SAMPLE_RESUME_TEXT.strip()
        assert body["warnings"], "heuristic parses should warn the candidate to review carefully"
        assert body["char_count"] > 0
        assert body["resume_document_id"] > 0

        skills = {s["skill"] for s in body["parsed"]["skills"]}
        assert "python" in skills
        assert "postgresql" in skills
        assert "docker" in skills
        assert body["parsed"]["years_experience"] == 6

    def test_parse_rejects_unsupported_file_type(self, client):
        token = _register(client, "resume-badtype@example.com")
        resp = _upload_resume(client, token, filename="resume.exe", content_type="application/octet-stream")
        assert resp.status_code == 400

    def test_parse_rejects_empty_file(self, client):
        token = _register(client, "resume-empty@example.com")
        resp = _upload_resume(client, token, content="")
        assert resp.status_code == 400

    def test_parse_rejects_oversized_file(self, client):
        token = _register(client, "resume-huge@example.com")
        huge = "a" * (5 * 1024 * 1024 + 1)
        resp = _upload_resume(client, token, content=huge)
        assert resp.status_code == 400


class TestResumeImport:
    def _import_payload(self, **overrides):
        payload = {
            "headline": "Senior Backend Engineer",
            "summary": "Builds distributed systems.",
            "location": "Bangalore",
            "phone": "+1-415-555-0100",
            "work_authorization": "Citizen",
            "years_experience": 6,
            "resume_text": _SAMPLE_RESUME_TEXT,
            "skills": [{"skill": "Python", "years": 6}, {"skill": "PostgreSQL", "years": 4}],
            "work_experiences": [
                {
                    "company": "Acme Corp",
                    "title": "Senior Backend Engineer",
                    "location": "Remote",
                    "start_date": "2020-01",
                    "end_date": None,
                    "is_current": True,
                    "description": "Built distributed systems.",
                }
            ],
            "education": [
                {"institution": "State University", "degree": "B.Tech", "field": "CS", "start_year": 2012, "end_year": 2016}
            ],
        }
        payload.update(overrides)
        return payload

    def test_import_creates_profile_with_replaced_lists(self, client):
        token = _register(client, "resume-import@example.com")
        resp = client.post("/me/resume/import", json=self._import_payload(), headers=_auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["headline"] == "Senior Backend Engineer"
        assert {e["company"] for e in body["experiences"]} == {"Acme Corp"}
        assert {e["institution"] for e in body["education"]} == {"State University"}
        assert {s["skill"] for s in body["skills"]} == {"Python", "PostgreSQL"}

    def test_import_replaces_rather_than_appends(self, client):
        """A second import must not leave the first import's rows behind."""
        token = _register(client, "resume-reimport@example.com")
        client.post("/me/resume/import", json=self._import_payload(), headers=_auth(token))

        second_payload = self._import_payload(
            work_experiences=[
                {
                    "company": "Globex",
                    "title": "Staff Engineer",
                    "location": "Remote",
                    "start_date": "2023-01",
                    "end_date": None,
                    "is_current": True,
                    "description": "",
                }
            ],
            education=[],
            skills=[{"skill": "Go", "years": 2}],
        )
        resp = client.post("/me/resume/import", json=second_payload, headers=_auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert [e["company"] for e in body["experiences"]] == ["Globex"]
        assert body["education"] == []
        assert {s["skill"] for s in body["skills"]} == {"Go"}

    def test_import_requires_authentication(self, client):
        resp = client.post("/me/resume/import", json=self._import_payload())
        assert resp.status_code == 401
