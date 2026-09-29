"""
Regression tests for database.py.

Covers the fixes behind CODEBASE_REVIEW.md findings:
- B04 (public access to sensitive records): resume_text must never appear in
  any projection used by list/detail endpoints.
- The N+1 verdict-summary query in the original /evaluations list handler:
  get_verdict_summaries must answer for many evaluations in one query.
- Canonical-verdict uniqueness: a second successful verdict for the same
  evaluation/round must be rejected, but a retry after a recorded
  INVALID_OUTPUT failure must still be allowed.
"""

import sqlite3

import pytest

from database import DuplicateVerdictError


SENSITIVE_MARKER = "UNIQUE_RESUME_MARKER_DO_NOT_LEAK_9f31"


def _make_evaluation(db, role="Backend Developer"):
    return db.create_evaluation(
        resume_text=f"Resume containing {SENSITIVE_MARKER}",
        role=role,
        candidate_name="Jane Doe",
    )


class TestPiiProjection:
    def test_get_evaluation_public_excludes_resume_text(self, isolated_db):
        eval_id = _make_evaluation(isolated_db)
        public = isolated_db.get_evaluation_public(eval_id)
        assert "resume_text" not in public
        assert public["candidate_name"] == "Jane Doe"

    def test_get_evaluation_internal_still_includes_resume_text(self, isolated_db):
        # Internal accessor is intentionally different — agents need the resume.
        eval_id = _make_evaluation(isolated_db)
        internal = isolated_db.get_evaluation(eval_id)
        assert SENSITIVE_MARKER in internal["resume_text"]

    def test_list_evaluations_excludes_resume_text(self, isolated_db):
        _make_evaluation(isolated_db)
        _make_evaluation(isolated_db)
        rows = isolated_db.list_evaluations()
        assert len(rows) == 2
        for row in rows:
            assert "resume_text" not in row


class TestSchemaMigrations:
    def test_schema_ledger_applies_current_version(self, isolated_db):
        with isolated_db._get_conn() as (conn, cur):
            cur.execute("SELECT version FROM schema_migrations ORDER BY version")
            assert [row["version"] for row in cur.fetchall()] == [1, 2, 3]

            cur.execute("PRAGMA table_info(agent_verdicts)")
            verdict_columns = {row["name"] for row in cur.fetchall()}
            assert {"attempt_id", "model_name", "usage_json", "completed_at"} <= verdict_columns

    def test_init_db_is_idempotent_after_migrations(self, isolated_db):
        isolated_db.init_db()
        with isolated_db._get_conn() as (conn, cur):
            cur.execute("SELECT COUNT(*) AS count FROM schema_migrations")
            assert cur.fetchone()["count"] == 3

    def test_legacy_sqlite_job_table_is_rebuilt_without_losing_rows(
        self, isolated_db, tmp_path, monkeypatch
    ):
        legacy_path = tmp_path / "legacy_evalia.db"
        monkeypatch.setattr(isolated_db, "_SQLITE_PATH", str(legacy_path))
        conn = sqlite3.connect(legacy_path)
        conn.execute(
            """CREATE TABLE background_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'PENDING',
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                available_at TEXT NOT NULL DEFAULT (datetime('now')),
                locked_at TEXT,
                locked_by TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                idempotency_key TEXT,
                CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'DEAD')),
                CHECK (attempts >= 0 AND max_attempts > 0)
            )"""
        )
        conn.execute(
            "INSERT INTO background_jobs (job_type, payload, idempotency_key) "
            "VALUES (?, ?, ?)",
            ("legacy", '{"value":1}', "legacy-key"),
        )
        conn.commit()
        conn.close()

        isolated_db.init_db()

        job = isolated_db.get_job(1)
        assert job["job_type"] == "legacy"
        assert job["payload"] == {"value": 1}
        assert job["tenant_key"] is None
        assert job["cancellation_requested"] == 0
        assert isolated_db.request_job_cancellation(1) is True
        assert isolated_db.get_job(1)["status"] == "CANCELLED"


