# Testing

## Summary

| Suite | Location | What it covers | Live LLM calls? | Last verified run |
|---|---|---|---|---|
| Backend automated tests | `backend/tests/` (pytest) | Output parsing/validation, database PII/uniqueness/batching, full route pipeline (mocked agents), identity/RBAC, marketplace, matching, invitations, scheduling, application screening, durable v1 admission/worker execution, prep suite, data export/deletion, contract harness, health/readiness, durable worker retries/cancellation/shutdown, structured event redaction | No | 221 passed, 0 failed, ~1m49s (2026-09-29) |
| Frontend type-check | `frontend/` (`npm run typecheck`) | TypeScript type safety across the whole `app/`/`components/` tree | N/A | 0 errors (2026-09-29) |
| Live agent smoke test | Ad hoc, not checked in (see below) | The actual CrewAI agents against a real LLM endpoint, end-to-end | **Yes** | Full happy path (PASS→PASS→PASS→HIRE) + reject path, verified manually 2026-09-27; not automated/repeatable as a checked-in test |

There is **no frontend browser/E2E test suite** (no Playwright/Cypress
config exists in this repository) and **no live-agent test in CI** (by
design — see below). Both are open items; see
[GAP_ANALYSIS.md](GAP_ANALYSIS.md).

## Running the backend suite

```powershell
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

Or with coverage:

```powershell
pytest -v --cov=. --cov-report=term-missing
```

### Why the suite never calls a live LLM

Every route-level test (`backend/tests/test_routes.py`) monkeypatches
`routes.run_screening`, `routes.run_technical_evaluation`, etc. — the exact
function references `routes.py` imported from `crew_runner.py` — with
deterministic async fakes that return a fixed, valid verdict shape. This
means:

- The suite runs in seconds, for free, with no API key and no network
  access, in any CI runner.
- It proves the **orchestration logic** in `routes.py` is correct
  (status transitions, idempotency, guard ordering, PII projection,
  duplicate/late-submission handling) — which is where the actual bugs
  documented in `CODEBASE_REVIEW.md` (B01, B03, B04, B05) lived.
- It does **not** prove the LLM will actually produce parseable,
  schema-valid JSON for a given prompt against a given model — that's a
  property of the model/prompt pairing, not of this code, and is exercised
  separately (see "Live agent smoke test" below).

### Test files

- `tests/conftest.py` — shared fixtures: `isolated_db` (fresh SQLite file
  per test via `tmp_path`, never the developer's real `backend/evalia.db`),
  `isolated_verdicts_dir` (fresh verdicts directory per test), `client` (a
  `TestClient` wired to both, using `with TestClient(main.app) as client:`
  so FastAPI's `lifespan` startup hook — `init_db()` — actually runs).
- `tests/test_crew_runner_parsing.py` — unit tests for
  `crew_runner._parse_json_output` / `_validate_verdict`: invalid JSON,
  markdown-fenced JSON, JSON surrounded by prose, out-of-range scores,
  unknown decision enum values, missing required fields (including
  confidence — there is no silent default). These are the direct regression
  tests for `CODEBASE_REVIEW.md` finding B03 ("model failures become
  candidate judgments").
- `tests/test_database.py` — PII projection (`resume_text` never appears in
  any public query result), batched verdict-summary fetching (proves a
  single query answers for N evaluations, not N queries — the fix for the
  original N+1 pattern in the `/evaluations` list handler), and the
  canonical-verdict uniqueness constraint (including that `INVALID_OUTPUT`
  rows never block a legitimate retry).
- `tests/test_routes.py` — full HTTP-level pipeline tests via `TestClient`:
  a complete PASS→PASS→PASS→HIRE happy path including idempotent
  `/final-decision` replay; rejection short-circuiting (proves later-stage
  agents are never invoked once an evaluation is rejected, using an
  assertion-raising fake in place of the agent function); `AgentOutputError`
  handling (proves a malformed agent response yields HTTP 502 and a
  `decision="INVALID_OUTPUT"` row, never a business decision); 404/409/400
  guard behavior; PII-safety of list/detail/report responses.
- `tests/test_rate_limit.py` — the `InMemoryRateLimitMiddleware` in
  isolation, against a minimal Starlette app (no database, no agents, no
  crewai import — this file alone runs in ~2–3 seconds).
- `tests/test_health.py` — process-only `/healthz`, database-backed `/readyz`,
  and the `503` behavior before startup completion or when the database probe
  fails.
- `tests/test_job_worker.py` — durable claim/outcome behavior, retry and
  cancellation transitions, and cooperative stop-event shutdown that drains
  a currently claimed job before exiting.
- `tests/test_observability.py` — stable JSON execution-event fields and the
  guarantee that job payloads such as resumes and answers are not logged.
- `tests/test_hardening.py` — scoped legacy evaluations, recruiter-search
  projection, assignment boundaries, minimum-only matching, and zero-rate
  bias monitoring.
- `tests/test_invitations_and_interviews.py` — invitation acceptance, email
  matching, scheduled interview participants, candidate agenda, duplicate
  scheduling, and cancellation.
- `tests/test_durable_pipeline.py` — 202 responses, durable screening
  admission, worker advancement, and scoped status access.
- `tests/test_prep.py` — topic catalog, roadmap ownership, progress XP, and
  explicit unverified submission behavior.
- `tests/test_data_subject.py` — authenticated export, last-owner protection,
  and account anonymization.
- `tests/test_evaluation_harness.py` — versioned deterministic contract rules
  and replayable starter fixtures.

### Disabling the rate limiter in tests

`conftest.py` sets `os.environ.setdefault("RATE_LIMIT_REQUESTS", "0")`
**before** any test imports `main.py`, because `main.py` reads that
variable once at import time to configure the middleware. Route/business
logic tests are not testing the rate limiter — that's `test_rate_limit.py`'s
job, using its own minimal app instance.

## Running the frontend type-check

```powershell
cd frontend
npm install   # first time only
npm run typecheck
```

No output means success (exit code 0). See [SETUP.md](SETUP.md) for why
`next build` itself is not a reliable check in a network-restricted
environment, and why a bare `npx tsc` should not be used here.

## Live agent smoke test (manual, not automated)

To validate the actual agents against a real LLM end-to-end (not just the
orchestration logic), drive the real FastAPI app with `TestClient` but do
**not** monkeypatch `crew_runner`'s `run_*` functions, so real
`Crew.kickoff()` calls happen against whatever `agents.py`'s `LLM_MODEL`
currently points at (Gemini or the local proxy — see
[ARCHITECTURE.md](ARCHITECTURE.md)).

This was done manually during the 2026-09-27 engagement and is not a
checked-in, repeatable test, for two reasons: (1) it costs real LLM calls
(time and possibly money) on every run, and (2) the technical/behavioral
question *text* is regenerated fresh by the LLM every run based on the
resume/role/prior verdicts — a hardcoded answer string written for one
run's specific questions will not reliably match a different run's
questions, so a naive "assert PASS" test is flaky by construction unless
the answer is either (a) read back from the actual generated question text
before being submitted, or (b) written broadly enough to plausibly address
any likely question on the topic. Findings from that manual run:

- Full pipeline (screening → technical → behavioral → recommendation →
  committee) completed successfully end-to-end against a real LLM, reaching
  a `HIRE` decision with `overall_score: 8.2`, `confidence: 0.93`.
- `/final-decision` called twice returned an identical result (idempotent
  replay confirmed against a real run, not just the mocked test).
- The rejection path (round 1 PASS, round 2 FAIL) was also confirmed live:
  the technical agent correctly identified an incomplete answer and
  rejected it with a specific, legible reasoning string.
- A non-blocking, cosmetic issue was observed: CrewAI's console event-bus
  logger throws `'charmap' codec can't encode...` on Windows when agent
  output contains smart quotes/em-dashes, because the default Windows
  console codepage isn't UTF-8. This is caught internally by CrewAI and
  never affects the actual HTTP response — it's log noise, not a functional
  bug. Not yet fixed; a `PYTHONIOENCODING=utf-8` environment variable would
  likely resolve it if it becomes a real problem in production logs.

