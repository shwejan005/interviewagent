# Evalia: production agent and evaluation-platform roadmap

**Date:** 2026-09-27  
**Status:** proposed plan, not implemented or production-certified  
**Evidence:** [CODEBASE_REVIEW.md](CODEBASE_REVIEW.md)  
**Objective:** build a useful, safely operated interview product that demonstrates the evaluation, observability, backend ownership, and judgment required by Hyprel's founding engineer role.

## 1. Product direction

### The strongest positioning

**Evalia is an evidence-grounded interview copilot with a reusable agent reliability workbench.**

The interview application is the first real workload. The workbench proves whether its agent followed policy, supported claims with evidence, recovered from failures, and improved between releases.

Do not lead with “five agents decide who to hire.” Lead with:

> Every assessment links to evidence. Every uncertain or failed execution is surfaced. Every confirmed failure can become a regression case. Every release is tested against a versioned benchmark before reaching users.

This provides two connected products, built incrementally rather than as two independent platforms:

1. **Candidate/reviewer experience:** structured interview, reliable submission, evidence scorecard, reviewer approval and corrections.
2. **Engineering/risk experience:** trace explorer, evaluation datasets, deterministic graders, experiment comparison, review queue, release gates, audit export.

### Scope discipline

- Begin with one role family: backend/AI engineers, using one agreed competency rubric and a small set of assessment formats.
- Start text-first and human-reviewed. Practice/mock interviews and explicitly consented pilots are the lowest-risk starting use cases.
- Do not make autonomous adverse hiring decisions. Technical failures must never become candidate failures.
- Do not infer emotion, honesty, intelligence, protected characteristics, or “culture fit” from face, voice, name, accent, or behavioral proxies.
- Add voice only after the text workflow has reliable state, traces, and evaluation infrastructure.
- Extract reusable evaluation infrastructure after it supports a real workflow; prove reuse with one small synthetic BFSI scenario later.

## 2. Direct mapping to the job

| Hyprel requirement | What to build | Evidence to bring to the interview |
|---|---|---|
| Ship an agent real users depend on | A narrowly scoped deployed interview workflow with draft recovery and human review | Consented pilot usage, completion/failure reports, feedback, and fixes—not fabricated adoption. |
| Evaluate with datasets, graders, benchmarks | Versioned cases, deterministic assertions, human labels, semantic graders, holdout evaluation | A reproducible experiment report and an example where a plausible model answer fails the checks. |
| Replace “LLM judge says fine” | Executable rules for ownership, workflow, schema, evidence references, arithmetic, tool outcomes | A rule report explaining exactly why a run passed/failed and what remains subjective. |
| Turn production failures into tests | Trace-to-incident-to-reviewed-dataset workflow | One actual incident or clearly labeled injected failure, the regression test, and the release that fixed it. |
| Find important traces among thousands | Deterministic filters, failure signatures, stratified sampling, clustering and review prioritization | Measured actionable issues per reviewed trace versus a random-sampling baseline. |
| Strong TypeScript and backend depth | Typed frontend/API contracts, a TypeScript evaluation runner and policy/grader package, durable backend execution | Type-safe extensions, idempotency/concurrency tests, database migrations, and contract tests. |
| Logs, traces, metrics, alerting | OpenTelemetry plus one LLM observability platform and operational dashboards | A trace from request through worker/model/validator/database; a useful alert with a runbook. |
| Client-facing risk understanding | Rubric workshops, failure taxonomy, reviewer workflow, versioned sign-off | Examples of ambiguous requirements converted into explicit policy and unresolved judgment. |
| Voice agents | Optional voice interview with transcript confirmation and audio-specific tests | Barge-in/reconnection/transcription experiments; no personality inference from voice. |
| AWS/Postgres; optional Go | One reproducible AWS deployment path with managed Postgres and measured operations | Restore/rollback evidence and infrastructure decisions. Go only for a justified, measured rules component. |
| Coding-agent fluency | Small reviewed changes with independent tests and recorded trade-offs | Explain what coding agents wrote, how it was verified, and a case where their suggestion was rejected. |

## 3. Requirements and engineering principles

| ID | Requirement |
|---|---|
| REQ-001 | Isolated, authenticated evaluation state and authorized access for every actor. |
| REQ-002 | Durable execution with validated transitions, idempotent commands, bounded retries, and restart recovery. |
| REQ-003 | Strict contracts; invalid outputs never become business decisions. |
| REQ-004 | Versioned, job-relevant rubrics, evidence-linked claims, and human decision ownership. |
| REQ-005 | Reproducible system evaluations, independently validated graders, and meaningful release gates. |
| REQ-006 | End-to-end tracing, operational metrics, costs, useful alerts, and runbooks. |
| REQ-007 | Trace triage and a reviewed failure-to-regression lifecycle. |
| REQ-008 | Privacy, audit integrity, retention/deletion, secure model/tool boundaries, and tenant separation. |
| REQ-009 | Accessible, recoverable candidate and reviewer UX with typed contracts. |
| REQ-010 | Measured cost/performance improvements without degrading quality or safety. |
| REQ-011 | Reproducible build/deploy, real-Postgres tests, backups, restore, and rollback. |
| REQ-012 | A bounded optional voice capability evaluated separately from text reasoning. |
| REQ-013 | Honest product claims, pilot evidence, and an interview-ready engineering narrative. |

