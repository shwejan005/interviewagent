# Product Improvement Plan

Status: approved baseline assessment (2026-10-01), superseded in part by subsequent implementation. The core application-linked screening/interview/report path, browser transcript correction and draft recovery, interview reminders/expiry, in-app notifications, and human interview rounds/scorecards have since been implemented. This document preserves the original backlog; its "current-state" and "Gaps found" sections describe the baseline date, not necessarily today's tree. See [AI_INTERVIEW_ARCHITECTURE_PLAN.md](AI_INTERVIEW_ARCHITECTURE_PLAN.md), [LIVE_INTERVIEW_AND_HIRING_ROUNDS_PLAN.md](LIVE_INTERVIEW_AND_HIRING_ROUNDS_PLAN.md), and [TESTING.md](TESTING.md) for current boundaries and verification.
Scope: candidate and recruiter experience, process redesign, admin-governed model access, trust and quality, privacy, durability, and the test strategy that proves each change.

This plan is grounded in the current code (cited per section), not in the aspirational docs. It does not claim production certification or legal compliance; India-specific legal review and operating defaults are recorded in section 13.

## 1. Guiding principles

1. **Human decides.** No automated rejection (D-10). AI output is evidence for a person. Every adverse outcome is confirmed by a human and is explainable to the candidate.
2. **Never lose candidate work.** Answers, profile edits, and resume imports survive refresh, network loss, worker failure, and deploys.
3. **Technical failure is never a candidate failure.** Provider outage, job exhaustion, or timeout routes to `REVIEW_REQUIRED` or a retry, never to a negative signal.
4. **Always show the next action.** Every screen for a candidate or recruiter states what is happening, who owns the next step, and what the user can do.
5. **Honest scope.** Text-first. No emotion, personality, accent, or culture-fit inference. No candidate code execution on the API host. Prep performance must not influence hiring ranking.
6. **Prove it.** Each change ships with unit or API tests, a Playwright regression where a UI is involved, and an exit gate (section 11).

## 2. Current-state assessment

What exists and works:

- Auth: register, login, refresh, export, delete, RBAC capabilities, hash-chained audit ([backend/app/auth/controller.py](../backend/app/auth/controller.py)).
- Candidate: profile (experience, education, skills, preferences, vault), resume parse/import, recommended jobs, applications with timeline and withdraw, referrals, interviews list ([backend/app/candidate/controller.py](../backend/app/candidate/controller.py)).
- Recruiter: campaigns and postings with edit/close/archive/restore, applications, transitions, screening, interview scheduling, candidate search, referrals, funnel analytics, evaluation criteria ([backend/app/hiring/controller.py](../backend/app/hiring/controller.py)).
- AI interview: durable screening, question plan, consent, one-question-at-a-time text interview, per-answer assessment, report, screening exception approval, job-exhaustion fallback to review ([backend/app/ai_interview/](../backend/app/ai_interview/)).
- Durable worker with leases, heartbeats, retry/backoff and cancellation ([backend/app/worker/job_worker.py](../backend/app/worker/job_worker.py)).
- Prep suite and PostgreSQL RLS with CI verification.

Gaps found by reading the flows (verified by search; none of these exist today):

