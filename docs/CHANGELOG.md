# Changelog

This is a chronological record of every substantive change an AI coding
agent has made to this repository, grouped by work session, with the
concrete reason for each change. It exists so that any change can be
audited: what was different before, what changed, and why — not just a
commit message, but the reasoning.

Entries are in **reverse chronological order** (most recent session first).

---

## Session 10 — Add durable retry controls for agent jobs

- Added typed provider, rate-limit, and stage-timeout errors in
  `backend/crew_runner.py`, with explicit stage labels, configurable
  deadlines, and capped exponential backoff with bounded jitter.
- Added worker retry jitter, cancellation-safe lease release, and explicit
  non-retryable dead-lettering for invalid model output.
- Extended `database.fail_job` with a retryability decision while preserving
  the existing attempt limit and SQLite/PostgreSQL behavior.
- Added focused regression tests for retry bounds, cancellation recovery,
  and immediate dead-lettering; updated roadmap and architecture status to
  describe the partial P2 implementation accurately.

---

## Session 9 — Fix: no persona distinction at onboarding (frontend only)

**Trigger:** the landing page's primary call-to-action was still "Start
Evaluation" / "Open Dashboard" — the pre-platform demo flow — with no path
that asked whether a visitor was job-hunting or hiring, and no visible link
into the real, tenant-isolated recruiter workspace built in Phases 0–2. A
visitor could reach an unauthenticated, global list of every sandbox
evaluation ever run by clicking the hero's second button, one click from the
homepage, styled identically to a real feature.

**No backend files were touched.** This was a frontend-only fix; the
platform's auth/RBAC/tenancy already existed and worked correctly — it was
simply unreachable from the page a new visitor actually lands on.

### Root cause

The landing page (`app/page.tsx`) predates Phase 0–2 and was never updated
after authentication, job postings, and the recruiter workspace were built.
It still promoted the anonymous single-pipeline demo (`/interview`,
`/dashboard`) as the primary product, with no mention of `/register`,
`/jobs`, or `/org` anywhere on the page.

### Fixes