Principles: database as source of truth; deterministic enforcement around probabilistic models; least privilege; human adjudication of high-impact judgments; reproducible evidence over architectural complexity; explicit unknowns; test every changed behavior.

No formal migration specification, constitution, or topology artifacts exist. This is a standalone enhancement plan grounded in the companion review, not authorization to run a migration or deploy services. Framework-version upgrades should be separate, tested changes, not mixed with every behavioral refactor.

## 4. Target architecture and stack decisions

### Architecture

Browser → authenticated API → Postgres transaction containing command/state change + durable work item → worker → model/provider adapter → strict validation → deterministic checks → persisted evidence/report → human review.

An event stream or bounded polling feeds progress back to the browser. Telemetry follows the same run ID through every component. The evaluation workbench calls a versioned adapter and evaluates both captured and fresh executions.

### Recommended first production shape

| Layer | Recommendation | Why / trade-off |
|---|---|---|
| UI | Retain Next.js/TypeScript; extract typed client and shared scorecards | Preserve useful work; build evidence/recovery UX rather than a cosmetic rewrite. |
| Product API and interview runner | Initially retain FastAPI and the existing prompt workflow, behind explicit service interfaces | Fix correctness first. Do not introduce a second owner of the interview state machine. |
| Durable execution | Dedicated worker from the same backend codebase; start with a Postgres job table with atomic claims, leases, attempt records, and retries | Fits the first workload without adding several managed systems. Queue library/SQL implementation must be chosen and tested in the first architecture decision. |
| Database | Managed PostgreSQL, versioned migrations, explicit repository methods | Keep existing SQL investment. Use production-like Postgres tests; SQLite is not proof of concurrency/SQL parity. |
| TypeScript depth | An evaluation runner, deterministic grader/policy package, experiment CLI and workbench contracts | Delivers real backend/tooling ownership without rewriting the whole app for a keyword match. Interview runtime remains the sole lifecycle owner. |
| Telemetry | OpenTelemetry plus one of Langfuse/Braintrust/Arize; select Langfuse as the initial candidate after privacy/deployment review | Buy generic trace storage/viewing; build domain-specific graders, review workflows, and release decisions. Do not integrate all three. |
| Auth | A managed OIDC/session provider; validate credentials at the actual API, not only in Next.js | If Neon is the selected backend and there is no existing identity provider, evaluate Managed Better Auth first. Confirm current capabilities, region, and private-network compatibility before choosing. |
| Object storage | Add only for consented uploads/audio/evidence exports | Reuse the chosen provider's supported storage. Keep personal data out of generic public/CDN access paths. |
| Hosting | A pragmatic portfolio path: Next.js on Vercel, API + worker on AWS ECS/Fargate, managed Postgres, managed secrets and logging | One deployment story, no Kubernetes. If an existing Neon Postgres is in use, retain it unless requirements justify moving. Region/network/data residency must be decided with the pilot owner. |
| Larger-scale queue | Add SQS plus transactional outbox dispatch when moving execution to a managed queue is operationally justified | Do not dual-write a database change and queue message without a recovery strategy. Avoid Redis + SQS + Temporal simultaneously. |
| Go | Defer | Consider a narrow rules engine only after profiling or an actual integration requirement; preserve one canonical policy implementation. |

If TypeScript must own the product API later, move one bounded endpoint/workflow at a time behind the same contracts and behavior tests. Keep one writer for each state transition; avoid a permanent TypeScript proxy that merely forwards everything to Python.

### State, commands, and recovery

Separate three concepts that are conflated today:

- **Execution state:** queued, running, waiting for input, retry scheduled, failed, cancelled, completed.
- **Assessment state:** evidence sufficient, evidence insufficient, review required, reviewer approved.
- **Human hiring outcome:** an explicitly authorized human action, recorded separately from model suggestions.

Use evaluation-scoped commands such as `POST /v1/evaluations`, `POST /v1/evaluations/{id}/answers`, `POST /v1/evaluations/{id}/finalize`, and read-only `GET /v1/evaluations/{id}`. Return `202` with operation/run IDs for work that is not complete. Stream only validated progress events, not unvalidated partial verdicts.

Every mutation carries an idempotency key and, where appropriate, an expected state version. Within a transaction: verify ownership and allowed transition, persist input and the durable work item, then commit. Workers claim work atomically, hold short leases/heartbeats, and do not keep a database transaction open while calling a model.

Persist raw result metadata separately from the validated canonical result. Only the current attempt/version can publish a result. On worker crash, safely reclaim expired work. Cancellation prevents future steps and rejects late commits from cancelled attempts.

Promise **effectively-once state changes**, not exactly-once provider billing. A crash after a provider responds but before persistence can require a repeat call unless the provider supports usable idempotency. Record and budget for that boundary.

### Data evolution

Add concepts incrementally, not an enormous schema on day one:

1. **Foundation:** organizations, users/memberships, evaluations with owner/tenant and version, questions with IDs, answer versions, stage runs/attempts, durable jobs.
2. **Evidence:** rubric versions, prompt/model configurations, evidence spans, assessments, deterministic check results, human review actions.
3. **Workbench:** datasets and immutable versions, cases, grader versions, experiments, run results, incidents and regression links.
4. **Governance:** access/audit events, consent/retention references, artifact manifests; recording metadata only when voice is enabled.

