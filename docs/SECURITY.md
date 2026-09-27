# Security posture

This document maps every finding in `CODEBASE_REVIEW.md` to its **current**
status, plus controls added since that review. It is written to be honest
about what is and isn't protected — do not deploy this publicly based on an
assumption that anything not listed as "fixed" below has been addressed.

## Summary judgment

**This system has no authentication, no authorization, and no
multi-tenancy.** Anyone who can reach the API can read every candidate's
evaluation data (except raw resume text, which is now excluded from
responses — see B04 below) and can trigger paid LLM calls. It is suitable
for a local demo, a single trusted operator, or a controlled pilot behind a
separate access-control layer (e.g. a VPN, a reverse proxy with basic auth,
or run entirely on `localhost`) — **not** for public internet exposure.

## `CODEBASE_REVIEW.md` findings — status

| ID | Finding | Status | Evidence |
|---|---|---|---|
| B01 | Reset creates two different state objects — a reset/start could lose the evaluation linkage used by later persistence | **Fixed** | `state.py` no longer holds any mutable session dictionary; the database is the sole source of truth per `evaluation_id`. Structurally impossible to reintroduce this specific bug without reintroducing a global mutable object. |
| B02 | Shared state and verdict files mix unrelated interviews | **Fixed** | Every evaluation's verdict files live under `backend/verdicts/{evaluation_id}/`, keyed by the DB-assigned ID (`state.eval_verdicts_dir`). |
| B03 | Model failures become candidate judgments (invalid JSON → fabricated FAIL; missing fields → fabricated defaults) | **Fixed** | `crew_runner._parse_json_output`/`_validate_verdict` raise `AgentOutputError` for any parse/schema failure; callers persist `decision="INVALID_OUTPUT"` and return HTTP 502 — never a business decision. Regression-tested in `backend/tests/test_crew_runner_parsing.py` and `test_routes.py::TestInvalidAgentOutputNeverBecomesADecision`. |
| B04 | Public access to sensitive records (raw resume text returned by list/detail endpoints); no request authentication at all | **Partially fixed.** Resume-text exposure is fixed. Authentication/authorization is **not** implemented. | `database._EVALUATION_SUMMARY_COLUMNS` excludes `resume_text`; every public-facing query uses it. Verified in `backend/tests/test_database.py::TestPiiProjection` and `test_routes.py::TestPiiSafety`. **No auth of any kind exists** — every endpoint is reachable by anyone who can reach the port. |
| B05 | Workflow transitions and commits are not protected (no idempotency key, no expected-round check, duplicate/out-of-order requests can corrupt history) | **Fixed** (for the single-writer-per-round case). | `routes.py` checks expected `current_round` (409 if wrong) and canonical-verdict existence (409 if already evaluated) before running any agent; `database.uq_verdicts_canonical` (a partial unique index) makes a second canonical verdict for the same evaluation/round a rejected `DuplicateVerdictError`, not a silent overwrite. `/final-decision` is idempotent by design (replays the persisted result). Verified in `test_routes.py::TestGuardsAndErrorHandling` and `test_database.py::TestCanonicalVerdictUniqueness`. |
| B06 | Long-running work is tied to HTTP lifetime; synchronous DB calls block the event loop; no durable queue/recovery | **Partially fixed.** Event-loop blocking is fixed. Durable queue/recovery is **not** implemented. | Every `database.py` call from `routes.py` is wrapped in `asyncio.to_thread` via the `_db()` helper, so synchronous `sqlite3`/`psycopg2` calls no longer block the event loop. There is still no durable job queue: a crashed backend process during an in-flight agent call loses that request (the DB row survives at its last committed state, but the client must retry). |
| Q01 | Committee is not truly independent verification (same model config, sees prior judgments, no evidence re-derivation) | **Unchanged / open.** | Bias isolation via explicit context passing (no resume/raw answers reach rounds 4–5) is real and unchanged — see [ARCHITECTURE.md](ARCHITECTURE.md). No evidence-grounded re-verification or baseline-vs-committee benchmark exists. |
| Q02 | No agreed/versioned scoring rubric; vague `culture_fit` inference | **Unchanged / open.** | `state.AVAILABLE_ROLES` is still a flat string list, not a versioned rubric. `tasks.py`'s `BEHAVIORAL_SCHEMA` still includes a `culture_fit` score. |
| Q03 | Confidence is not calibrated; landing page overclaimed calibration | **Partially addressed.** | `models.py` requires every verdict to include `confidence` explicitly (Pydantic `Field(...)`, no default) — an agent can no longer silently omit it and get a fabricated `0.8`. It is still a **self-reported, uncalibrated** value, not a measured probability of correctness. No calibration dataset/procedure exists. |
| Q04 | Overall scoring double-counted the recommendation's own synthesized score | **Fixed** | `routes.py`'s `/final-decision` handler averages only rounds 1–3's scores, explicitly excluding round 4 (see code comment and [API_REFERENCE.md](API_REFERENCE.md)). |
| Q05 | No system evaluation harness (benchmark cases, human labeling, grader validation, release gates) | **Unchanged / open.** | Not implemented. This remains the single largest gap versus `PRODUCTION_ROADMAP.md` — see [GAP_ANALYSIS.md](GAP_ANALYSIS.md) P3. |
| Q06 | Prompt injection / evidence laundering (resumes/answers/prior outputs interpolated as untrusted text into prompts) | **Unchanged / open.** | `tasks.py` still interpolates resume/answer/prior-verdict text directly into task descriptions with no sanitization or injection defenses. No adversarial test exists. |
| Q07 | Logs/records are not an immutable audit system; internal exception text was returned to clients; README overclaimed "immutable audit trail" | **Partially fixed.** | `main.py`'s global exception handler now returns a generic message to the client for any unhandled exception and logs the real one server-side only (fixes the info-disclosure half of this finding). Verdict records are still not a tamper-evident/append-only audit log — a `DELETE`/`UPDATE` against `agent_verdicts` is not prevented or detected at the database level. |

