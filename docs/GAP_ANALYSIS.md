# Gap analysis: roadmap vs. actual implementation

This document is the literal "compare and contrast" deliverable: every
phase and task ID from `PRODUCTION_ROADMAP.md` (section 10, "Phased
implementation plan and task breakdown"), checked against the actual
current state of the code, with concrete evidence for each verdict.

**Status legend:** ✅ Done · 🟡 Partial · ⬜ Not started

## P0 — Establish a trustworthy baseline

| Task | Status | Evidence |
|---|---|---|
| T001 — Capture current API contract + synthetic successful/failing flows | ✅ Done | [API_REFERENCE.md](API_REFERENCE.md) documents every endpoint's request/response/status codes from source; `backend/tests/test_routes.py` exercises both successful (`TestHappyPath`) and failing (`TestRejectionShortCircuit`, `TestInvalidAgentOutputNeverBecomesADecision`, `TestGuardsAndErrorHandling`) flows as executable tests, not just prose. |
| T002 — Isolated regression tests for stale-state binding and malformed verdict cases | ✅ Done (for malformed verdicts) / **N/A for stale-state binding** | `backend/tests/test_crew_runner_parsing.py` directly regression-tests every malformed-verdict case from `CODEBASE_REVIEW.md` B03 (invalid JSON, out-of-range score, unknown enum, missing confidence). The "stale-state binding" bug (B01) required a process-global mutable dictionary to exist at all; that mechanism was removed entirely in the prior engineering pass (see [ARCHITECTURE.md](ARCHITECTURE.md#why-session-context-changed)), so the specific bug class is structurally impossible to reintroduce without reintroducing the removed mechanism — there is nothing left to regression-test directly. |
| T003 — Canonical test/lint commands, pinned runtime policy, reproducible deps, PR validation | 🟡 Partial | Added: `backend/pytest.ini`, `backend/requirements-dev.txt`, `frontend`'s `npm run typecheck` script, and `.github/workflows/ci.yml` (runs both on every push/PR). **Not done:** a real dependency lockfile for Python (`requirements.txt` uses version *ranges*, not pins — e.g. `fastapi>=0.115.0,<1.0.0` — so two installs on different days can resolve different exact versions); no `engines` field pinning Node version in `frontend/package.json`. |
| T004 — Reconcile product claims in README/page.tsx; remove sensitive/generated material from tracking | ✅ Done | Root `README.md` rewritten to describe actual current behavior (see below). `frontend/app/page.tsx` marketing copy corrected: removed the false "calibrated confidence" claim, removed the unverified "<2m processing time" stat, corrected the "Gemini + SQLite only" architecture FAQ answer. Three git-tracked, stale, real-looking resume-content verdict files under `backend/verdicts/round{1,2,3}.txt` were removed from tracking (see [CHANGELOG.md](CHANGELOG.md)). |

## P1 — Safety and multi-user correctness

| Task | Status | Evidence |
|---|---|---|
| T005 — Evaluation-scoped persistence replacing runtime dict/files | ✅ Done (prior pass) | `state.py` holds only constants; every route re-derives state from `database.py` keyed by `evaluation_id`. Verified live: `backend/tests/test_routes.py` runs the full pipeline through `TestClient` with no shared mutable state between tests. |
| T006 — Versioned schema migrations, stage attempts, canonical-result uniqueness, state versions | 🟡 Partial | Canonical-result uniqueness: ✅ done (`uq_verdicts_canonical` partial unique index, tested). Versioned schema migrations: ✅ initial ledger done — `backend/migrations.py` records ordered versions and migration 3 preserves legacy job rows while adding the `CANCELLED` state. Tenant/owner columns, per-question IDs, answer *versions*, stage-attempt records, and state versions: ⬜ not done — see [DATA_MODEL.md](DATA_MODEL.md). |
| T007 — Managed identity + object/tenant-level permissions | ⬜ Not started | No authentication or authorization exists anywhere in `routes.py`. This requires selecting and integrating an external identity provider (the roadmap suggests evaluating Managed Better Auth or an OIDC provider) — a product/infrastructure decision and credentials this engagement does not have. See [SECURITY.md](SECURITY.md). |
| T008 — Strict verdict schemas/enums; validate outputs; remove fallbacks | ✅ Done (prior pass) | `models.py` uses real `Enum` types for every decision field; `crew_runner._validate_verdict` raises `AgentOutputError` on any schema violation instead of falling back to a default. Regression-tested. |
| T009 — Idempotency + expected-stage/version guards; finalize as a command; GETs read-only | 🟡 Partial | Expected-round guards (409) and canonical-verdict-exists guards (409): ✅ done and tested. `/final-decision` idempotent replay: ✅ done and tested. **Remaining gap:** `/final-decision` is still a `GET` that performs paid mutating work (runs two agents, writes to the DB) on first call — the roadmap's recommendation to make finalization an explicit `POST` command was not applied, to avoid a breaking API change during this pass. Expected-*version* guards (optimistic concurrency beyond round-number checks) do not exist. |
| T010 — Centralized settings validation, remove raw internal errors, input size limits, abuse/spend limits, summary-only list data | 🟡 Partial | Raw internal errors: ✅ done (prior pass — global exception handler returns a generic message). Input size limits: ✅ done (prior pass — `StartRequest`/`AnswerRequest` have `max_length` bounds). Summary-only list projections: ✅ done (prior pass — `resume_text` excluded). **New in this pass:** basic startup config validation (`main.py`'s `_validate_startup_config`) and a basic in-memory per-IP rate limiter (`rate_limit.py`) — see [SECURITY.md](SECURITY.md) for their honest scope. **Still missing:** per-tenant/global LLM *spend* budgets (the rate limiter bounds request count, not cost), and a real centralized settings/validation layer (e.g. `pydantic-settings`, which is already an installed transitive dependency but not used for this purpose). |

## P2 — Durable execution and basic observability

| Task | Status | Evidence |
|---|---|---|
| T011 — Separate admission from execution; durable worker/job repository; atomic claims/leases | 🟡 Partial | `database.py` now persists `background_jobs` with idempotency keys, atomic SQLite/PostgreSQL claims, leases, retries, and dead-letter status; `job_worker.py` provides `run_once`/`run_forever`; finalization is resumable through round-4/5 checkpoints. The final-decision route can still execute the claimed job inline for backward compatibility, and screening/technical/behavioral stages are not yet admitted to jobs. Heartbeats and explicit graceful shutdown remain open. |
| T012 — Per-stage deadlines, typed transient errors, bounded backoff+jitter, tenant concurrency, cancellation, dead-letter | 🟡 Partial | `crew_runner.py` now labels stages, classifies provider/rate-limit/timeout failures, applies capped exponential jitter, and enforces a configurable stage deadline. `job_worker.py` applies bounded retry jitter, persists cancellation requests, releases cancelled claims, and dead-letters `AgentOutputError` failures. Tenant-aware scheduling, lease heartbeats, cooperative in-flight cancellation tokens, and manual dead-letter recovery are still open. |
| T013 — Persist attempt IDs, model/prompt/rubric versions, usage, errors, deployment provenance | 🟡 Partial | `agent_verdicts` rows now persist generated attempt IDs, model name, prompt/rubric labels, optional usage JSON, typed error classification, start/completion timestamps, and deployment provenance. Automatic provider usage extraction/cost accounting and a normalized stage-attempt history remain open. |
| T014 — Instrument request→queue→worker→model→validator→DB spans; connect an observability destination | ⬜ Not started | Only Python `logging` calls exist; no distributed tracing (OpenTelemetry or similar), no external observability platform connected. |
| T015 — Liveness/readiness, graceful worker shutdown, alerts+runbooks, crash/restart recovery proof | ⬜ Not started | No `/healthz`/`/readyz` endpoints exist beyond the informational `GET /`. No worker process exists to shut down gracefully (there is no separate worker — see T011). |

**P2 assessment:** partially implemented. Durable finalization and core retry
controls now exist, but the first three rounds still run in HTTP requests and
the worker lacks heartbeats, tenant concurrency controls, tracing, readiness,
and graceful shutdown. The phase is not production-certified.

## P3 — Evidence, rubrics and evaluation harness

| Task | Status | Evidence |
|---|---|---|
| T016 — Versioned, anchored role rubric; replace vague scoring | ⬜ Not started | `state.AVAILABLE_ROLES` is still a flat list of ten role-name strings, not a versioned rubric with anchors/forbidden-inference rules. `tasks.py`'s prompts are unchanged. |
| T017 — Evidence-span/reference validation; deterministic aggregation rule | 🟡 Partial | The overall-score double-counting bug (roadmap's Q04) is fixed (aggregation now explicitly excludes round 4's own score — see [SECURITY.md](SECURITY.md) Q04 row). Evidence-span/citation validation (verifying a claimed quote actually appears in the source answer) does not exist. |
| T018 — Provider-neutral evaluation adapter + TypeScript deterministic grader/runner package | ⬜ Not started | No such package exists in `frontend/` or elsewhere. |
| T019 — Curate/version first benchmark cases; multi-reviewer labeling; dev/validation/holdout splits | ⬜ Not started | No benchmark dataset of any size exists in this repository. |
| T020 — Validate semantic judges against adjudicated labels; baseline/no-committee comparison | ⬜ Not started | No judge-validation or baseline-comparison experiment exists. |
| T021 — Protected live-provider release-gate runs alongside deterministic PR tests | ⬜ Not started | CI (`ci.yml`, added this pass) runs only the free, mocked-agent test suite — intentionally, so it needs no API key/secret and can't rack up LLM spend on every PR. A separate, budget-capped, secret-gated live-provider workflow does not exist. |

**P3 assessment:** unstarted. This is explicitly called out in
`PRODUCTION_ROADMAP.md` itself as "the primary differentiator" and the
single largest, most valuable remaining body of work — and also the one
most dependent on product decisions (which rubric, which judge model, how
many cases, who labels them) that cannot be made unilaterally by an
automated pass over the code.

## P4 — Candidate recovery and human review

| Task | Status | Evidence |
|---|---|---|
| T022 — Server-owned flow, evaluation-scoped URLs, typed contracts, draft recovery | 🟡 Partial | `evaluation_id` is now passed explicitly on every mutating request (prior pass fixed the frontend to do this via `sessionStorage`-held IDs) instead of relying on a shared session. **Still missing:** the ID lives in `sessionStorage`, not the URL (so a shared link or a page reload after closing the tab loses it — `sessionStorage` survives reload but not a closed tab); there is no server-side draft-recovery mechanism if the browser state is lost mid-round; API response types are still `any` in places (e.g. `verdict: any` in `result/page.tsx`), not generated/shared typed contracts. |
| T023 — Queued/running/retry/review states; accessible forms; no unintended answer carryover | 🟡 Partial | Three concrete accessibility fixes were made this pass (form label/control association via `htmlFor`/`fieldset`+`legend`, a non-interactive `div` with a click handler converted to a `<button>`, non-stable React list keys replaced) in `interview/page.tsx`, `round/[id]/page.tsx`, and `result/page.tsx` — see [CHANGELOG.md](CHANGELOG.md). No loading state exists beyond a simple `loading` boolean disabling the form; there's no distinct "queued"/"retry"/"under review" UI state (there's nothing to be "queued" behind, since P2's durable queue doesn't exist). No test proves answers don't carry over between rounds/questions. |
| T024 — Dashboard detail → evidence review with approve/correct/escalate + attributed history | ⬜ Not started | `app/dashboard/[id]/page.tsx` remains a read-only detail view; there is no reviewer action (approve/correct/escalate) or amendment-history concept anywhere in the schema or UI. |
| T025 — Server-side search/filter/pagination on the dashboard list | 🟡 Partial | The API (`GET /evaluations`) already supports `status`/`limit`/`offset` server-side (prior pass). Whether the dashboard *UI* actually exposes and uses all of these (vs. client-side filtering of one fetched page) was not re-verified in this pass — flagged here rather than asserted either way. |
| T026 — Consent/privacy/accommodation flows; a11y checks; remove unused assets | 🟡 Partial | Concrete a11y lint fixes made (see T023). Consent/privacy/accommodation UI flows: ⬜ not started. Unused-asset review (`useFullscreen.ts`/`FullscreenWarning.tsx`, flagged by `CODEBASE_REVIEW.md` as apparently unused, and redundant Google Fonts loading via both CSS and `next/font`): not re-verified or removed in this pass — see "Deferred" below. |

## P5 — Reliability workbench and closed-loop learning

| Task | Status |
|---|---|
| T027 — Run/experiment comparison UI | ⬜ Not started |
| T028 — Failure signatures, dedup, risk-based sampling | ⬜ Not started |
| T029 — Trace-to-regression drafting with sanitization/approval/versioning | ⬜ Not started |
| T030 — Measured triage yield + BFSI synthetic case study | ⬜ Not started |

No part of P5 has been started. It depends on P2 (traces) and P3 (datasets)
existing first, per the roadmap's own stated dependency.

## P6 — Deployment hardening and controlled pilot

| Task | Status | Evidence |
|---|---|---|
| T031 — Reproducible builds, one IaC/deployment definition, isolated envs, managed secrets | 🟡 Partial | `.github/workflows/ci.yml` is the first CI definition in this repository (test/type-check only — no build/deploy job). `docker-compose.yml` (local Postgres only) and `frontend/vercel.json` predate this pass and remain the only deployment-adjacent artifacts; no backend deployment IaC (Dockerfile, ECS/Fargate/etc. definition) exists — see [DEPLOYMENT.md](DEPLOYMENT.md). |
| T032 — Real-Postgres contract/concurrency tests, scans, load/fault tests, migration rehearsal | ⬜ Not started | The entire automated suite runs against SQLite only (see [TESTING.md](TESTING.md)). No dependency/secret scanning job exists in CI. |
| T033 — Retention/deletion, audit integrity, backup restore verification | ⬜ Not started | No retention/deletion policy is implemented or enforced anywhere in the code. |
| T034 — Consented pilot; track reliability/cost/quality; publish limitations | ⬜ Not started | No pilot has been run; this documentation set itself is the closest artifact to "published limitations" that exists (see [SECURITY.md](SECURITY.md)). |

## P7 — Optional voice extension

| Task | Status |
|---|---|
| T035 — Consented voice input/transcript confirmation + text fallback | ⬜ Not started |
| T036 — Speech-specific datasets/traces/tests, separate speech-vs-reasoning error reporting | ⬜ Not started |

No voice capability exists in this codebase (`useFullscreen.ts` and
`FullscreenWarning.tsx` exist but are not wired into any active page — see
`CODEBASE_REVIEW.md`'s frontend findings; this was not independently
re-verified or acted on in this pass).

## What this pass added that is *not* on the original roadmap's task list

For completeness — these were judged to be concrete, safely implementable,
high-value gaps surfaced by comparing the roadmap's *intent* (P0/T003's
"canonical test commands," P1/T010's "abuse controls") against the actual
repository, even though they don't map to a single named task ID:

- A real, executable, 38-test backend regression suite (`backend/tests/`) —
  zero automated tests existed before this pass.
- A CI workflow (`.github/workflows/ci.yml`) — none existed before.
- A basic in-memory rate limiter (`backend/rate_limit.py`) and startup
  config validation (`main.py`).
- Removal of three git-tracked, sensitive-looking generated files.
- Several concrete, low-risk accessibility and marketing-copy-accuracy
  fixes in the frontend.
- This documentation set itself.

## What was deliberately not attempted, and why

Everything marked ⬜ above that requires one or more of the following was
deliberately left undone rather than partially/superficially implemented:

1. **An external product or infrastructure decision** this engagement is
   not positioned to make unilaterally (which identity provider, which
   observability vendor, which queue technology, which rubric, how many
   benchmark cases, what pilot population).
2. **Credentials or infrastructure this environment does not have**
   (a managed Postgres instance for concurrency testing, a cloud account
   for deployment, a real observability backend, additional LLM budget for
   a benchmark suite).
3. **A scope large enough that a superficial implementation would create
   false confidence** — e.g., a "fake" evaluation harness with no real
   benchmark cases would be worse than clearly documenting that none
   exists, because it would look done without being done. Per this
   project's own explicit instruction, integrity of the documentation
   matters more than the appearance of completeness.

Anyone picking this project back up should treat P2 and P3 as the highest
per-hour-of-effort payoff next steps: P2 (durable execution) removes the
single largest correctness/reliability gap, and P3 (evaluation harness) is
the differentiator `PRODUCTION_ROADMAP.md` itself identifies as the
strongest positioning — but both require the product decisions listed
above to be made first.