Use appropriate foreign keys, tenant constraints, unique canonical-result/submission keys, bounded numeric/check constraints, JSONB for structured evidence, and indexes driven by access patterns. Preserve raw inputs under tighter permissions; list endpoints return summary projections only. Audit events are not a substitute for full event sourcing.

## 5. Evaluation engineering: the primary differentiator

### Two separate scorecards

**Candidate assessment:** what does the submitted evidence support about the agreed job competencies?

**Agent/system evaluation:** did the system follow the workflow, interpret evidence correctly, comply with access/policy constraints, handle uncertainty, and complete within its quality/cost budget?

A candidate's score is not a quality metric for the system. A plausible explanation or high model confidence is not verification.

### Evaluation layers

| Layer | Concrete checks | Limits |
|---|---|---|
| Contract | Required fields, enums, finite bounded numbers, schema version, unknown fields, valid question IDs | Valid JSON does not imply a correct assessment. |
| Workflow/security | Ownership, expected stage, no duplicate canonical result, no cross-tenant data, authorized tool use | Must be enforced in code/DB, not delegated to a judge. |
| Evidence | Source IDs exist, cited spans belong to this answer, exact quote/offset checks, redaction boundaries | Quote presence is deterministic; whether it supports a claim can require human/semantic review. |
| Objective domain checks | Score arithmetic from approved dimensions, required criteria coverage, reference tests for coding exercises | Use only where a legitimate oracle exists. Passing tests is not universal competence. |
| Semantic quality | Correctness, relevance, unsupported claims, rubric application, helpful feedback | Human labels plus calibrated judge assistance; preserve ambiguity rather than forcing a binary label. |
| Robustness | Prompt injection, irrelevant instructions, missing evidence, paraphrases, formatting, model faults | Finite tests demonstrate observed behavior, not universal immunity. |
| Experience/operations | Recovery, latency, cost, timeout behavior, accessible UI, voice turn-taking | Measure on specified workloads and environments. |

Use stable rule IDs, versions, expected versus observed values, severity, evidence references, and remediation text. Make rule results understandable to a reviewer who has never read the prompt.

Do not execute candidate code on the API host. Objective coding checks require an isolated sandbox with no production credentials, restricted/no network, CPU/memory/time limits, output limits, and disposable filesystems. Start with non-executing text exercises if that sandbox cannot be operated safely.

### Dataset strategy

Start with **50–100 carefully reviewed cases** for a narrow role/workflow, then grow toward **200–500 versioned cases** as observed failures justify coverage. These are proposed scope targets, not current assets or statistical proof of rare-event safety.

Each case contains a stable ID, provenance/consent classification, sanitized inputs or a captured trace, rubric and policy versions, expected assertions, acceptable semantic labels/ranges, severity, tags, human labels/disagreement, and dataset split.

Include:

- Clear successes and legitimate insufficient-evidence cases.
- Correct technical answers versus polished but incorrect answers.
- Missing questions, contradictory answers, unsupported resume claims.
- Invalid JSON, missing fields, impossible scores, provider timeouts/429s.
- Retry after uncertain submission, duplicate finalize, out-of-order answers, worker restart.
- Cross-tenant access attempts and leaked personal data canaries.
- Prompt injection in resumes, answers, and prior agent outputs.
- Paraphrases/format changes and carefully controlled irrelevant-attribute counterfactuals.

Split by candidate/scenario family and source, not random individual variants. Keep paraphrases and synthetic siblings in the same split. Maintain a development set, an adjudicated validation set, and a restricted held-out benchmark. Do not tune prompts on the holdout.

Use at least two reviewers for an initial ambiguous subset, record disagreement, refine the rubric, then adjudicate. Synthetic labels and model-generated tests are proposals, not ground truth. Do not use previous hire/reject decisions as unquestioned labels.

### Graders and model comparisons

1. Run cheap deterministic checks first.
2. Use a semantic judge only for dimensions without a reliable executable oracle.
3. Validate each judge against human-reviewed examples, including adversarial “looks good but wrong” cases. Test order, verbosity, and self-preference effects.
4. Compare the current seven-task design with a simpler structured baseline and a version with no committee. Add an independent verifier only if measurements justify it.
5. Compare provider/model/prompt/rubric versions on identical cases and report quality, latency, token use, cost, and uncertainty together.
6. Repeat a selected nondeterminism subset several times; report decision-flip rate and score spread. Temperature zero does not guarantee determinism.

Report separate error types: **false acceptance** of a defective agent run, **false rejection** of a valid run, and **abstention/review rate**. For candidate assessments, report agreement with a narrowly defined rubric—not “hiring accuracy.”

Use confidence intervals and slice counts. With zero observed failures in N independent cases, the approximate 95% upper bound is 3/N; 100 passing cases cannot demonstrate an extremely low incident rate, and correlated synthetic variants weaken that inference further.

Remove invented confidence defaults. If self-reported model confidence remains, label it as such. A calibrated probability needs a clearly defined correctness event, held-out labels, calibration testing, and drift monitoring. Do not weight hiring outcomes by arbitrary model confidence.

### Offline, pre-release, and online loop

- **Every PR:** code tests, deterministic fixtures, policy/security regressions, contract checks; no paid API secrets in untrusted fork jobs.
- **Protected nightly/pre-release:** budget-capped live-provider benchmark, repeated-run subset, paired comparison to the last accepted release.
- **Staging:** full candidate/reviewer journey, real-Postgres concurrency, worker crashes, provider faults, retention/deletion checks.
- **Pilot:** shadow evaluation, reviewer corrections, sampled production trace review, alerts and trend analysis.
- **Release:** reviewer-approved quality/risk report, canary, observation window, rollback criteria. Never silently turn a flaky critical test green by rerunning until it passes.