class TestVerdictSummaryBatching:
    def test_batched_summaries_match_individual_lookups(self, isolated_db):
        eval_ids = [_make_evaluation(isolated_db) for _ in range(3)]
        for i, eid in enumerate(eval_ids):
            isolated_db.save_verdict(
                evaluation_id=eid,
                agent_type="screening",
                round_number=1,
                verdict_json={"decision": "PASS"},
                verdict_text="raw",
                score=float(i),
                decision="PASS",
                confidence=0.9,
            )

        summaries = isolated_db.get_verdict_summaries(eval_ids)

        assert set(summaries.keys()) == set(eval_ids)
        for i, eid in enumerate(eval_ids):
            assert len(summaries[eid]) == 1
            assert summaries[eid][0]["decision"] == "PASS"
            assert summaries[eid][0]["score"] == float(i)

    def test_batched_summaries_single_query_for_n_evaluations(self, isolated_db):
        """Proves the list endpoint no longer issues one query per evaluation (N+1)."""
        eval_ids = [_make_evaluation(isolated_db) for _ in range(5)]
        for eid in eval_ids:
            isolated_db.save_verdict(
                evaluation_id=eid,
                agent_type="screening",
                round_number=1,
                verdict_json={"decision": "PASS"},
                verdict_text="raw",
                score=8.0,
                decision="PASS",
                confidence=0.9,
            )

        query_count = 0
        real_get_conn = isolated_db._get_conn

        class _CountingCursor:
            def __init__(self, cur):
                self._cur = cur

            def execute(self, *args, **kwargs):
                nonlocal query_count
                query_count += 1
                return self._cur.execute(*args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._cur, name)

        from contextlib import contextmanager

        @contextmanager
        def counting_get_conn():
            with real_get_conn() as (conn, cur):
                yield conn, _CountingCursor(cur)

        isolated_db._get_conn = counting_get_conn
        try:
            isolated_db.get_verdict_summaries(eval_ids)
        finally:
            isolated_db._get_conn = real_get_conn

        assert query_count == 1

    def test_empty_id_list_returns_empty_dict_without_querying(self, isolated_db):
        assert isolated_db.get_verdict_summaries([]) == {}


class TestCanonicalVerdictUniqueness:
    def test_second_canonical_verdict_for_same_round_is_rejected(self, isolated_db):
        eval_id = _make_evaluation(isolated_db)
        isolated_db.save_verdict(
            evaluation_id=eval_id, agent_type="screening", round_number=1,
            verdict_json={"decision": "PASS"}, verdict_text="raw",
            score=8.0, decision="PASS", confidence=0.9,
        )
        with pytest.raises(DuplicateVerdictError):
            isolated_db.save_verdict(
                evaluation_id=eval_id, agent_type="screening", round_number=1,
                verdict_json={"decision": "PASS"}, verdict_text="raw again",
                score=7.0, decision="PASS", confidence=0.9,
            )

    def test_invalid_output_rows_do_not_block_a_later_canonical_verdict(self, isolated_db):
        eval_id = _make_evaluation(isolated_db)
        # Two failed agent executions recorded for triage...
        isolated_db.save_verdict(
            evaluation_id=eval_id, agent_type="screening", round_number=1,
            verdict_json={"error": "bad json"}, verdict_text="not json",
            score=None, decision="INVALID_OUTPUT", confidence=None,
        )
        isolated_db.save_verdict(
            evaluation_id=eval_id, agent_type="screening", round_number=1,
            verdict_json={"error": "bad json again"}, verdict_text="still not json",
            score=None, decision="INVALID_OUTPUT", confidence=None,
        )
        # ...then a genuine successful retry must still be allowed.
        isolated_db.save_verdict(
            evaluation_id=eval_id, agent_type="screening", round_number=1,
            verdict_json={"decision": "PASS"}, verdict_text="raw",
            score=8.0, decision="PASS", confidence=0.9,
        )
        canonical = isolated_db.get_verdict_by_round(eval_id, 1)
        assert canonical["decision"] == "PASS"

    def test_get_verdict_by_round_ignores_invalid_output(self, isolated_db):
        eval_id = _make_evaluation(isolated_db)
        isolated_db.save_verdict(
            evaluation_id=eval_id, agent_type="screening", round_number=1,
            verdict_json={"error": "bad json"}, verdict_text="not json",
            score=None, decision="INVALID_OUTPUT", confidence=None,
        )
        assert isolated_db.get_verdict_by_round(eval_id, 1) is None

    def test_verdict_persists_execution_metadata(self, isolated_db):
        eval_id = _make_evaluation(isolated_db)
        isolated_db.save_verdict(
            evaluation_id=eval_id,
            agent_type="screening",
            round_number=1,
            verdict_json={"decision": "PASS"},
            verdict_text="raw",
            score=8.0,
            decision="PASS",
            confidence=0.9,
            attempt_id="attempt-123",
            model_name="test-model",
            prompt_version="prompt-v2",
            rubric_version="rubric-v1",
            usage={"input_tokens": 10, "output_tokens": 5},
            error_type=None,
            deployment_provenance="test-suite",
        )

        verdict = isolated_db.get_verdict_by_round(eval_id, 1)
        assert verdict["attempt_id"] == "attempt-123"
        assert verdict["model_name"] == "test-model"
        assert verdict["usage_json"] == {"input_tokens": 10, "output_tokens": 5}
        assert verdict["deployment_provenance"] == "test-suite"
        assert verdict["error_type"] is None

    def test_pending_job_cancellation_is_terminal_without_claiming(self, isolated_db):
        job_id = isolated_db.enqueue_job("cancel-before-run", {})
        assert isolated_db.request_job_cancellation(job_id) is True
        job = isolated_db.get_job(job_id)
        assert job["status"] == "CANCELLED"
        assert job["attempts"] == 0