## Controls added since the review (this documentation/hardening pass)

These were not present at `CODEBASE_REVIEW.md`'s review date and are new as
of 2026-09-27:

- **Basic in-memory rate limiting** (`backend/rate_limit.py`,
  `InMemoryRateLimitMiddleware`): a fixed-window, per-client-IP request
  counter, default 60 requests/60s, configurable via `RATE_LIMIT_REQUESTS`
  / `RATE_LIMIT_WINDOW_SECONDS`, disableable via `RATE_LIMIT_REQUESTS=0`.
  **Honest scope:** single-process only (no shared state across multiple
  backend workers/instances); not a substitute for authentication, per-user
  quotas, or a real spend budget. See [ARCHITECTURE.md](ARCHITECTURE.md#rate-limiting).
- **Startup configuration validation** (`main.py`'s `_validate_startup_config`):
  warns (does not block startup) on an insecure `CORS_ORIGINS=*` +
  credentialed-CORS combination, on `APP_ENV=production` without
  `DATABASE_URL` (silently falls back to unvalidated-for-concurrency
  SQLite), and on `APP_ENV=production` without `GEMINI_API_KEY` (a hint that
  the hardcoded local-proxy override in `agents.py` may be left in place
  unintentionally).
- **Git hygiene**: three git-tracked, stale generated verdict `.txt` files
  under the old flat `backend/verdicts/round{1,2,3}.txt` path (predating the
  per-evaluation subdirectory fix) were removed from tracking. They
  contained what appears to be a real candidate's resume-screening output —
  exactly the kind of accidental sensitive-data commit `CODEBASE_REVIEW.md`
  flagged as a concern. Note: this removes them from the current tree and
  future commits; it does **not** purge them from prior git history — a
  history rewrite (e.g. `git filter-repo`) would be required for that, and
  was intentionally not performed without explicit authorization (a
  destructive, hard-to-reverse operation on shared history).

## Explicitly open gaps (not addressed in this pass)

In priority order for anyone planning to expose this beyond a local/trusted
environment:

1. **Authentication and per-tenant authorization.** Nothing currently
   verifies who is calling any endpoint. `PRODUCTION_ROADMAP.md` P1/T007
   proposes a managed OIDC/session provider; this requires an external
   identity provider decision and credentials this engagement does not
   have — it was not implemented here.
2. **Spend/abuse budgets beyond the basic rate limiter above.** No
   per-tenant or global LLM spend cap exists; the rate limiter only bounds
   *request count*, not cost.
3. **A real evaluation/grading harness for the agents themselves** (Q05
   above) — the single biggest differentiator described in
   `PRODUCTION_ROADMAP.md` section 5, entirely unimplemented.
4. **Prompt-injection defenses** (Q06) — no sanitization, delimiter
   strategy, or adversarial test suite exists for resume/answer content
   passed into agent prompts.
5. **Tamper-evident audit logging** (Q07, remaining half) — verdict rows
   can be modified or deleted with a normal `UPDATE`/`DELETE` and nothing
   would detect it.
6. **Schema migrations** — see [DATA_MODEL.md](DATA_MODEL.md); `CREATE TABLE
   IF NOT EXISTS` on every boot is not a substitute for versioned,
   reviewable migrations, especially once real data exists in production.