## 6. Trace triage and failure-to-regression workflow

### Instrument once, reuse everywhere

Carry `trace_id`, `evaluation_id`, `run_id`, `attempt_id`, organization scope, prompt/rubric/model/grader versions, deployment SHA, and schema version. Avoid candidate names/raw resumes as metrics labels. Trace HTTP admission, authorization, job claim/queue delay, context assembly, model request, output validation, rule checks, persistence, and review.

Record input/output token usage, provider request IDs where available, model latency, total job latency, retries, estimated cost with pricing version, error class, and cancellation/timeout outcomes. Track billed usage separately where reconciliable.

Default to redacted metadata. Raw sensitive content requires restricted storage, retention policy, deliberate access, and auditing. Do not request or expose hidden chain-of-thought; store concise justifications, tool facts, and evidence links.

### Find important traces

1. Filter deterministically: invalid outputs, policy failures, unsupported citations, repeated attempts, expensive runs, reviewer overrides, model-version regressions.
2. Group by stage/error signature and deduplicate recurring incidents.
3. Add semantic clustering of sanitized traces only if simple grouping misses useful patterns.
4. Sample across tenants, stages, model versions, input lengths, successful runs, and failure types. Keep a random-success sample to find false negatives.
5. Rank with explicit risk, novelty, frequency, and review-cost factors. Do not use model confidence as the sole selector.
6. Evaluate triage with precision@K/actionable findings per review hour and coverage against a manually audited sample. Correct for sampling bias in aggregate rate estimates.

### The closed loop

Trace → issue candidate → sanitized minimal reproduction → human-reviewed expected behavior → versioned regression case → failing baseline → fix → complete regression run → approved release → production verification.

An automation agent may draft test cases, propose clusters, and open a change request. It must not invent ground truth, alter the protected holdout, weaken a gate, merge its own policy change, or deploy without approval.

Each confirmed incident links to its trace, affected versions, severity/impact, owner, reviewed test, remediation, and verification result. Incidents with insufficient evidence remain unresolved rather than generating fake certainty.

## 7. Product experience and responsible use

### Candidate workflow

- Role/job-specific introduction with purpose, consent, privacy, AI limitations, and available accommodations.
- Pasted text first; later secure PDF/DOCX ingestion with file/type/size limits, scanning, extraction preview, and deletion policy.
- Stable question IDs, one question per answer, clear rubric expectations, allowed-AI/tool policy, and constrained follow-ups to fill evidence gaps.
- Server-backed progress, scoped draft autosave, reconnect/reload recovery, explicit submission acknowledgement, and safe retries.
- Visible queued/running/review-required states; no endless “agent thinking” screen or fake percentage.
- Correction/appeal path and accessible text alternative to voice. Avoid storing full sensitive answers persistently on shared devices without a deliberate policy.

### Reviewer workflow

- Separate login and role permissions for reviewer, evaluator engineer, and administrator.
- Evidence viewer next to the original answer/transcript: claim, cited span, rubric criterion, rule results, and unresolved uncertainty.
- Approve, correct, request more evidence, or escalate. Keep model output immutable as an observation; store human amendments as separate attributed events.
- Versioned rubric editor with anchored examples and approval before publication.
- Search/filter/pagination, consistent stage status, and metrics whose denominator/scope is explicit.
- Candidate-facing reports reveal only intended feedback; internal risk metadata and other candidates' data remain restricted.

### Workbench UI

Build five useful views: **Runs**, **Datasets**, **Experiments**, **Review queue**, and **Release/audit report**. Reuse an observability platform for generic trace trees. Build the domain-specific evidence comparison and regression action in Evalia.

Preserve the dark visual identity, but prioritize semantic controls, keyboard navigation, focus visibility, contrast testing, error/empty/loading states, reduced-motion support, and responsive layouts. Remove redundant fonts, unused dependencies/assets after usage checks, and unverified marketing claims.

### Privacy and governance

- Tenant-aware authorization at every resource boundary; optional Postgres row-level security as defense in depth with a tested pooling-compatible context strategy.
- Server-validated auth/session handling, expiring/revocable candidate invites, secure cookies and CSRF protection where cookie auth is used, or correctly validated issuer/audience/expiry for bearer tokens.
- Encryption in transit and at rest, managed secrets, least-privilege service identities, dependency/secret scanning, request size limits, per-actor quotas and budget enforcement.
- Minimize identity fields before model calls. Treat resumes, answers, retrieved documents, tool results and prior agent messages as untrusted content.
- Versioned retention and deletion rules across database, object storage, observability exports, derived datasets, and backup expiry; document exceptions/legal holds with qualified review.
- Tamper-evident artifact manifests and append-only reviewer events under restricted privileges. Hashes alone do not prevent an administrator from rewriting both data and hashes; stronger assurance may need separately controlled immutable storage/signatures.
- Map applicable privacy/employment/client policies with qualified stakeholders. Do not describe the product as DPDP/GDPR/SOC 2 compliant or BFSI-approved just because these controls exist.

## 8. Efficiency and reliability improvements

### Highest-value optimizations