| # | Gap | Evidence |
|---|---|---|
| G1 | No password reset or email verification. Registration reveals taken emails (noted in code as deferred). | No forgot/reset/verify code in backend or frontend. |
| G2 | Candidate AI interview answer drafts are lost on refresh or tab close. Only server-saved answers persist. | [ai-interview page](../frontend/app/ai-interview/[applicationId]/page.tsx) holds the draft in component state only. |
| G3 | No pause/resume messaging, per-question time expectations, or answer-length guidance. No candidate-visible report or feedback after completion. | Same page; completion shows a static message. |
| G4 | No accommodation request, alternative format, or appeal path. | No such endpoints or UI. |
| G5 | Notifications are SMTP-only and best-effort. No in-app notification center, no preferences, no delivery state visible to the user. | [backend/app/shared/notifications.py](../backend/app/shared/notifications.py). |
| G6 | Interview scheduling has no candidate confirm/reschedule, no calendar file, no time zone handling, no reminders. | Hiring controller interview endpoints are recruiter-only create/cancel. |
| G7 | No retention or deletion job for stale applications, interview text, and resumes beyond the manual data-subject delete. | No purge code. |
| G8 | Interview expiry and reminders: unique-active index exists but nothing expires an idle `INTERVIEW_READY` or `IN_PROGRESS` run. | Schema has `EXPIRED`; no worker job sets it. |
| G9 | Recruiter has evidence review per application but no bulk triage queue, no SLA indicators, no exception queue across a posting. | Review is per application. |
| G10 | Posting policy changes are not versioned in the recruiter UI; candidates in flight are pinned but recruiters cannot see which version a candidate was assessed under. | Pinned policy snapshot exists in repository; not surfaced. |
| G11 | Quality program is partial: no rubric calibration set, prompt-injection suite, fairness/adverse-impact check, or live-provider gated evaluation. | Evaluation harness exists but is narrow. |
| G12 | Operational gaps: in-memory rate limiting, no per-tenant job caps, no provider spend budget, no runbooks or dashboards. | [backend/tests/test_rate_limit.py](../backend/tests/test_rate_limit.py) covers in-memory only. |
| G13 | Accessibility not audited (live regions beyond the loading skeleton, focus management in modals, keyboard flows). | One `aria-live` use found. |
| G14 | PRODUCT_BLUEPRINT status is stale relative to the implementation. | Docs review. |
| G15 | Model choice is environment-wide and effectively hard-coded; there is no approved catalog, per-user access grant/revocation, user preference, or complete spend metering. | Model globals are constructed in `backend/app/evaluation/agents.py`; no model administration UI/API exists. |

## 3. Candidate onboarding redesign

Target flow: **Register, verify email, choose intent, import or build profile, readiness check, apply.**

Changes:

1. **Email verification and password reset (G1).** Single-use, hashed, expiring tokens; generic responses so registration and reset do not leak whether an email exists; rate limited per IP and per email; audit events. Unverified accounts can build a profile but cannot apply.
2. **Intent step.** After first login ask: looking for jobs, preparing for interviews, or both. Routes to the right home and hides irrelevant navigation. Recruiters arrive through invitations and are never asked.
3. **Resume-first profile.** Keep parse/import. Add a diff-style review (what will be added or replaced), explicit confirmation, and keep the original file text for the screening evidence trail.
4. **Profile readiness meter.** A computed checklist (skills, experience, contact, resume, preferences) with specific missing items and what each unlocks. Applying with an incomplete profile shows exactly which fields the posting requires, not a generic error.
5. **First-run guidance.** Empty states already exist; add one next-best-action per page.

Acceptance: a new user can reach "applied" without guessing; reset and verification work end to end; no enumeration through timing or message differences.

## 4. Application and tracker redesign (candidate)

1. **Clear stage model.** One candidate-facing vocabulary mapped from internal stages: Submitted, Screening, Interview ready, Interview in progress, Under review, Interview scheduled, Decision. Each shows owner of next step and an expected-time hint.
2. **In-app notification center (G5).** Persisted notifications (type, application, read state), a bell with unread count in the navbar, email as an additional channel not the only channel. Preferences per event type. Delivery failures are recorded and visible to admins, never block state changes.
3. **Withdraw, appeal, accommodation (G4).** Withdraw stays. Add: request accommodation (extra time, alternative format) and request human review of an outcome. Both create a recruiter-visible task with SLA and an audit event. The system never decides these automatically.
4. **Scheduling (G6).** Candidate sees proposed slots with their local time zone, confirms or requests another time, and downloads an `.ics`. Reminder notification before the slot. Calendar provider integrations are out of scope; use `.ics` only.
5. **Data self-service.** Existing export and delete get a status page; add a clear description of what is retained and for how long (section 9).

## 5. AI interview flow redesign

Current flow is sound; the changes make it recoverable, transparent, and fair.

