"""
Shared pytest fixtures for the Evalia backend test suite.

Design constraints these fixtures enforce:

1. No test in this suite ever calls a live LLM (Gemini or the local
   OpenAI-compatible proxy in agents.py). Route-level tests monkeypatch
   crew_runner's public ``run_*`` functions with deterministic fakes, so the
   suite is fast, free, and reproducible in CI without any API key.
2. Every test gets a throwaway SQLite database file (never the developer's
   real backend/evalia.db) and a throwaway verdicts directory, so tests
   never leave state behind and can run in parallel-safe isolation.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Disable the in-memory rate limiter for the deterministic test suite. It is
# read once at main.py import time, so this must be set before the first
# `import main` anywhere in the suite. Route/business-logic tests are not
# testing the rate limiter — see test_rate_limit.py for that in isolation.
os.environ.setdefault("RATE_LIMIT_REQUESTS", "0")

import pytest  # noqa: E402


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point database.py at a fresh, throwaway SQLite file for this test only."""
    import database

    db_path = tmp_path / "test_evalia.db"
    monkeypatch.setattr(database, "_SQLITE_PATH", str(db_path))
    database.init_db()
    return database


@pytest.fixture
def isolated_verdicts_dir(tmp_path, monkeypatch):
    """Point state.py's verdict-file storage at a throwaway directory."""
    import state

    verdicts_dir = tmp_path / "verdicts"
    monkeypatch.setattr(state, "VERDICTS_DIR", str(verdicts_dir))
    return str(verdicts_dir)


@pytest.fixture
def client(isolated_db, isolated_verdicts_dir, monkeypatch):
    """A FastAPI TestClient wired to the isolated DB/verdicts fixtures above.

    Uses the ``with`` form so the app's lifespan (``init_db()`` on startup)
    actually executes — omitting ``with`` skips lifespan and produces a
    misleading "no such table" error that looks like an application bug.
    """
    import main
    from fastapi.testclient import TestClient

    with TestClient(main.app) as test_client:
        yield test_client