1. Eliminate redundant or unproven model work: screening already suggests questions, while another task regenerates them. Reuse only after schema/rubric validation and quality comparison.
2. Benchmark whether recommendation plus committee adds measurable value. Replace duplicate synthesis with deterministic aggregation plus one concise evidence summary when the benchmark supports it.
3. Pass minimal typed evidence, not entire repeated resumes/verdict narratives. Record provenance so compression does not erase important uncertainty.
4. Use cheaper models for extraction/simple formatting only after slice-based evaluation. Reserve stronger checks for uncertain/high-risk cases; falling back to another model is a separately evaluated policy.
5. Apply bounded concurrency and tenant/provider token quotas. Reserve budget before starting; account for retries, judge calls, and cancelled work.
6. Cache only safely reusable, version-keyed artifacts. Never cache personalized verdicts across tenants. Prefer question/rubric/config caching before response caching.
7. Batch dashboard summaries, avoid `SELECT *`, use stable pagination, and measure query counts and payload bytes. Tune indexes using real query plans rather than guessing.
8. Remove synchronous DB calls from the async event-loop path, either through a properly scoped thread boundary or a planned async-driver change. Do not mix a driver rewrite into the first critical bug fix.

### Metrics

- Product: start-to-submit completion, abandonment by stage, recovery success, time to reviewed report, reviewer correction/override rate.
- Quality: invalid-output rate, unsupported-claim rate, rule violations, semantic disagreement, abstention, repeated-run variance, slice-specific regressions.
- Operations: availability, non-model API p50/p95/p99, queue age, job duration, timeout/error rates, retry counts, DB saturation, worker recovery.
- Economics: tokens and estimated/billed cost per completed interview, cost per correct/accepted run, cost of evals/reviews, infrastructure idle cost, storage/egress.

Cost per successful interview includes model calls, retries, evaluation judges, speech if enabled, infrastructure, and review effort divided by successful completions. Do not quote savings until the same benchmark/workload has been measured before and after.

## 9. Optional voice milestone

Build one narrow voice flow after the text-first quality gates pass:

- Consent and device preflight; visible recording state; a complete text fallback.
- Streaming speech-to-text, an explicit confirmed transcript, and question playback/TTS where useful.
- VAD/end-of-turn policy, barge-in handling, reconnect/cancel behavior, maximum duration, and audio retention controls.
- Score confirmed content against the same rubric; do not score accent, pitch, emotion, confidence, or perceived identity. Model speech errors must not count against candidates.
- Trace audio segment timing → transcript revision → model response → playback. Assess text reasoning and speech-system errors separately.

The voice test set should cover Indian English accents and consented language/code-switching examples, background noise, low bandwidth, silence, overlap, interruptions, reconnects, technical terminology, and numerals/negation. Measure WER where reference transcripts exist, but also task-critical semantic transcription errors, false end-of-turn, interruption recovery, turn latency, and completion rate.

Set voice latency and accuracy gates only after selecting the actual provider and measuring a baseline. No telephony integration or voice-based hiring inference is necessary for the first compelling demonstration.

## 10. Phased implementation plan and task breakdown

**Estimation assumptions:** one experienced full-time engineer, access to a reviewer/domain partner, a bounded model/cloud budget, one initial role/workflow, and no enterprise procurement delay. Tasks are unchecked because no implementation has been performed.

Expect roughly **10–14 weeks for a narrow, evaluated pilot**, not a universally production-ready hiring platform. An interview-ready vertical slice can be built earlier by reducing breadth. Voice and regulated-client readiness add time. Exit gates matter more than dates.

### P0 — Establish a trustworthy baseline (days 1–3)

**Requirements:** REQ-003, REQ-011, REQ-013. **Dependencies:** none.

- [ ] T001 [Plan:P0] Capture the current API contract and synthetic successful/failing flows using [backend/routes.py](backend/routes.py) and [backend/models.py](backend/models.py); preserve intentional behavior, not known bugs.
- [ ] T002 [Plan:P0] Add isolated regression tests for stale-state binding and malformed verdict cases identified in [backend/state.py](backend/state.py) and [backend/crew_runner.py](backend/crew_runner.py).
- [ ] T003 [Plan:P0] Establish canonical backend/frontend test and lint commands, pinned runtime policy, reproducible Python dependencies, and PR validation from [backend/requirements.txt](backend/requirements.txt) and [frontend/package.json](frontend/package.json).
- [ ] T004 [Plan:P0] Reconcile product claims in [README.md](README.md) and [frontend/app/page.tsx](frontend/app/page.tsx); inventory tracked generated verdicts and remove sensitive/generated material from tracking after review.

**Exit:** known critical behaviors have executable failing regressions; a fresh environment can run validation; demo/synthetic data is clearly labeled; no public launch.

### P1 — Safety and multi-user correctness (weeks 1–3)

**Requirements:** REQ-001, REQ-002, REQ-003, REQ-008. **Dependencies:** P0.