1. **Draft durability (G2).** Debounced autosave of the in-progress answer, keyed by application and turn, to the server (preferred) with a local fallback; restore on reload; clear on successful submit. Prevent double submit; handle a 409 turn-already-answered by reloading state rather than showing an error.
2. **Pause and resume (G3).** Explicit "Save and continue later" with a stated expiry window and a reminder notification. Idle runs expire through a worker job (G8): `INTERVIEW_READY` and `IN_PROGRESS` move to `EXPIRED` after a configurable window with a recruiter-visible reason and an option to reissue. Reissue creates a new run; the unique-active index already permits this.
3. **Transparent progress.** Show question N of M (or phase progress when the count is adaptive), approximate remaining time, and word guidance. No timing pressure beyond the stated window.
4. **Consent record.** Notice text is versioned; store the exact notice version and timestamp (already present) and show candidates a copy of what they accepted.
5. **Fallbacks.** If the AI service fails mid-interview the candidate sees "saved, your hiring team will follow up", the run is marked `REVIEW_REQUIRED`, and the recruiter gets a task to continue manually or reissue. Already partially built; add the recruiter task and tests.
6. **Candidate feedback.** Support feedback, but make it opt-in per posting and off by default. Only after a human decision may a recruiter approve a short, job-related, evidence-based summary. Never expose raw model scores, rankings, confidence, or private recruiter notes.
7. **Voice.** Out of scope for this plan; the notice already states text only. No microphone or camera is requested.
8. **Per-attempt history.** Keep reports per run so reissues do not overwrite earlier evidence.

## 6. Recruiter redesign

1. **Work queue.** A single "needs attention" view across postings: screening exceptions, `REVIEW_REQUIRED`, reports ready, accommodation and appeal requests, expiring interviews. Sort by age with SLA badges (G9).
2. **Evidence review.** Side-by-side: criteria, per-competency evidence with quotes (quotes are already validated as grounded), candidate answers, and the policy version used (G10). Decision actions require a reason and are audited.
3. **Posting policy versioning (G10).** Edits to criteria create a new version; show how many in-flight candidates are pinned to each. Warn before a change that would alter requirements.
4. **Bulk actions.** Multi-select transition with a single confirmation and per-item results; a failure on one item does not roll back the others and is reported clearly.
5. **Scheduling.** Propose multiple slots, see confirmations, reschedule and cancel with automatic candidate notification. Panel availability stays manual in this phase.
6. **Analytics.** Keep funnel and selection rates. Add time-in-stage, drop-off by stage, and an adverse-impact view on selection rates with a clear "indicative, not a legal determination" label. Small cells are suppressed to protect candidates.
7. **Export.** CSV or PDF of a candidate's evidence packet for hiring-manager review, audit-logged and permission-gated.

## 7. Trust and quality program (G11)

1. **Rubric calibration set.** Curated answer samples per competency and level with expected score bands, versioned alongside the rubric. A regression run flags drift when prompts, models, or the rubric change.
2. **Prompt-injection suite.** Answers and resumes that try to override instructions, leak the system prompt, or inflate scores. Assert the assessment ignores them and the evidence-quote validator rejects ungrounded claims.
3. **Evidence validation.** Keep grounded-quote checks; add numeric bounds and schema-strict parsing with a safe fallback to review.
4. **Fairness checks.** Counterfactual tests (swap names or gendered terms, equivalent content) assert score stability within tolerance; fail the gate if exceeded.
5. **Live-provider gated eval.** An opt-in job (not in default CI) runs the calibration set against the real provider and records results for comparison. Default CI uses recorded or deterministic doubles.
6. **Disclosure.** Candidate and recruiter surfaces state what the AI did and did not do.

## 8. Admin-governed model access and spend (G15)

This is a required product capability, not an optional deployment setting.

