# Evalia: evidence-based codebase review

**Reviewed:** 2026-09-27. **Purpose:** production enhancement planning and alignment with Hyprel's founding engineer role. **Companion:** [PRODUCTION_ROADMAP.md](PRODUCTION_ROADMAP.md).

## 1. Scope and evidence limits

Reviewed the authored backend modules, frontend routes/components/hooks/styles, dependency manifests, tracked-file inventory, environment example, launcher, database configuration, and deployment configuration. Dependency/vendor directories, private environment files, real databases, and binary assets were not audited. Existing verdict files are not treated as a benchmark or representative production data.

Evidence levels used below:

- **Reproduced:** executed the actual functions extracted from source using Python AST, with filesystem operations mocked. No application import, database access, or model call.
- **Static:** directly supported by source inspection; the live behavior or exploit has not been exercised.
- **Unverified:** needs installation, integration testing, browser testing, production telemetry, or stakeholder input.

Checks performed:

- All eight top-level backend Python modules parse successfully.
- VS Code reported no current workspace diagnostics. This is not a successful build or test suite.
- Reproduced state-reference divergence and three malformed-output cases below.
- Confirmed three generated verdict text files are tracked despite ignore patterns.
- No authored automated tests or CI workflows found in the inspected repository; no canonical test command is defined.
- Frontend dependencies are not installed locally, so no frontend build, typecheck, or browser validation was performed. Nothing was installed for this review.
- The selected Python environment reports 3.11.9; the repository's backend version file specifies 3.11.12. This is a reproducibility discrepancy, not a demonstrated compatibility failure.

No performance, pricing, security certification, live model quality, or cloud deployment claim has been validated. No application implementation files were changed.

## 2. What the product actually does

### Current user journey

1. The landing page describes the five-stage architecture and links to intake and recruiter dashboard.
2. Intake takes a candidate name, one of ten fixed role labels, and pasted resume text. It clears browser session storage and calls a global reset before starting.
3. `POST /start` creates a database record, runs resume screening, and either rejects the candidate or generates technical questions.
4. The technical page submits one text answer containing responses to the generated questions. The backend evaluates it and either rejects or generates behavioral questions.
5. The behavioral page similarly submits one text answer. A passing/borderline response marks the in-memory flow complete, although synthesis still needs to run.
6. Loading the result page invokes `GET /final-decision`, which runs recommendation and committee tasks and persists a summary when an evaluation ID is available.
7. The dashboard lists evaluations; its detail page reads persisted verdicts and a stage summary.

### Components and boundaries

| Area | Existing implementation | Important boundary |
|---|---|---|
| Browser application | Next.js App Router, React, TypeScript, Tailwind | Browser storage currently carries flow state; there is no authenticated candidate/recruiter separation. |
| API proxy | [frontend/next.config.js](frontend/next.config.js) | Forwards `/api/*` to `BACKEND_URL`, with a localhost fallback. This is routing, not authorization. |
| API/orchestration | [backend/routes.py](backend/routes.py) | Request handlers invoke agents directly and manipulate global state. |
| Agent definitions | [backend/agents.py](backend/agents.py) | Five personas use the same Gemini model; delegation is disabled and no tools are attached. |
| Prompt definitions | [backend/tasks.py](backend/tasks.py) | Prompt-only shape instructions; seven task constructors, including question generation. |
| Execution/parsing | [backend/crew_runner.py](backend/crew_runner.py) | Runs each Crew in a thread, extracts output, and reads/writes shared files. |
| State | [backend/state.py](backend/state.py) | A single process-global mutable dictionary, not a session store. |
| Persistence | [backend/database.py](backend/database.py) | Parameterized SQL, PostgreSQL pool or SQLite fallback; four tables. |
| Contract declarations | [backend/models.py](backend/models.py) | Pydantic models exist, but verdict models are not used to validate runner output. |
| Operations | [dev.sh](dev.sh), [docker-compose.yml](docker-compose.yml), [frontend/vercel.json](frontend/vercel.json) | Development launcher, optional local Postgres, frontend hosting configuration; no complete backend deployment definition. |