- [ ] T005 [Plan:P1] Replace runtime dictionary/files with evaluation-scoped persistence in [backend/state.py](backend/state.py), [backend/routes.py](backend/routes.py), and [backend/crew_runner.py](backend/crew_runner.py); keep constants separate from lifecycle state.
- [ ] T006 [Plan:P1] Introduce versioned schema migrations for tenant/owner, questions/answer versions, stage attempts, canonical-result uniqueness and state versions around [backend/database.py](backend/database.py).
- [ ] T007 [Plan:P1] Integrate managed identity and enforce object/tenant-level permissions at [backend/main.py](backend/main.py) and every relevant route; add negative authorization tests.
- [ ] T008 [Plan:P1] Use strict verdict schemas/enums in [backend/models.py](backend/models.py) and validate outputs in [backend/crew_runner.py](backend/crew_runner.py); remove decision/score/confidence fallbacks and duplicate prompt schemas where possible.
- [ ] T009 [Plan:P1] Add idempotency and expected-stage/version guards in [backend/routes.py](backend/routes.py); move finalization to a command and make all GET requests read-only.
- [ ] T010 [Plan:P1] Centralize settings before imports, validate required production configuration, remove raw internal errors, constrain input sizes, add abuse/spend limits, and return summary-only list data in [backend/main.py](backend/main.py), [backend/models.py](backend/models.py), and [backend/database.py](backend/database.py).

**Exit:** two users can interleave workflows without contamination; cross-tenant reads/writes fail; duplicate/out-of-order commands are handled correctly; malformed output never approves or rejects a candidate; all findings' regression tests pass.

### P2 — Durable execution and basic observability (weeks 3–4)

**Requirements:** REQ-002, REQ-006, REQ-010, REQ-011. **Dependencies:** P1.

- [ ] T011 [Plan:P2] Separate admission from execution in [backend/routes.py](backend/routes.py) and [backend/crew_runner.py](backend/crew_runner.py); add a durable worker/job repository and atomic claims/leases.
- [ ] T012 [Plan:P2] Implement per-stage/provider deadlines, typed transient errors, bounded exponential backoff with jitter, tenant-aware concurrency, cancellation and dead-letter/manual recovery.
- [ ] T013 [Plan:P2] Persist attempt IDs, model/prompt/rubric versions, usage, errors, timestamps and deployment provenance in the persistence layer.
- [ ] T014 [Plan:P2] Instrument request → queue → worker → model → validator → DB spans and structured logs; connect one reviewed observability destination.
- [ ] T015 [Plan:P2] Add safe liveness/readiness, graceful worker shutdown and operational alerts with runbooks; prove crash/restart recovery with model stubs.

**Exit:** an accepted job survives process loss; late/duplicate attempts cannot overwrite canonical state; every run has attributable status/cost/error telemetry; retry storms are bounded.

### P3 — Evidence, rubrics and evaluation harness (weeks 4–7)

**Requirements:** REQ-003, REQ-004, REQ-005, REQ-008, REQ-010. **Dependencies:** P1; P2 for end-to-end traces.

- [ ] T016 [Plan:P3] Define an approved, versioned role rubric with anchors, forbidden inferences and insufficient-evidence handling; replace vague scoring in [backend/tasks.py](backend/tasks.py) and [backend/models.py](backend/models.py).
- [ ] T017 [Plan:P3] Build evidence-span/reference validation and explicit policy checks; aggregate only original competency scores under a versioned rule, not the recommendation's duplicate score.
- [ ] T018 [Plan:P3] Add a provider-neutral evaluation adapter and TypeScript deterministic grader/runner package with strict contracts and a budget-capped CLI.
- [ ] T019 [Plan:P3] Curate and version the first benchmark cases, label an ambiguous subset with multiple reviewers, and separate scenario families across development/validation/holdout splits.
- [ ] T020 [Plan:P3] Validate semantic judges against adjudicated labels; compare the existing pipeline, a simpler baseline, and no-committee variant with repeated-run and slice reporting.
- [ ] T021 [Plan:P3] Add protected live-provider runs and release gate reports alongside deterministic PR tests; block critical policy regressions and report statistical uncertainty.

**Exit:** one-command replay produces versioned results; graders catch plausible-but-wrong outputs; the benchmark is not solely model-labeled; quality/cost trade-offs can be explained using measured evidence.

### P4 — Candidate recovery and human review (weeks 6–8)

**Requirements:** REQ-004, REQ-008, REQ-009, REQ-013. **Dependencies:** P1/P2; evidence UI depends on P3.

- [ ] T022 [Plan:P4] Replace browser-authoritative flow in [frontend/app/interview/page.tsx](frontend/app/interview/page.tsx), [frontend/app/round/[id]/page.tsx](frontend/app/round/[id]/page.tsx), and [frontend/app/result/page.tsx](frontend/app/result/page.tsx) with scoped URLs, typed API contracts, server resume and draft recovery.
- [ ] T023 [Plan:P4] Add queued/running/retry/review states, safe reconnect, accessible forms and status announcements; test no unintended carryover of answers between questions/rounds.
- [ ] T024 [Plan:P4] Evolve [frontend/app/dashboard/[id]/page.tsx](frontend/app/dashboard/[id]/page.tsx) into evidence review with approve/correct/escalate, attributed amendment history and controlled report export.
- [ ] T025 [Plan:P4] Add server-side search/filter/pagination and explicit error states to [frontend/app/dashboard/page.tsx](frontend/app/dashboard/page.tsx); batch summary queries and consolidate duplicated UI/contracts.
- [ ] T026 [Plan:P4] Add consent/privacy/accommodation flows and keyboard/screen-reader/contrast checks; remove or defer unused fullscreen/model assets and redundant font/dependency loading after usage verification.

**Exit:** refresh/reconnect does not lose acknowledged progress; the human reviewer can explain/correct every material assessment; candidate and internal views are isolated; browser journey tests pass.

### P5 — Reliability workbench and closed-loop learning (weeks 8–10)

