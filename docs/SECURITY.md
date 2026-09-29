# Security posture

This document maps every finding in `CODEBASE_REVIEW.md` to its **current**
status, plus controls added since that review. It is written to be honest
about what is and isn't protected — do not deploy this publicly based on an
assumption that anything not listed as "fixed" below has been addressed.

## Summary judgment

Authentication, role-based authorization, tenant isolation, and an audited
trail of security-relevant actions now exist (added in the platform
foundation phase). The interview-pipeline endpoints (`/start`, `/round/*`,
`/final-decision`, `/evaluations*`) remain **deliberately unauthenticated**
for backwards compatibility — they attribute ownership when credentials are
present and work anonymously when they are not.

So: the identity foundation is in place and tested, but **the product is not
yet fully locked down**, because the original pipeline endpoints are still
open by design during the transition. Suitable for a controlled pilot behind
a separate access-control layer; not yet for unrestricted public exposure.

What exists now:

| Control | Status |
|---|---|
| Password authentication | bcrypt over SHA-256 pre-hash, cost factor 12 |
| Session tokens | Signed JWTs; no capabilities in the token, so revocation is immediate |
| Capability-based authorization | `rbac.Capability`, enforced via `authz.requires(...)` |
| Tenant isolation | `authz.assert_tenant`, returns 404 (not 403) to prevent ID enumeration |
| Audit trail | Tiered, hash-chained, with integrity verification endpoint |
| Account enumeration resistance | Login returns identical errors and comparable timing for unknown email vs. wrong password |
| Rate limiting | Basic in-memory per-IP (single-process only) |

What is still missing is listed under "Explicitly open gaps" below.

## `CODEBASE_REVIEW.md` findings — status

| ID | Finding | Status | Evidence |
|---|---|---|---|
| B01 | Reset creates two different state objects — a reset/start could lose the evaluation linkage used by later persistence | **Fixed** | `state.py` no longer holds any mutable session dictionary; the database is the sole source of truth per `evaluation_id`. Structurally impossible to reintroduce this specific bug without reintroducing a global mutable object. |
| B02 | Shared state and verdict files mix unrelated interviews | **Fixed** | Every evaluation's verdict files live under `backend/verdicts/{evaluation_id}/`, keyed by the DB-assigned ID (`state.eval_verdicts_dir`). |
| B03 | Model failures become candidate judgments (invalid JSON → fabricated FAIL; missing fields → fabricated defaults) | **Fixed** | `crew_runner._parse_json_output`/`_validate_verdict` raise `AgentOutputError` for any parse/schema failure; callers persist `decision="INVALID_OUTPUT"` and return HTTP 502 — never a business decision. Regression-tested in `backend/tests/test_crew_runner_parsing.py` and `test_routes.py::TestInvalidAgentOutputNeverBecomesADecision`. |
| B04 | Public access to sensitive records (raw resume text returned by list/detail endpoints); no request authentication at all | **Substantially fixed.** Resume-text exposure fixed. Authentication, RBAC, and tenant isolation now exist — but the legacy pipeline endpoints remain intentionally open. | `database._EVALUATION_SUMMARY_COLUMNS` excludes `resume_text`. Identity layer: `security.py`, `rbac.py`, `authz.py`, `auth_routes.py`. Tenant isolation verified by `tests/test_identity.py::TestTenantIsolation` (a CI gate). Remaining gap: `/start`, `/round/*`, `/final-decision`, `/evaluations*` still accept unauthenticated calls for backwards compatibility. |
| B05 | Workflow transitions and commits are not protected (no idempotency key, no expected-round check, duplicate/out-of-order requests can corrupt history) | **Fixed** (for the single-writer-per-round case). | `routes.py` checks expected `current_round` (409 if wrong) and canonical-verdict existence (409 if already evaluated) before running any agent; `database.uq_verdicts_canonical` (a partial unique index) makes a second canonical verdict for the same evaluation/round a rejected `DuplicateVerdictError`, not a silent overwrite. `/final-decision` is idempotent by design (replays the persisted result). Verified in `test_routes.py::TestGuardsAndErrorHandling` and `test_database.py::TestCanonicalVerdictUniqueness`. |
| B06 | Long-running work is tied to HTTP lifetime; synchronous DB calls block the event loop; no durable queue/recovery | **Partially fixed.** Event-loop blocking is fixed, and finalization now has durable queue/recovery support with persisted cancellation. | Every `database.py` call from `routes.py` is wrapped in `asyncio.to_thread` via the `_db()` helper. `background_jobs` adds atomic claims, leases, bounded retries, dead-letter status, tenant keys, and cancellation state for finalization; `job_worker.py` checks cancellation before and after handlers and can resume persisted round-4/5 checkpoints. Screening, technical, behavioral, and inline final-decision execution can still be lost with the HTTP process and require retry. |
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

1. **Authentication on the legacy pipeline endpoints.** `/start`,
   `/round/*`, `/final-decision`, and `/evaluations*` still accept
   unauthenticated requests. This is a deliberate backwards-compatibility
   choice during the platform transition, not an oversight — but it means
   the API must not be publicly exposed until those endpoints require
   credentials and scope their queries by tenant.
2. **Invitation flow.** The `invitations` table exists and tokens are
   hashed, but the accept-an-invite flow is not implemented; only
   already-registered users can be added to an organization.
3. **Spend/abuse budgets beyond the basic rate limiter.** No
   per-tenant or global LLM spend cap exists; the rate limiter only bounds
   *request count*, not cost. The in-memory limiter is also single-process
   only — multiple workers each enforce an independent limit.
4. **A real evaluation/grading harness for the agents themselves** (Q05
   above) — unimplemented.
5. **Prompt-injection defenses** (Q06) — no sanitization, delimiter
   strategy, or adversarial test suite exists for resume/answer content
   passed into agent prompts.
6. **Audit anchoring** — the hash chain detects edits and deletions, but a
   sufficiently privileged attacker who rewrites every subsequent row could
   reforge it. Resisting that needs periodic signed digests written to
   separately-credentialed, object-locked storage.
7. **Schema migrations** — see [DATA_MODEL.md](DATA_MODEL.md). Startup DDL
   plus a narrow additive-column helper is not a substitute for versioned,
   reviewable migrations once real data exists.
8. **Password reset, email verification, MFA** — none implemented. The
   `email_verified_at` column exists but nothing sets it.