There is no scheduled/CI version of this test. Building one is exactly the
"protected nightly benchmark run" concept described in
`PRODUCTION_ROADMAP.md` section 5 ("Offline, pre-release, and online
loop") — not implemented; see [GAP_ANALYSIS.md](GAP_ANALYSIS.md) P3.

## What is explicitly not tested

Documented here so it isn't mistaken for an oversight during review:

- **Concurrency/load testing** — no test exercises two truly concurrent
  requests racing on the same evaluation (the `DuplicateVerdictError` path
  is tested by *simulating* the race — manually resetting `current_round`
  between two sequential requests — not by firing genuinely parallel
  requests).
- **Real PostgreSQL** — the entire suite runs against SQLite. `database.py`
  has a PostgreSQL code path, but it has not been exercised by an automated
  test in this repository (`PRODUCTION_ROADMAP.md` explicitly calls out that
  "SQLite is not proof of concurrency/SQL parity").
- **Frontend component/browser tests** — no Vitest/Jest/Playwright config
  exists; only `tsc` type-checking is automated for the frontend.
- **Accessibility testing** — a few concrete accessibility lint findings
  were fixed during this documentation pass (label/control association,
  non-interactive click handlers, array-index React keys — see
  [CHANGELOG.md](CHANGELOG.md)), but there is no automated accessibility
  test (e.g. axe-core) verifying this doesn't regress.
- **Security testing** — no automated authorization/tenant-isolation tests
  exist, because there is no authorization/tenant isolation implemented yet
  (see [SECURITY.md](SECURITY.md)).
- **Distributed observability** — worker lifecycle JSON events are tested
  locally, but there is no OpenTelemetry trace, external observability
  destination, alert, or crash/restart integration test yet.