**Requirements:** REQ-005, REQ-006, REQ-007, REQ-013. **Dependencies:** P2/P3/P4.

- [ ] T027 [Plan:P5] Build run/experiment comparison with rubric/model/version filters, trace deep links, failed assertions, and cost/latency deltas.
- [ ] T028 [Plan:P5] Implement failure signatures, deduplication, risk-based review sampling and a random-success baseline; add semantic clustering only when justified.
- [ ] T029 [Plan:P5] Add trace-to-regression drafting with sanitization, human approval, dataset versioning, incident linkage and protected release gates.
- [ ] T030 [Plan:P5] Measure triage yield versus random review and publish one reproducible failure-to-fix case study; test the adapter on one synthetic, policy-constrained BFSI support scenario without live financial actions or customer data.

**Exit:** a reviewer can move a real or labeled injected failure from trace to regression to fixed release; a second narrow workload can reuse the harness without copying the platform.

### P6 — Deployment hardening and controlled pilot (weeks 10–14)

**Requirements:** REQ-006, REQ-008, REQ-010, REQ-011, REQ-013. **Dependencies:** core P1–P5 gates; basic CI/deployment work starts earlier.

- [ ] T031 [Plan:P6] Produce reproducible API/worker builds, one chosen infrastructure/deployment definition, isolated environments, managed secrets and a documented frontend/backend configuration based on [frontend/vercel.json](frontend/vercel.json) and [frontend/next.config.js](frontend/next.config.js).
- [ ] T032 [Plan:P6] Run real-Postgres contract/concurrency tests, dependency and secret scans, production-like load/fault tests, migration rehearsal and rollback/canary checks.
- [ ] T033 [Plan:P6] Implement and verify data retention/deletion across storage/telemetry, audit integrity, backup restore and operational access control.
- [ ] T034 [Plan:P6] Run a small consented pilot, collect reviewer/user feedback, track actual reliability/cost/quality, resolve material findings and publish honest release limitations.

**Exit:** restore and rollback have been exercised; operational ownership is assigned; access/privacy review is complete; benchmark and pilot evidence support the stated scope. Passing these gates does not imply certification or universal hiring validity.

### P7 — Optional voice extension (additional 2–4+ weeks)

**Requirements:** REQ-005, REQ-006, REQ-008, REQ-009, REQ-012. **Dependencies:** text-first P1–P6 controls.

- [ ] T035 [Plan:P7] Implement consented voice input/transcript confirmation and optional question playback with a text fallback, bounded storage and reconnect/cancel controls.
- [ ] T036 [Plan:P7] Add speech-specific datasets, turn-level traces, interruption/noise/reconnection tests and separately reported speech-versus-reasoning errors; pilot only after agreed gates pass.

**Exit:** a voice failure cannot silently alter the confirmed answer or candidate assessment; quality is measured across the supported input conditions.

## 11. Validation strategy and release acceptance

### Validation stack

Mixed API + client-side web application. Proposed stack: pytest/httpx for backend behavior; real PostgreSQL for persistence/concurrency; Vitest for TypeScript graders/components; Playwright for browser journeys; a budget-capped live-model runner for semantic evals; k6 or equivalent for load/fault exercises.

Current validation availability is limited: the Python environment was selected and isolated source checks ran; frontend dependencies are absent; Docker daemon/cloud credentials/browser compatibility have not been checked. These are future execution prerequisites, not claims of available infrastructure.

Use isolated database schemas/databases and synthetic fixtures with deterministic IDs. A local real Postgres or a schema-only development branch is acceptable when containers are unavailable. SQLite-only tests may cover some unit behavior but cannot satisfy the Postgres concurrency/migration gate. API-only tests cannot replace browser recovery/accessibility tests.

### Required journeys

1. Authorized user creates an evaluation, completes text answers, and receives a reviewed evidence report.
2. A second tenant attempts reads, writes, trace access, export and stream subscription against the first tenant; every unauthorized path fails.
3. Concurrent duplicate submission/finalization produces one canonical effect and a consistent response.
4. Worker dies before/after a provider call; recovery preserves acknowledged answers and prevents stale commits.
5. Provider timeout, 429, invalid JSON, missing evidence and invalid score produce explicit operational/review states, never automatic candidate rejection.
6. Browser refresh, reconnect, navigation and retry restore the correct question/draft without cross-round carryover.
7. Human correction creates attributed history and a reviewed regression proposal, without overwriting raw model evidence.
8. Retention/deletion, audit export, backup restore and rollback behave as documented.

### Proposed pilot targets—not measured results