1. **Model catalog.** Platform admins configure provider, model identifier, endpoint (where applicable), status, supported task types, context/output limits, and pricing metadata. Provider credentials must be stored as secret references or in an encrypted secret store and are never returned by APIs or exposed in logs. Do not accept arbitrary model IDs from a client.
2. **Approval and grants.** Platform admins approve or disable catalog entries. Organization owners/admins grant or revoke only approved models for their organization members. Every change is capability-checked and recorded in the Tier-1 audit trail. A user-facing catalog returns only active models the caller is authorized to use.
3. **User selection boundaries.** Users may choose among granted models for prep and other non-hiring assistance. Hiring evaluation models are selected by authorized organization policy and pinned, with model/provider/version metadata, to the posting/run. Candidates cannot change the model evaluating their application. Recheck grants before queued work executes.
4. **Adapters, not a global model.** Replace the module-global model instance with a per-request factory and explicit provider adapters across evaluation, AI interview, prep, resume assistance, and every future LLM call. A provider call without an authorized model selection fails closed.
5. **Usage metering.** Record provider, model, task, organization/user, request correlation ID, provider-reported token usage, estimated INR cost, and outcome. Do not store prompts, answers, secrets, or candidate PII in metering rows. Admins see aggregate spend; ordinary users see only their own usage and allowance.
6. **Pilot caps.** Hard caps: ₹500 per user, ₹5,000 per organization, and ₹25,000 platform-wide per calendar month, with alerts at 80% (₹400/₹4,000/₹20,000). These are conservative, configurable pilot guardrails, not a provider-cost estimate. Enforce an estimated upper-bound cost before dispatch and reconcile against provider usage after completion. Require pricing metadata and bounded output before a model can be enabled; do not permit unmetered models for hiring assessment.
7. **Cap behavior.** At a hiring-related cap or provider failure, stop automated work, preserve candidate progress, mark the case for human review, and notify the hiring team—never make or imply a negative candidate decision. For non-hiring AI, explain the cap and reset date. Overrides require a reason and audit event.
8. **Validation.** Test grants/revocations (including queued jobs), cross-tenant isolation, secret non-disclosure, model pinning, cost estimation/reconciliation, cap boundaries, and safe fallback for every task type.

## 9. Privacy and retention (G7)

1. **Retention policy as data.** Configurable per-organization defaults: application records for 24 months; resumes, interview text, and reports for 12 months after last activity. These are product defaults subject to India-specific legal review, not a compliance determination.
2. **Retention worker.** Scheduled job that deletes or anonymizes past-retention data, writes an audit event with counts only, and supports a dry-run mode.
3. **Consent versioning.** Notices carry a version and effective date; changed notices require re-acknowledgement before the next AI step (already enforced at interview start; extend to data-processing notices).
4. **Provider review checklist.** Document what is sent to the model provider, redaction applied, and data-retention terms to confirm before launch.
5. **Subject requests.** Existing export/delete get regression tests covering the new tables (notifications, drafts, accommodation requests).

## 10. Durability and operations (G12)

1. **PostgreSQL parity.** Run the full backend suite against PG17 in CI, not only the verify script; add RLS tests for each new table.
2. **Concurrency tests.** Double-start, double-submit, concurrent transitions, worker crash mid-job, and lease loss; assert exactly-once effects through idempotency keys.
3. **Worker controls.** Per-tenant concurrency caps, dead-job inspection and manual retry for admins, heartbeat age alert.
4. **Rate limits.** Shared-store rate limiting (database or Redis) replacing in-memory. Model spend limits are defined and enforced under G15.
5. **Observability.** Structured events exist; add counters (jobs queued, failed, exhausted, age of oldest job), a health endpoint that includes worker liveness, and a short runbook for each alert.
6. **Backups and migration safety.** Documented backup and restore check, and migration tests that run forward on a populated database.

## 11. Testing and regression strategy

| Layer | Scope | Gate |
|---|---|---|
| Backend unit | Services, validators, retention logic, token handling | pytest green, new code covered by tests written first |
| Backend API | Each endpoint: happy path, authz denial, tenant isolation, validation, idempotency | No endpoint without a denial-path test |
| Concurrency | Races listed in section 10 | Deterministic, repeated N times in CI |
| PostgreSQL | Full suite plus RLS verify | Green on PG17 |
| Frontend typecheck | `npm run typecheck` | Zero errors |
| Playwright E2E (mocked API) | Onboarding, apply, interview with refresh recovery, notification center, recruiter queue, scheduling | Existing 13 stay green; every new flow adds specs |
| Accessibility | Keyboard-only run of each flow and automated axe checks in Playwright | No critical violations (G13) |
| Quality evals | Calibration, injection, fairness | Pass thresholds; live-provider run on demand |
| Regression matrix | Role routing, lifecycle (campaign/posting), profile and criteria, prep recovery, datetime picker, AI interview flow | Run in full before each phase closes |

Exit gate for every phase: backend suite, typecheck, full Playwright, `git diff --check`, docs updated (CHANGELOG, GAP_ANALYSIS, API_REFERENCE, DATA_MODEL where applicable), and honest status wording.

## 12. Phased delivery