- **`app/page.tsx`** — hero CTA replaced with a `PersonaCta` component
  (early-return per branch, matching the pattern already used for
  `Navbar`'s auth-area, rather than a nested ternary): guests see
  "I'm looking for a job" / "I'm hiring talent" leading to
  `/register?intent=...`; an authenticated candidate sees "Browse jobs" /
  "Complete your profile"; an authenticated recruiter sees "Go to recruiter
  workspace" / "Browse jobs". Added a dedicated "Built for job seekers and
  hiring teams" section with two audience cards, each listing concrete
  capabilities and its own signup CTA — this is the section that directly
  answers "is this for me or for recruiters?" Reframed the five-agent
  architecture section as *the engine that runs inside applications*, not
  the product itself, with an explicit link to the sandbox for anyone who
  wants to see it without signing up. Updated the FAQ to lead with "Is
  Evalia for job seekers or hiring teams?".
- **`app/register/page.tsx`** — added a persona selector (segmented control,
  "I'm looking for a job" / "I'm hiring talent"), read from `?intent=` so
  landing-page links pre-select it. Post-registration redirect now depends
  on intent (`/profile` for candidates, `/org` for recruiters) — a `?next=`
  deep link (e.g. "log in to apply to this job") always wins over the
  persona default, since that candidate already told the app what they came
  for. Wrapped in `Suspense` for `useSearchParams`, matching the existing
  `login` page pattern.
- **`app/login/page.tsx`** — the "Sign up instead" link now forwards `?next=`
  so a candidate redirected to login from a specific job doesn't lose that
  destination if they realize they need to register first.
- **`app/profile/page.tsx`** — fixed a redirect-to-login call that was
  missing `?next=/profile` (every other protected page already had this;
  this one was a genuine oversight, not a deliberate omission). Strengthened
  the empty-profile state into an explicit welcome message with a "skip for
  now, browse jobs" escape hatch, so a candidate isn't forced through
  profile completion before they've seen there's anything worth applying to.
- **`app/org/page.tsx`** — the zero-membership state now explicitly says
  this workspace is separate from candidate job-seeking on the same login,
  addressing the dual-persona model directly at the point someone would be
  confused by it.
- **`app/components/Navbar.tsx`** — guests now see a "For recruiters" link
  distinct from "Log in"/"Sign up", in both desktop and mobile nav, so the
  persona split is visible in navigation, not only on the landing page.
- **`app/dashboard/page.tsx`, `app/interview/page.tsx`** (the legacy,
  unauthenticated demo flow) — **kept working, not removed** (backwards
  compatibility, consistent with every prior session), but relabeled from
  "Recruiter Dashboard" / "Start Candidate Evaluation" to explicit
  "Public demo — AI evaluation sandbox" framing, each with an inline note
  and a cross-link to the real, authenticated equivalent (`/org`, `/jobs`).
  A visitor can no longer mistake the public sandbox for the tenant-isolated
  product, but the sandbox itself — genuinely useful for trying the agent
  pipeline without an account — still works exactly as before.

### What did not change

No backend route, model, or capability changed. The `/dashboard` and
`/interview` endpoints they call (`GET /evaluations`, `GET /dashboard/stats`,
`POST /start` without credentials) are unchanged and still intentionally
unauthenticated per [SECURITY.md](SECURITY.md) — this session made that
scope visible in the UI rather than changing it, which is a product-honesty
fix, not a security fix. The underlying "legacy endpoints are still open"
gap remains recorded in SECURITY.md exactly as before.

### Verification

Full backend suite (176 tests) re-run and unaffected, since no backend files
were touched. `npm run typecheck` clean. One incidental lint fix
(`actor?.memberships.length` optional-chain) made in `org/page.tsx` while
already editing that block; two pre-existing, unrelated findings in the same
file (nested ternaries in campaign/posting status rendering, untouched by
this session) were left as-is, consistent with this project's established
practice of not fixing unrelated pre-existing style debt in the same pass.

---

## Session 8 — Phase 2: matching engine, sourcing, referrals, analytics, and the first frontend

**Trigger:** instruction to proceed with Phase 2, building backend and
frontend functionality together rather than backend-only.

### Backend: `matching.py`

A deterministic, explainable matching engine — deliberately Stage 1 of the
three-stage plan in [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md) §8.1.
Semantic (pgvector) and learned ranking are documented as explicitly
deferred, the latter because it needs real outcome data that does not exist
yet; building it now would mean training on nothing.

Every score ships with its own explanation — a bare number nobody can
interrogate is a black box, not a recommendation. The scoring function
(`score_match`) is pure (no database access), which is what let it be
unit-tested exhaustively without a database; orchestration (`rank_jobs_for_candidate`,
`rank_candidates_for_posting`) is a thin, separately-tested layer on top.

A verified skill earns a bonus within the skills component, capped so it
cannot alone guarantee a match — deliberately conservative, per the
gamification guardrail in the blueprint: prep-suite performance should never
silently become a hiring ranking factor without disclosure.

### Backend: sourcing, referrals, analytics

- **Talent-pool search** (`candidate_db.search_discoverable_profiles`) —
  gated on a candidate opt-in (`is_discoverable`) enforced in the query
  itself, not a post-filter, so it cannot be bypassed by a route bug.
  Reading it is audited at Tier 3: browsing people who have not applied to
  you is a materially different act than reading your own pipeline.
- **Referrals** — a recruiter can refer a candidate by email before that
  candidate necessarily has an account; matching is by normalized email. A
  partial unique index blocks a duplicate *open* referral without blocking a
  fresh one after the first was closed.
- **Analytics: funnel** — stage-to-stage conversion, gated at org-wide read
  (`campaign:read:org`, hiring-manager-and-above) rather than the narrower
  scope a plain recruiter holds.
- **Analytics: selection-rate divergence** — reports the same four-fifths-rule
  ratio a formal EEO audit would use, computed over non-protected fields
  (`source`, a derived experience band) since no protected characteristic is
  collected (see [DECISIONS.md](DECISIONS.md) D-05). Documented explicitly,
  including in its own API response, as the mechanism rather than a
  compliant audit — the distinction matters and is stated rather than
  implied. A flagged result audits at Tier 1.

### Frontend: first UI for the platform

Previously the platform existed only as an API. This session adds the first
pages: `lib/api.ts` (typed fetch wrapper, attaches the bearer token and
active-org header automatically), `lib/auth-context.tsx` (session state,
org-switching), `lib/types.ts` (shared domain types mirroring the backend
response shapes), and pages for registration, login, the profile vault
editor, job search with recommendations, job detail/apply, the application
tracker, the referral inbox, and — on the recruiter side — campaign/posting
management, the applicant pipeline, and the analytics dashboard.

### Fixed during this session

- A duplication bug in `hiring_schema.py` (a dropped assignment left part of
  the SQLite DDL unreachable) was caught by the new tests failing, not by
  static analysis — worth noting as a reminder that schema changes need a
  test that actually exercises `init_db()`, which the existing suite already
  does.
- A nested-ternary lint finding in `Navbar.tsx`'s auth-state rendering was
  extracted into a small `DesktopAuthArea` component.

### Tests

134 → **176 passing**. `tests/test_matching.py` unit-tests `score_match`
exhaustively (skills overlap and gaps, experience under/over-qualification,
location/remote combinations, compensation overlap, recency decay) without
touching a database. `tests/test_hiring.py` gained coverage for sourcing
opt-in, referral creation/duplication, and the funnel/selection-rate
endpoints, including that non-discoverable candidates never appear in
search results.

### Known gaps

Interview scheduling and notifications remain unbuilt. The frontend has no
automated test suite (no Playwright/Vitest config exists) — only `tsc
--noEmit`, consistent with the pre-existing gap noted in
[TESTING.md](TESTING.md).

---

## Session 7 — Phase 1: profile vault, campaigns, postings, applications

**Trigger:** instruction to settle the open decisions, then build Phase 1.

### Decisions settled

The decision-maker was unavailable, so the four blocking decisions were taken
autonomously, each resolved to the **reversible or lower-risk** option and
recorded in [DECISIONS.md](DECISIONS.md) with its reversal cost. Summary:
RLS deferred until a Postgres test environment exists (adding it now means
shipping untested security code); in-house auth kept; consent and retention
captured now but enforced per-market later; and **no automated rejection**.

### New modules

`hiring_schema.py` (DDL), `candidate_db.py` (profile vault),
`hiring_db.py` (campaigns/postings/applications plus the state machine),
`hiring_models.py`, `candidate_routes.py`, `recruiter_routes.py`.

### The "fill it once" vault

The retention mechanic, and the thing that makes application two cheaper than
application one: `GET /jobs/{id}/application-form` returns the posting's
questions already pre-filled from the candidate's vault, and answers supplied
at submission are written back. A `question_key` is stable across
organizations, so a question one company asks pre-fills for the next.

Candidates can opt out per-application (`save_answers_to_vault: false`),
because "notice period" and "reason for leaving" are not equally reusable.

### Decisions embedded in the code

- **`auto_reject_enabled` defaults to `false`** on every posting. An
  automated employment decision is a regulated act; orgs opt in explicitly
  and auditably.
- **`PENDING_REVIEW` stage** — an automated stage producing an adverse
  recommendation parks the application here rather than rejecting it. The
  stage can transition in either direction, because overriding the machine is
  the entire point of it existing.
- **Explicit transition table** rather than "anything goes", so a replayed or
  out-of-order request is rejected instead of corrupting pipeline history.
  Terminal stages have no exits.
- **`profile_snapshot` on every application** — an immutable copy of the
  profile at submission. A candidate editing their profile later must not
  silently rewrite what a recruiter actually assessed.
- **Verified skills survive a profile edit.** Verification is earned by
  demonstrated performance; a profile edit must not be able to fabricate or
  erase it. Tested.
- **Partial unique index excludes withdrawn applications**, so a candidate
  who withdrew can genuinely re-apply. Tested.
- **Rejection requires `APPLICATION_REJECT` on top of `APPLICATION_ADVANCE`**
  — advancing someone and ending their candidacy are different acts.
- **Rejection audits at Tier 1**, however routine it is operationally,
  because it is an adverse decision about a person. Recruiters reading
  candidate data audits at Tier 3, which is what a subject-access request
  needs.
- **Internal recruiter notes never reach the candidate timeline.** Tested.

### Tests

89 → **134 passing**. `tests/test_hiring.py` adds 45, including
`TestHiringTenantIsolation` as a second CI gate covering campaigns, postings,
applicants and transitions — with a positive control so it cannot pass by
denying everything, and a case asserting one candidate cannot read another's
application.

### Known gaps

Interview scheduling, notifications, and the matching engine are Phase 1/2
scope and not yet built. The job board search is `LIKE`-based, which is
adequate at current volume and will need real full-text search later.

---

## Session 6 — Platform foundation: identity, RBAC, tenancy, audit

**Trigger:** instruction to begin implementing the product blueprint, one
piece at a time, keeping existing functionality intact.

This is **Phase 0** from [PRODUCT_BLUEPRINT.md](PRODUCT_BLUEPRINT.md) — the
layer everything else depends on, and the only part that genuinely cannot be
retrofitted later without rewriting every query in the codebase.

### New modules

- **`backend/security.py`** — password hashing and token issuance.
  Passwords are SHA-256 pre-hashed before bcrypt because **bcrypt silently
  truncates at 72 bytes**, meaning two distinct long passwords can otherwise
  collide; there is a regression test for exactly that. Tokens are stateless
  JWTs carrying only a user ID — deliberately *not* capabilities, so that a
  role change or revoked membership takes effect on the next request instead
  of lingering until expiry. Refuses to start with `APP_ENV=production` unless
  `JWT_SECRET` is set.
- **`backend/rbac.py`** — 34 capabilities and 7 system roles. Business logic
  branches on capabilities, never on role names, because role names change
  and will eventually become customer-defined.
- **`backend/authz.py`** — the `Actor` abstraction plus FastAPI dependencies
  (`current_actor`, `optional_actor`, `requires(...)`, `assert_tenant`).
  Cross-tenant access returns **404, not 403**: a 403 confirms a resource
  exists, which would let a competitor enumerate another company's IDs.
- **`backend/audit.py`** — tiered, hash-chained audit events. Never raises;
  an audit backend failure must not take down the product, but it logs at
  ERROR so the gap is detectable rather than silent.
- **`backend/auth_routes.py`** — register, login, `/auth/me`, organization
  and membership management.
- **`backend/admin_routes.py`** — audit search, chain verification, and
  impersonation.

### Schema

Seven new tables (`organizations`, `users`, `roles`, `role_capabilities`,
`org_memberships`, `invitations`, `audit_events`), with roles and their
capabilities re-seeded idempotently on every startup so a code change takes
effect without a manual migration step.

`evaluations` gained **nullable** `org_id` and `owner_user_id`, applied by an
additive-column helper for databases that predate them. Nullable is
deliberate: rows created before ownership existed cannot be retroactively
attributed, and inventing an owner would corrupt the audit story.

### Deliberate design decisions

- **Dual-persona identity.** A user is not typed as candidate *or* recruiter.
  Identity is a `users` row; being a recruiter is an `org_memberships` row.
  A `user.type` column would permanently block the case where someone is a
  candidate at one company and a recruiter at their own employer.
- **Login cannot enumerate accounts.** Unknown email and wrong password
  return an identical error, and the unknown-email path still performs a
  bcrypt verification against a dummy hash so response *timing* does not leak
  the answer either. Tested.
- **Last-owner guard.** An organization cannot be left without an owner;
  removing or demoting the only owner returns 409. An ownerless org requires
  manual database intervention to recover.
- **Impersonation controls enforced in code, not policy** — mandatory written
  reason stored in the audit log, 30-minute token, self-impersonation and
  admin-on-admin impersonation both refused (the latter would let one admin
  launder actions through another's identity).

### Backwards compatibility — explicitly preserved

The existing pipeline endpoints (`/start`, `/round/*`, `/final-decision`,
`/evaluations*`) still work **without credentials**. `/start` uses an
*optional* actor dependency: with a token it records ownership and writes an
audit event, without one it behaves exactly as before, and an invalid token
degrades to anonymous rather than erroring. All 38 pre-existing tests passed
unmodified at every step.

### Tests

38 → **89 passing**. The new `tests/test_identity.py` adds 51, including a
`TestTenantIsolation` class intended as a CI gate — those tests are the
executable form of "two companies cannot see each other's data," and a
failure there is a data breach rather than a bug. It includes a positive
control (own-org access still works) so the suite cannot pass merely because
everything is denied. Audit tests verify the hash chain detects both edits
and deletions.

`BCRYPT_ROUNDS=4` is set in `conftest.py` — bcrypt at the production cost
factor of 12 dominated the suite runtime. Safe only because those hashes
never leave the test process.

### Known gaps left open deliberately

Invitation accept-flow, password reset, email verification, and MFA are not
implemented. The legacy pipeline endpoints remain unauthenticated by design
during the transition — documented in [SECURITY.md](SECURITY.md) rather than
quietly left as an apparent oversight.

---

## Session 5 — Product blueprint (planning only, no code changes)

**Trigger:** request to reshape Evalia from a demo-style single pipeline into a
full product — RBAC, admin console, audit trails, recruiter/candidate
segregation, campaigns and applicant tracking, prep suite with in-browser
IDE and DSA/dev challenges, gamification, personalized roadmaps, auto-apply
agent, onboarding for both personas, recommendation engines, and SaaS
monetization parked as future scope.

**No application code was modified in this session.** The deliverable was a
plan, per the request's closing instruction ("come up with a plan on how can
we improvise this entire thing").

- **Added [`docs/PRODUCT_BLUEPRINT.md`](PRODUCT_BLUEPRINT.md)** — the target
  product architecture: three-layer authorization model (tenant → role →
  resource), full domain model across identity/hiring/prep/engagement,
  tiered audit-trail design with hash chaining, recruiter campaign and
  configurable-pipeline model, candidate Profile Vault ("fill once")
  and progressive onboarding, staged matching engine (deterministic →
  semantic → learned), prep suite built on a curated topic graph with
  sandboxed code execution, gamification with an anti-bias guardrail,
  auto-apply agent with adapter preference order, admin console, platform
  services, and a six-phase delivery plan with monetization as explicit
  future scope.
- **Added [`docs/DECISIONS.md`](DECISIONS.md)** — 10 decisions that block
  Phase 0, each with options, trade-offs, a recommendation, and an urgency
  rating. Four are marked as needing resolution before any Phase 0 code is
  written, because each one shapes the database schema.
- **Edited [`docs/README.md`](README.md)** — split the index into "current
  system" and "forward-looking plans," and documented how the blueprint
  relates to the pre-existing `PRODUCTION_ROADMAP.md`.

**Why planning rather than implementation:** the requested scope spans
multi-tenancy, RBAC, an ATS, a LeetCode-style judge with sandboxed code
execution, and an auto-apply agent. Several foundational choices in that set
— tenancy isolation, auth provider, compliance jurisdiction, and the stance
on automated rejection — are effectively irreversible once data exists, and
three of them (code-execution sandboxing, auto-apply against third-party
ToS, automated employment decisions) carry security or legal risk that
should be decided deliberately rather than assumed by an implementation.

---

## Session 4 — Documentation, gap analysis, and test/CI hardening

**Trigger:** explicit request to compare the codebase against
`PRODUCTION_ROADMAP.md`/`CODEBASE_REVIEW.md`, implement any feasible gaps,
and produce a complete, high-integrity `docs/` folder plus this changelog.

### Repository hygiene

- **Removed from git tracking:** `backend/verdicts/round1.txt`,
  `round2.txt`, `round3.txt`. **Why:** these were stale artifacts from
  before the per-evaluation verdict-directory fix (current code writes to
  `backend/verdicts/{evaluation_id}/roundN.txt`, never the flat path), they
  were not written by any current code path, and their content appeared to
  be a real candidate's resume-screening output — exactly the accidental
  sensitive-data-commit risk `CODEBASE_REVIEW.md` flagged. They remain
  ignored by `.gitignore`; this change stops tracking them going forward.
  (Note: this does not purge them from prior git history — a history
  rewrite was intentionally not performed without explicit authorization,
  per this project's operational-safety rules around destructive,
  hard-to-reverse actions on shared history.)
- **Added:** `backend/verdicts/.gitkeep`. **Why:** the verdicts directory
  itself was deleted as a side effect of removing the only files in it;
  `.gitkeep` keeps the empty directory present in a fresh checkout
  (`state.py` also recreates it at import time regardless, so this is a
  convenience, not a functional requirement).

### Backend: automated test suite (new)

No automated tests existed anywhere in this repository before this
session. Added `backend/tests/`:

- `conftest.py` — shared fixtures: `isolated_db` (fresh SQLite file per
  test via `tmp_path`, so tests never touch a developer's real
  `backend/evalia.db`), `isolated_verdicts_dir`, `client` (a `TestClient`
  wired to both). Also disables the new rate limiter
  (`RATE_LIMIT_REQUESTS=0`) before the first `import main`, since route
  tests exercise business logic, not the rate limiter.
- `test_crew_runner_parsing.py` — 11 tests directly regression-testing
  `CODEBASE_REVIEW.md` finding B03 ("model failures become candidate
  judgments"): invalid JSON, markdown-fenced JSON, out-of-range scores,
  unknown decision enums, missing confidence, all correctly raising
  `AgentOutputError` instead of a fabricated decision.
- `test_database.py` — 11 tests covering PII projection (`resume_text`
  never leaks), batched verdict-summary fetching (proves a single query
  answers for N evaluations — the N+1 fix), and the canonical-verdict
  uniqueness constraint (including that `INVALID_OUTPUT` rows never block a
  legitimate retry).
- `test_routes.py` — 12 tests driving the real FastAPI app end-to-end via
  `TestClient`, with every agent-calling function monkeypatched to a
  deterministic fake (no live LLM calls, ever): full happy path to `HIRE`
  with idempotent `/final-decision` replay; rejection short-circuiting
  (asserts later-stage agents are literally never invoked after an early
  rejection); invalid-agent-output handling; 404/409/400 guard behavior;
  PII-safety of list/detail/report responses.
- `test_rate_limit.py` — 4 tests for the new rate-limit middleware in
  isolation (its own minimal Starlette app, no database/agents/crewai
  import — runs in ~2-3 seconds).
- `backend/pytest.ini` — canonical test configuration/discovery.
- `backend/requirements-dev.txt` — `pytest`, `pytest-cov`, `httpx` (test/CI-only
  dependencies, separate from runtime `requirements.txt`).

**Why:** `PRODUCTION_ROADMAP.md` P0/T001–T003 and `CODEBASE_REVIEW.md`
explicitly identified "no authored automated tests or CI workflows" as a
finding. This closes that gap concretely and verifiably (38 tests, all
passing, ~44s total run time, zero live LLM calls / zero cost).

### Backend: rate limiting and startup validation (new)

- **Added `backend/rate_limit.py`** (`InMemoryRateLimitMiddleware`): a
  fixed-window, per-client-IP request counter. Default 60 requests/60s per
  IP, configurable via `RATE_LIMIT_REQUESTS`/`RATE_LIMIT_WINDOW_SECONDS`,
  disableable via `RATE_LIMIT_REQUESTS=0`. **Why:** `CODEBASE_REVIEW.md`
  finding B04 and `PRODUCTION_ROADMAP.md` P1/T010 both call out the absence
  of any abuse control on endpoints that trigger paid LLM calls. This is
  explicitly scoped as a single-process, request-count-only control — not a
  distributed rate limiter, not a spend budget, not a substitute for
  authentication — documented honestly in `docs/SECURITY.md` rather than
  oversold.
- **Edited `backend/main.py`:** wired in the new middleware; added
  `_validate_startup_config()`, which logs (does not block startup)
  warnings for an insecure `CORS_ORIGINS=*` + credentialed-CORS
  combination, `APP_ENV=production` without `DATABASE_URL` (silent SQLite
  fallback), and `APP_ENV=production` without `GEMINI_API_KEY` (a hint that
  the hardcoded local-proxy override in `agents.py` may be unintentional in
  that environment). **Why:** cheapest, highest-value subset of P1/T010's
  "validate required production configuration" that doesn't require a full
  settings-management rewrite. **Middleware ordering:** the rate limiter is
  registered *before* `CORSMiddleware`. Starlette builds its middleware
  stack so the last-registered middleware ends up outermost — an initial
  version of this change registered CORS first, which meant a 429 response
  from the rate limiter (short-circuited before reaching CORS) would be
  missing CORS headers entirely, appearing to a browser client as an opaque
  CORS failure instead of a legible 429 + `Retry-After`. Caught by this
  environment's static analysis after the first implementation and
  corrected before this session ended; re-verified with the full test
  suite (38/38 passing) after the fix.
- **Edited `.env.example`:** documented the new `APP_ENV`,
  `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`,
  `COPILOT_PROXY_API_KEY` variables.

### CI (new)

- **Added `.github/workflows/ci.yml`.** Two jobs: backend `pytest` (no
  secrets required — every test is offline/mocked, see above) and frontend
  `npm run typecheck`. **Why:** `PRODUCTION_ROADMAP.md` P0/T003 explicitly
  calls for "PR validation"; none existed. Deliberately does **not** run
  `next build` in CI (see `docs/SETUP.md` — it requires outbound network
  access to Google Fonts and would fail in a network-restricted runner for
  a reason unrelated to code correctness) and deliberately does **not**
  include a live-LLM-calling job (would require a secret and incur cost on
  every PR — see `docs/TESTING.md` "Live agent smoke test" for why that's a
  separate, manual/protected concern instead).

### Frontend: accessibility and prop-readonly fixes

Fixed concrete, tool-confirmed findings (not speculative):

- `app/interview/page.tsx` — associated the "candidate name" and "resume"
  labels with their inputs via `htmlFor`/`id`; replaced the "target role"
  `<label>` (which had no single associated control — it labels a group of
  buttons) with a semantic `<fieldset>`/`<legend>`.
- `app/result/page.tsx` — converted the clickable verdict-card header from
  a non-interactive `<div onClick>` (no keyboard access, no role) to a
  native `<button type="button">`; replaced raw array-index React `key`
  props on strengths/weaknesses/hiring-risks lists with a content-derived
  key; marked `VerdictCard`'s props type `Readonly<...>`.
- `app/page.tsx` (landing page) — applied the same
  non-interactive-`div`-to-`button` fix to the FAQ accordion; marked its
  props `Readonly<...>`.
- `app/round/[id]/page.tsx` — associated the "candidate answer" label with
  its textarea; replaced `parseInt` with `Number.parseInt`; extracted a
  nested ternary (stage-indicator color logic) into a named
  `stageColor()` helper function.
- `tsconfig.json` — bumped `target` from `es5` (deprecated, will stop
  working in TypeScript 7.0) to `es2020`. **Why safe:** Next.js's own SWC
  compiler (not `tsc`) produces the actual shipped/polyfilled browser
  bundle; this setting only affects `tsc`'s own type-checking/lib
  resolution, not runtime browser compatibility.

**Why these specific fixes:** all were surfaced by this environment's
built-in diagnostics (not invented), are small and self-contained, and were
each individually verified via a fresh `get_errors` pass afterward
confirming resolution with zero new errors introduced, plus a full
`npm run typecheck` pass confirming no regressions.

### Frontend: marketing-copy accuracy fixes

- `app/page.tsx`: removed the false "All evaluations include a **calibrated**
  confidence score" claim (confidence is self-reported by the LLM, not
  calibrated against any labeled dataset — `CODEBASE_REVIEW.md` finding
  Q03); removed the unverified "<2m" processing-time stat (no measurement
  in this repository supports a specific latency claim); corrected the FAQ
  answer describing the architecture as "5 CrewAI agents powered by Gemini
  2.5 ... SQLite persistence" to reflect that the LLM provider is
  configurable (and currently overridden to a local proxy — see
  `docs/ARCHITECTURE.md`) and that PostgreSQL is the primary supported
  database, SQLite only a local fallback.

**Why:** direct implementation of `PRODUCTION_ROADMAP.md` P0/T004
("Reconcile product claims in README.md and frontend/app/page.tsx").

### Documentation (new)

- **Added `docs/`** with `README.md` (index), `ARCHITECTURE.md`,
  `API_REFERENCE.md`, `DATA_MODEL.md`, `SETUP.md`, `TESTING.md`,
  `SECURITY.md`, `GAP_ANALYSIS.md`, `DEPLOYMENT.md`, and this
  `CHANGELOG.md`. Every factual claim in these documents was grounded in
  source code read during this session or a test actually executed, not
  inferred from the pre-existing (partly aspirational) `README.md`.
- **Rewrote the root `README.md`** to describe the actual current system
  (accurate endpoint list, accurate architecture summary, accurate setup
  instructions, honest "what this is / isn't" framing) and to point to
  `docs/` for full detail, rather than repeating the prior version's
  overclaims.

---

## Session 3 — Live end-to-end validation (no code changes)

**Trigger:** explicit request to test the full pipeline end-to-end now that
a live LLM endpoint (a local OpenAI-compatible proxy on port 9999) was
available.

No source files were modified in this session. Findings (used as evidence
throughout this documentation set, particularly `docs/TESTING.md`):

- Full pipeline (screening → technical → behavioral → recommendation →
  committee) completed successfully end-to-end against the real, live LLM
  proxy, reaching a `HIRE` decision (`overall_score: 8.2`,
  `confidence: 0.93`).
- `/final-decision` called twice for the same completed evaluation returned
  an identical result — idempotent replay confirmed against a real run.
- The rejection path (round 1 PASS, round 2 FAIL) was independently
  confirmed live.
- `/evaluations` and `/evaluations/{id}` were confirmed, against live data,
  to never include resume text.
- Observed (non-blocking, cosmetic): CrewAI's console event-bus logger
  throws `'charmap' codec can't encode...` on Windows when agent output
  contains smart quotes/em-dashes, due to the default Windows console
  codepage not being UTF-8. Caught internally by CrewAI; never affects the
  actual HTTP response. Not fixed — recorded as a known, low-priority
  cosmetic issue in `docs/TESTING.md`.
- A throwaway test script and throwaway SQLite database created during this
  session were deleted afterward; the repository was left unchanged.

---

## Session 2 — LLM provider swap (Gemini → local proxy)

**Trigger:** explicit request to point every agent at a local,
OpenAI-compatible proxy served by a VS Code extension on port 9999, instead
of Gemini, while leaving the original Gemini configuration line intact and
unmodified (so it could be trivially restored).

- **Edited `backend/agents.py`:** left the original
  `LLM_MODEL = "gemini/gemini-2.5-flash"` line untouched, and added a second
  assignment directly after it:
  ```python
  LLM_MODEL = LLM(
      model="openai/gpt-5.6-luna",
      base_url="http://127.0.0.1:9999/v1",
      api_key=os.getenv("COPILOT_PROXY_API_KEY", "not-needed"),
      custom_openai=True,
  )
  ```
  **Why this shape:** `crewai`'s `LLM(...)` factory, given a `model` string
  prefixed `openai/` plus an explicit `base_url` and `custom_openai=True`,
  routes through the native OpenAI-compatible provider against that
  `base_url` regardless of whether the model name matches any of crewai's
  built-in model patterns — this is what makes an arbitrary model name like
  `gpt-5.6-luna` work against a non-OpenAI backend, as long as that backend
  implements the `/v1/chat/completions` wire format. The OpenAI Python SDK
  requires a non-empty `api_key` string even against an unauthenticated
  local proxy, hence the `"not-needed"` fallback default. Since this is a
  later assignment to the same variable name, it silently wins over the
  Gemini line without deleting it — satisfying the explicit "keep the
  Gemini logic intact, make no changes to it" constraint.

---

## Session 1 — Production-hardening pass (backend rewrite + frontend contract fixes)

**Trigger:** a prior codebase review (`CODEBASE_REVIEW.md`) identified
several concrete, reproduced bugs and a production roadmap
(`PRODUCTION_ROADMAP.md`) was written; this session implemented the P0/P1
fixes that were feasible without new infrastructure or external product
decisions.

- **`backend/state.py`** — removed the process-global mutable
  `interview_state` dictionary entirely. **Why:** it was the root cause of
  finding B01 — `state.py`'s `reset_state()` rebuilt the dictionary as a
  *new* object rather than mutating the existing one, so `routes.py`
  (which had imported a reference to the *old* object) silently wrote to an
  abandoned dictionary that `get_state()` would never read again. Replaced
  with: the database as sole source of truth per `evaluation_id`, plus a
  per-evaluation verdict-directory helper (`eval_verdicts_dir`) so
  concurrent evaluations can never share or overwrite each other's verdict
  files (finding B02).
- **`backend/models.py`** — converted every decision field to a real
  `Enum` (`ScreeningDecision`, `RoundDecision`, `BehavioralDecision`,
  `HiringDecision`, `EvaluationStatus`); removed the silent
  `confidence` default; added `max_length` bounds to `StartRequest`/
  `AnswerRequest`. **Why:** finding B03 — invalid decision strings and
  out-of-range scores were previously accepted as valid verdicts.
- **`backend/crew_runner.py`** — added `_parse_json_output`/
  `_validate_verdict`, raising a new `AgentOutputError` (carrying the raw
  output for triage) on any parse or schema failure, instead of ever
  falling back to a keyword-searched, fabricated decision. **Why:** the
  direct fix for B03; the previous parser's own error text (containing the
  word "Failed") was literally being matched as a candidate failure signal.
- **`backend/database.py`** — added `DuplicateVerdictError` and the
  `uq_verdicts_canonical` partial unique index (exempting
  `decision='INVALID_OUTPUT'` rows, so a retry after a failure is never
  blocked); added `get_evaluation_public()`/PII-safe `list_evaluations()`
  excluding `resume_text` (finding B04); added `get_verdict_summaries()` to
  answer the evaluation list's verdict-summary needs in one batched query
  instead of one query per evaluation (the N+1 pattern noted in the
  frontend/efficiency findings table).
- **`backend/routes.py`** — every endpoint now takes `evaluation_id`
  explicitly instead of relying on shared session state; every synchronous
  `database.py` call is wrapped in `asyncio.to_thread` via a `_db()` helper
  (stops blocking the event loop on DB I/O — part of finding B06);
  `/final-decision` became idempotent (replays the persisted result on a
  second call rather than re-invoking the recommendation/committee agents);
  `overall_score` aggregation was fixed to average only rounds 1–3,
  excluding round 4's own already-synthesized score (finding Q04).
- **`backend/main.py`** — moved `load_dotenv()` to run before
  `from routes import router`/`from database import init_db` (previously,
  `database.py` could read `DATABASE_URL` at import time before the .env
  file had been loaded, silently missing it); the global exception handler
  no longer echoes raw exception text to the client (finding Q07's
  information-disclosure half) — it logs the real error server-side and
  returns a generic message.
- **Frontend (`interview/page.tsx`, `round/[id]/page.tsx`,
  `result/page.tsx`)** — removed the `POST /api/reset` call on mount
  (there is no shared session left to reset); every round/answer/result
  fetch now sends `?evaluation_id=<value from sessionStorage>`, matching
  the backend's new explicit-ID contract.

**Validation performed at the time:** static/structural review, AST-level
reproduction of the original bugs to confirm the fix (documented in
repository memory), and `TestClient`-based smoke tests of every
non-agent-calling endpoint against a real temporary SQLite database (agent-
calling endpoints could not be exercised live yet — no `GEMINI_API_KEY` or
alternative LLM endpoint was available until Session 2). A proper automated
regression suite for these fixes did not exist until Session 4 (this
session) — see above.