| Area | Initial acceptance proposal |
|---|---|
| Critical correctness/security | All curated authorization, tenant-isolation, idempotency, transition and malformed-output regression tests pass; no unresolved critical exposure. This is a finite test claim, not zero lifetime risk. |
| Invalid outputs | 100% of deliberately malformed fixtures blocked from canonical business verdicts; invalid live outputs explicitly counted and surfaced. |
| Recovery | Every acknowledged test submission survives the defined API/worker fault scenarios; cancelled/stale attempts cannot publish. |
| Evidence | All published assessment claims have valid source references or are explicitly marked unsupported/insufficient; semantic support is separately sampled/reviewed. |
| Traceability | Every canonical test run links to input version, rubric/prompt/model config, attempt, validator results and deployment version. |
| Non-model API | Provisional p95 under 500 ms at an agreed pilot load, e.g. 20 concurrent active sessions; publish workload/environment and exclusions. |
| LLM execution | Set stage completion/deadline targets after real-provider baseline. Separately report queue and provider time. No blanket sub-two-minute claim. |
| Quality gate | No critical policy regressions; paired semantic-quality results meet a pre-agreed non-inferiority margin with slice counts/uncertainty and human sign-off. Choose the margin from label variability and risk, not convenience. |
| Cost | Per-run and daily budgets enforced; cost per accepted completion reported. Set numeric budgets only after measuring the initial workload. |
| Service operation | Provisional 99.5% monthly API availability target; report job/provider success separately, with clear maintenance/exclusion policy. |
| Disaster recovery | Provisional pilot RPO ≤24h and RTO ≤4h, only accepted after a restore exercise. Tighten if user impact requires it. |
| Accessibility | Automated checks plus manual keyboard/recovery testing for core flows; broader WCAG conformance requires a dedicated audit. |

Observability must distinguish “HTTP accepted” from “job completed correctly.” Critical failures trigger a safe halt/review or rollout pause, not merely a notification.

## 12. Interview demonstration and evidence pack

### A ten-minute demo

1. Show a normal interview and the reviewer evidence scorecard.
2. Show a realistic polished-but-wrong answer or injected parser failure that an unconstrained judge accepts.
3. Open its trace: input version, model version, rule result, evidence, cost, timing and uncertainty.
4. Show why a deterministic or evidence-grounded check catches the issue; acknowledge any remaining subjective judgment.
5. Convert it into a sanitized, reviewed regression case.
6. Compare a baseline and fix on the full benchmark, not only that example; show cost/latency trade-offs and confidence intervals.
7. Show a blocked release for the broken version and an approved report for the fixed one.
8. Demonstrate concurrent users or worker-crash recovery. Add a short voice fault demo only if it is genuinely complete.

The currently reproduced parser problem is a strong **development-discovered failure**: invalid output becomes `FAIL` because of the parser's own error text. Do not present it as a production incident or as an LLM-judge false-positive story unless separately demonstrated.

### Bring these artifacts

- A working, access-controlled demo with clearly labeled synthetic data and an offline replay mode for provider outages.
- Architecture decisions explaining retained Python, meaningful TypeScript ownership, queue semantics, and deferred complexity.
- A versioned dataset card, label policy, grader validation results, experiment report and risk limitations.
- One real or clearly labeled injected incident report with trace → test → fix → release evidence.
- A dashboard of measured usage, errors, latency, costs and reviewer corrections from a consented pilot.
- A short restore/rollback demonstration and an operations runbook.
- A candid account of coding-agent use and independent verification. No invented customer logos, adoption, certification or savings.

### Fastest compelling slice if the interview is soon

Prioritize P0/P1 correctness and auth, a narrow P2 durable traceable flow, one P3 rubric with 50 reviewed cases and deterministic graders, a minimal P4 evidence/review screen, and one P5 failure-to-regression demonstration. Use a controlled deployment. Defer elaborate clustering, voice, broad role coverage, enterprise SSO and multi-cloud portability.

## 13. Requirement mapping

| Requirement | Plan phases | Completion evidence |
|---|---|---|
| REQ-001 | P1 | Tenant/owner constraints, negative authorization tests, interleaved-user journey. |
| REQ-002 | P1–P2 | Durable attempts, idempotency/transition tests, restart/cancellation evidence. |
| REQ-003 | P0–P1, P3 | Strict schemas, invalid-output fixtures, contract and policy gate reports. |
| REQ-004 | P3–P4 | Approved rubric, cited scorecards, attributed human review and correction history. |
| REQ-005 | P3, P5, P7 | Versioned datasets/graders, held-out comparisons and release reports. |
| REQ-006 | P2, P5–P7 | Cross-component traces, usage/cost/error dashboards, alerts and runbooks. |
| REQ-007 | P5 | Reviewed trace-to-regression flow and measured triage baseline. |
| REQ-008 | P1, P3–P4, P6–P7 | Access controls, redaction/retention/deletion tests, evidence integrity and consent. |
| REQ-009 | P4, P7 | Typed client, recoverable browser flows, accessible reviewer and candidate UI. |
| REQ-010 | P2–P3, P6 | Measured quality/cost/latency comparison and bounded execution budgets. |
| REQ-011 | P0, P2, P6 | Reproducible CI/deploy, real-Postgres validation, migration/restore/rollback evidence. |
| REQ-012 | P7 | Confirmed transcripts, speech fault tests, supported-condition quality report. |
| REQ-013 | P0, P4–P6 | Corrected claims, consented pilot evidence and interview demo/case study. |

## 14. Decisions to confirm before implementation

These do not block this planning review but change implementation cost and launch risk:

- Interview date and available weekly effort: build a bounded slice rather than promise the whole roadmap.
- First real user: candidate practice, recruiter-assisted screening, or an actual employer pilot; who owns the rubric and review?
- Data permissions and allowed retention/model/telemetry destinations; applicable region and client requirements.
- Existing database/auth/cloud accounts to preserve, and monthly cloud/model budget.
- Expected pilot concurrency, supported languages, accessibility accommodations and recovery needs.
- Whether meaningful TypeScript eval tooling is sufficient initially or the product API itself must become TypeScript.

**First implementation milestone:** isolated authenticated state + strict output validation + regression tests + one traceable evidence report. That is more credible than adding another agent to the current architecture.