The successful flow has **seven application-level Crew executions**, not five: screening, technical questions, technical evaluation, behavioral questions, behavioral evaluation, recommendation, committee. Each Crew execution may involve more than one underlying provider request; actual token usage and request counts need instrumentation.

This is currently a sequential LLM workflow, not five independently operating services. That is a reasonable starting point. More autonomy is not automatically an improvement.

### Current data model

- `evaluations`: name, raw resume, role, lifecycle status, round, overall score, final decision, timestamps.
- `agent_verdicts`: evaluation foreign key, round/agent identifiers, serialized verdict JSON, raw output, score, decision, confidence.
- `interview_questions`: round-level unstructured question text.
- `interview_answers`: round-level unstructured answer text.

Useful foundations include foreign keys, indexes on evaluation references, parameterized value queries, PostgreSQL pooling, and separate question/answer/verdict records. Missing concepts include identity/organization ownership, stable question IDs, durable jobs, attempt IDs, rubric versions, model configuration provenance, evidence references, reviewer actions, and benchmark datasets.

## 3. Immediate blockers

### B01 — Reset creates two different state objects [reproduced]

[backend/routes.py](backend/routes.py#L23-L28) imports the dictionary directly. [backend/state.py](backend/state.py#L75-L91) rebinds that dictionary inside `reset_state()` rather than mutating the imported object. Routes then write the evaluation ID and questions into the stale reference while `get_state()` reads the new object.

The isolated check captured the imported reference, called the actual reset function with mocked filesystem operations, and wrote ID `123` to the old reference. Results:

- Imported route reference is current state: **false**.
- `get_state()["evaluation_id"]` after that write: **None**.

This is not just a multi-user scaling issue. A normal reset/start path can lose the evaluation linkage used by later persistence and final-decision caching. The permanent fix is evaluation-scoped database state; a temporary reference repair alone is not production readiness.

### B02 — Shared state and verdict files mix unrelated interviews [static]

[backend/state.py](backend/state.py#L75-L86) has one global interview and deletes/recreates the entire verdict directory on reset. [backend/crew_runner.py](backend/crew_runner.py#L71-L86) addresses verdicts by fixed filenames, without an evaluation ID. Concurrent starts or answers can overwrite or consume another interview's state. Additional web workers would have different memory but potentially shared or missing files.

Namespacing files or putting the same global dictionary into Redis does not solve authorization, transaction boundaries, or workflow isolation.

### B03 — Model failures become candidate judgments [reproduced]

[backend/crew_runner.py](backend/crew_runner.py#L89-L164) parses arbitrary JSON, then falls back to keyword search, zero score, and `0.8` confidence.

| Synthetic input | Actual extracted result | Why unacceptable |
|---|---|---|
| `not valid json` | `FAIL`, score `0.0`, confidence `0.8` | The parser's own error text contains “Failed,” which is interpreted as candidate failure. |
| `{}` | `BORDERLINE`, score `0.0`, confidence `0.8` | Missing evidence produces a business verdict rather than an execution error. |
| `{"decision":"APPROVE","score":999}` | `APPROVE`, score `999.0`, confidence `0.8` | Neither decision vocabulary nor numeric bounds are enforced. |

The existing enums and numeric bounds in [backend/models.py](backend/models.py#L15-L109) do not protect this path. Several verdict decision fields are themselves plain strings. Prompts describe a desired shape but do not validate it.

**Required distinction:** invalid model output is `OUTPUT_INVALID` or `REVIEW_REQUIRED`, never a candidate rejection or approval.

### B04 — Public access to sensitive records and paid execution [static]

[backend/routes.py](backend/routes.py) contains no request authentication, ownership checks, or organization scoping. Global reset/start/answer/finalization and historical read endpoints are accessible to any caller who can reach the API.

[backend/database.py](backend/database.py#L289-L312) selects all evaluation columns for list views. [backend/routes.py](backend/routes.py#L429-L459) returns those records, so the list includes raw resume text, even though the dashboard only needs summaries. The detail endpoint also returns the full evaluation. CORS does not prevent non-browser access.

Add identity, object-level authorization, least-privilege response projections, abuse controls, and bounded spending **before public exposure**.

### B05 — Workflow transitions and commits are not protected [static]

Answer handlers check generic `ONGOING` status but not the expected round, question identity, answer version, or authenticated owner: [backend/routes.py](backend/routes.py#L145-L170), [backend/routes.py](backend/routes.py#L225-L250).

Answers, verdicts, and evaluation updates commit separately. There is no submission idempotency key, expected-version check, or uniqueness constraint for the canonical result of an attempt. Repeated or out-of-order requests can produce duplicates or inconsistent history.

[backend/routes.py](backend/routes.py#L300-L392) performs paid work and writes from a GET request. Its intended in-memory cache is vulnerable to the state-reference bug and concurrent requests. Browser cancellation does not imply provider execution stopped.

### B06 — Long-running work is tied to HTTP lifetime [static]

[backend/crew_runner.py](backend/crew_runner.py#L20-L46) retries selected exception strings with waits of **60 and 120 seconds** before exhausting three attempts. Those 180 seconds of waiting are additional to provider execution time. Sleep occurs in the worker thread, not directly on the event loop, but still occupies execution capacity. There is no application-level total deadline, durable queue, backpressure, or recovery ledger.

Synchronous database functions are invoked directly from async routes and can block the event loop during database I/O. A thread-safe pool is not an async driver and its size has not been load-tested.

## 4. Agent quality and audit weaknesses

### Q01 — The committee is not independent verification

All agents use [the same model configuration](backend/agents.py#L10-L13). Later agents see earlier judgments and the committee sees the recommendation. This can amplify correlated errors and anchoring. Removing direct resume access does not remove identity details or bias propagated through summaries.

The committee can check consistency of peer outputs, but cannot verify all claims against original evidence it never receives. Keep context minimization, add redacted evidence references, and test whether a committee improves quality against simpler baselines.

### Q02 — No agreed scoring contract

Role selection is a fixed string list in [backend/state.py](backend/state.py#L24-L35), not a versioned job-specific rubric. Technical evaluation has no trusted executable reference checks. Behavioral prompts assign a `culture_fit` score from minimal text: [backend/tasks.py](backend/tasks.py#L254-L266).

Replace vague suitability/personality inference with job-relevant observable competencies and explicit “insufficient evidence.” A resume claim is not a verified employment fact. A STAR response is not proof of a stable personality trait.

### Q03 — Confidence is not calibrated

The prompts **do request** confidence. The issue is that the values are self-reported, defaults can invent missing values, and no calibration dataset or calibration procedure exists. They are not measured probabilities of correctness.

The [landing page](frontend/app/page.tsx#L50-L70) claims calibrated confidence, sub-two-minute processing, full auditability, and validated Pydantic output without supporting measurement/enforcement in this repository.

### Q04 — Overall scoring double-counts synthesis

[backend/routes.py](backend/routes.py#L364-L367) averages all stored non-null scores, including the recommendation score that already summarizes earlier rounds. Duplicate verdicts can further alter weighting. There is no versioned aggregation policy or handling of uncertainty/missing evidence.

### Q05 — No system evaluation harness

Candidate scores are application output, **not tests of the evaluator**. The repository has no benchmark cases, human labeling protocol, independent grader validation, prompt/model version comparisons, failure taxonomy, or release-quality gates.

### Q06 — Prompt injection and evidence laundering

[backend/tasks.py](backend/tasks.py) interpolates resumes, answers, and prior model outputs directly into task descriptions. All are untrusted input. A later agent may treat an earlier model's unsupported claim as evidence. No successful attack was demonstrated in this review; the missing trust boundaries require adversarial testing.

### Q07 — Logs and records are not an immutable audit system

Verbose agent/Crew output can expose sensitive content depending on library behavior. The API's exception handler returns internal exception messages: [backend/main.py](backend/main.py#L94-L111). There is no end-to-end trace ID, model/prompt/rubric provenance, privileged-read audit, or artifact integrity control.

The README calls decision memory immutable, but verdict files are overwritten and globally deleted on reset. Existing database tables alone do not provide tamper evidence or retention governance.

## 5. Frontend, efficiency, and operations

| Finding | Source | Planned correction |
|---|---|---|
| Intake clears all session storage on mount and submission; answers contain no evaluation/question ID | [intake](frontend/app/interview/page.tsx#L39-L65), [round submission](frontend/app/round/[id]/page.tsx#L46-L67) | Server-owned flow, evaluation-scoped URLs, draft recovery, narrowly scoped local cache. |
| Round component resets neither answer nor draft explicitly on round change | [round page](frontend/app/round/[id]/page.tsx#L35-L53) | Key state by round/question; browser test whether route reuse currently carries old answers. |
| Fetches have no explicit abort/deadline; dashboard failures can look like an empty list | [dashboard](frontend/app/dashboard/page.tsx#L55-L79) | Typed client, safe read retries, idempotent mutation retries, distinct error/empty states. |
| Dashboard filters only fetched records; API defaults to 50 and UI has no pagination | [dashboard filtering](frontend/app/dashboard/page.tsx#L77-L80), [API pagination](backend/routes.py#L429-L459) | Server-side filters/search/pagination with stable ordering and an explicit stats scope. |
| Early rejection still appears under a committee decision heading | [result page](frontend/app/result/page.tsx) | Show actual originating stage and human-review status. |
| API shapes use `any`; verdict cards and schemas are duplicated | [result](frontend/app/result/page.tsx), [report](frontend/app/dashboard/[id]/page.tsx), [models](backend/models.py), [tasks](backend/tasks.py) | Generated contracts, runtime validation, shared evidence/scorecard components. |
| Clickable divs and labels without explicit input association | [result card](frontend/app/result/page.tsx#L40-L44), [intake form](frontend/app/interview/page.tsx) | Semantic buttons/links, input IDs, keyboard/focus handling, live status announcements. |
| Fullscreen helpers are not imported by active pages; activation flag is never set | [fullscreen hook](frontend/app/hooks/useFullscreen.ts), [warning component](frontend/app/components/FullscreenWarning.tsx) | Remove/defer rather than treat as a security control. No active voice/camera flow was found. |
| Google fonts are requested through both CSS and Next font loading | [styles](frontend/app/globals.css#L1), [layout](frontend/app/layout.tsx#L3-L17) | One font-loading strategy; measure loading and avoid redundant third-party requests. |
| One verdict query per listed evaluation, loading full JSON/raw outputs | [list handler](backend/routes.py#L439-L451) | Batched summary projection; list query count currently grows as N + 2. |
| Configuration is read at import, before the explicit dotenv call in the entrypoint | [database config](backend/database.py#L23-L29), [entrypoint import order](backend/main.py#L33-L37) | Load/validate settings before dependent imports. Actual behavior may depend on third-party import side effects; test the documented startup path. |
| Dependency ranges, no Python lock, no complete backend deployment/CI | [requirements](backend/requirements.txt), [frontend manifest](frontend/package.json), [local Postgres](docker-compose.yml) | Reproducible runtime/lock strategy; tested deployment, migrations, probes, CI. No specific CVE is asserted. |
| Three generated verdict files remain tracked | [ignore rules](.gitignore#L20-L26) | Review consent/data classification; later remove generated artifacts from tracking. Ignore patterns do not untrack existing files. |
| Launcher assumes POSIX virtualenv paths and reinstalls Python requirements | [dev.sh](dev.sh#L44-L56) | Document/test Windows setup and reproducible installs, track child PIDs precisely. |
| Neon configuration is empty; backend connects through ordinary SQL | [neon.ts](neon.ts), [database](backend/database.py) | Do not assume Neon auth/functions/storage are configured or deployed. |

## 6. Preserve these strengths

- A complete conceptual user journey and a coherent visual identity.
- Existing historical reports and structured verdict concepts.
- Modular separation of prompts, execution, API, schema declarations, and persistence.
- Explicit context assembly, a useful starting point for least-privilege evidence access.
- Parameterized SQL and PostgreSQL support, avoiding a forced database rewrite.
- A small enough codebase to make meaningful improvements without a microservice rebuild.

**Conclusion:** a useful prototype, but not yet a safe multi-user production hiring system. The most compelling next step is to make failures visible and testable, replace shared state, and demonstrate trustworthy evaluation of the agent itself. See [PRODUCTION_ROADMAP.md](PRODUCTION_ROADMAP.md).