class TestEvaluationLifecycle:
    def test_create_and_update_roundtrip(self, isolated_db):
        eval_id = _make_evaluation(isolated_db)
        evaluation = isolated_db.get_evaluation(eval_id)
        assert evaluation["status"] == "IN_PROGRESS"
        assert evaluation["current_round"] == 1

        isolated_db.update_evaluation(eval_id, status="COMPLETE", current_round=5, final_decision="HIRE")
        updated = isolated_db.get_evaluation(eval_id)
        assert updated["status"] == "COMPLETE"
        assert updated["current_round"] == 5
        assert updated["final_decision"] == "HIRE"

    def test_count_evaluations_respects_status_filter(self, isolated_db):
        eval_id_1 = _make_evaluation(isolated_db)
        _make_evaluation(isolated_db)
        isolated_db.update_evaluation(eval_id_1, status="REJECTED")

        assert isolated_db.count_evaluations() == 2
        assert isolated_db.count_evaluations(status="REJECTED") == 1
        assert isolated_db.count_evaluations(status="IN_PROGRESS") == 1


class TestDurableBackgroundJobs:
    def test_enqueue_is_idempotent_and_payload_roundtrips(self, isolated_db):
        first = isolated_db.enqueue_job(
            "finalize_evaluation",
            {"evaluation_id": 42},
            idempotency_key="evaluation:42:finalize",
        )
        second = isolated_db.enqueue_job(
            "finalize_evaluation",
            {"evaluation_id": 42, "ignored": True},
            idempotency_key="evaluation:42:finalize",
        )

        assert first == second
        job = isolated_db.get_job(first)
        assert job["status"] == "PENDING"
        assert job["payload"] == {"evaluation_id": 42}

    def test_claim_complete_requires_the_claiming_worker(self, isolated_db):
        job_id = isolated_db.enqueue_job("example", {"value": 1})

        claimed = isolated_db.claim_next_job("worker-a")
        assert claimed["id"] == job_id
        assert claimed["status"] == "RUNNING"
        assert claimed["attempts"] == 1
        assert isolated_db.complete_job(job_id, "worker-b") is False
        assert isolated_db.get_job(job_id)["status"] == "RUNNING"
        assert isolated_db.complete_job(job_id, "worker-a") is True
        assert isolated_db.get_job(job_id)["status"] == "COMPLETED"

    def test_failed_job_retries_then_becomes_dead(self, isolated_db):
        job_id = isolated_db.enqueue_job("unstable", {}, max_attempts=2)

        isolated_db.claim_next_job("worker-a")
        assert isolated_db.fail_job(job_id, "worker-a", "first failure", retry_delay_seconds=0) == "PENDING"
        isolated_db.claim_next_job("worker-a")
        assert isolated_db.fail_job(job_id, "worker-a", "second failure", retry_delay_seconds=0) == "DEAD"
        job = isolated_db.get_job(job_id)
        assert job["attempts"] == 2
        assert job["last_error"] == "second failure"

    def test_claim_reclaims_expired_lease(self, isolated_db):
        job_id = isolated_db.enqueue_job("recoverable", {})
        isolated_db.claim_next_job("dead-worker", lease_seconds=1)

        with isolated_db._get_conn() as (conn, cur):
            cur.execute(
                "UPDATE background_jobs SET locked_at = datetime('now', '-10 minutes') WHERE id = ?",
                (job_id,),
            )

        reclaimed = isolated_db.claim_next_job("replacement-worker", lease_seconds=1)
        assert reclaimed["id"] == job_id
        assert reclaimed["attempts"] == 2
        assert reclaimed["locked_by"] == "replacement-worker"

    def test_expired_final_attempt_becomes_dead(self, isolated_db):
        job_id = isolated_db.enqueue_job("crashed", {}, max_attempts=1)
        isolated_db.claim_next_job("dead-worker", lease_seconds=1)

        with isolated_db._get_conn() as (conn, cur):
            cur.execute(
                "UPDATE background_jobs SET locked_at = datetime('now', '-10 minutes') WHERE id = ?",
                (job_id,),
            )

        assert isolated_db.claim_job(job_id, "replacement-worker", lease_seconds=1) is None
        assert isolated_db.get_job(job_id)["status"] == "DEAD"