**Phase A. Safety net and candidate trust (highest value, lowest risk)**
- G1 email verification and password reset.
- G2 answer draft autosave and recovery.
- G8 interview expiry job and reissue.
- G5 in-app notification center (backend table, API, navbar bell, email as secondary channel).
- Tests: auth abuse cases, enumeration, draft recovery E2E, expiry and reissue API, notification isolation.

**Phase B. Admin-governed model access (required before multi-model user selection or production claims)**
- G15 provider/model catalog, secure credential references, platform approval, organization/member grants and revocation, user model preference for non-hiring tasks, pinned hiring model policy, usage metering, and pilot hard caps.
- Tests: every AI integration path, grant/revoke races, queued-job revalidation, tenant isolation, audit coverage, secret redaction, budget boundaries, and human-review fallback.

**Phase C. Recruiter throughput**
- G9 work queue with SLA badges and exception handling.
- G10 posting policy versioning surfaced in UI.
- G4 accommodation and appeal requests (candidate create, recruiter resolve).
- Bulk transition with per-item results.
- Tests: queue ordering and tenant isolation, policy pinning, request lifecycle, bulk partial failure.

**Phase D. Scheduling and feedback**
- G6 slot proposal, candidate confirm/reschedule, `.ics`, reminders, time zones.
- Candidate feedback release (off by default; per-posting opt-in and human-approved).
- Evidence packet export.
- Tests: time zone and daylight-saving edge cases, double-booking, reminder idempotency.

**Phase E. Quality, privacy, operations**
- G11 calibration, injection, fairness suites and gated live eval.
- G7 retention worker with dry run.
- G12 PG parity in CI, concurrency tests, shared rate limiting, runbooks.
- G13 accessibility audit and fixes. G14 refresh PRODUCT_BLUEPRINT.

Sequencing rationale: Phase A removes the most likely ways to lose a candidate or lock them out; B establishes controlled and metered model choice before surfacing it; C and D improve recruiter throughput and scheduling; E hardens the product before any launch claim.

## 13. Confirmed decisions and policy defaults
- **Jurisdiction:** India is the initial target. This is an operating assumption, not a legal-compliance conclusion; obtain qualified counsel review of notices, retention, and applicable AI/employment requirements before launch.
- **Email:** SMTP only for now. Persisted in-app notifications remain the source of truth; SMTP is the delivery mechanism for verification, reset, and reminders.
- **Model control:** Admin-managed catalog and provider configuration; admins approve and grant/revoke access. Users see only active models granted to them. User selection is for prep and other non-hiring AI; hiring evaluations use an authorized, pinned model the candidate cannot change.
- **Budget:** Pilot hard caps of ₹500/user/month, ₹5,000/organization/month, and ₹25,000/platform/month, with 80% alerts. Caps are configurable, conservative pilot guardrails and must be enforced using metered usage plus bounded estimates.
- **Interview modality:** Text only; no microphone or camera.
- **Calendar:** `.ics` only; no calendar-provider integration.
- **Candidate feedback:** Supported but off by default per posting; after a human decision, a recruiter may approve a short evidence-based summary. No raw scores, rankings, confidence, or private notes.
- **Retention defaults:** Applications 24 months; resumes, interview text, and reports 12 months after last activity; drafts cleared on submission and shortly after expiry. These are configurable product defaults subject to India-specific legal review.

## 14. Risks

| Risk | Mitigation |
|---|---|
| Scope growth across four phases | Phase exit gates; ship A before starting B |
| Email deliverability blocks verification | Provider decision first; tracker and in-app notification remain the source of truth |
| Model drift changes scores | Calibration regression and pinned rubric/prompt versions |
| Retention job deletes wrong data | Dry-run first, counts-only audit, PG and SQLite tests with fixtures |
| Concurrency regressions with new states | Race tests and idempotency keys for every new write path |
| Claims outrun evidence | Status wording reviewed at each phase close; no certification claims |

## 15. Success measures

- Candidates: share who complete an started interview, share who recover a draft after reload, time from apply to next visible status, support-request rate for "where is my application".
- Recruiters: median time from report ready to decision, share of exceptions resolved within SLA, bulk action error rate.
- Platform: oldest queued job age, failed or exhausted job rate, notification delivery success, zero cross-tenant data access in tests.
- Quality: calibration score drift within band, injection and fairness suites passing.
