# AI-conducted interview: research-grounded architecture and delivery plan

**Prepared:** 2026-10-01
**Status:** Proposed architecture; not implemented or production-approved
**Scope:** An end-to-end, application-linked AI interview and recruiter report for a specific organization, campaign, posting, and candidate application.

This is a feature plan grounded in the current repository and the sources listed below. It is not legal advice, a vendor selection, or a claim that the proposed interview has been validated. No code changes are implied by this plan.

## 1. Recommendation in brief

Build this as a **bounded interview domain inside the existing Next.js + FastAPI application**, not as a second, disconnected evaluation product or a collection of new microservices.

1. **Use the application as the ownership and authorization root.** The server derives organization and posting from the application, then campaign from the posting. The candidate must never choose those associations by supplying IDs to the interview client.
2. **Automate the positive path from application submission.** Require a complete candidate profile first (resume upload → editable extraction → save, or a structured manual profile). When an application is committed, automatically queue screening. A passing applicant automatically receives an AI-interview invitation/session; the recruiter does not click “screen,” “invite,” or schedule each candidate. The candidate still chooses when to start and explicitly accepts the disclosed interview mode.
3. **Make live voice the intended interview experience, with an equivalent text path.** Start with a provider feasibility spike and a mocked/text end-to-end flow; enable real microphone streaming only after privacy, consent, latency, accessibility, and recovery gates pass. Camera/video is off by default and not scored.
4. **Use deterministic orchestration around constrained AI roles.** One application pipeline controller owns screening admission, allowed transitions, interview phases, timing, retries, and completion. A conversational interviewer asks bounded, level-aware follow-ups; separate scoring/report steps cite answer evidence. Model output cannot directly change application stage or make a hiring decision.
5. **Pin screening and each interview to versioned posting policies.** Keep hard constraints, level/difficulty map, question plan, competency weights, and scoring anchors immutable for that application run. Generate the report from those snapshots, not from whatever criteria happen to be current when the report is opened.
6. **Show progress and the report in the existing application detail surface.** Candidates see profile-required, screening-queued, interview-ready, and report-pending states. Recruiters see the pipeline history, job-specific evidence, uncertainty/transcription caveats, and exception/review actions; they retain the final advance/hold/reject decision.
7. **Do not use the supplied paper’s headline numbers as product targets.** It is useful for workflow ideas, but its reported outcomes are not sufficiently documented in the supplied copy to establish effect sizes or fairness.

**Roadmap relationship:** This is an addendum to [PRODUCTION_ROADMAP.md](../PRODUCTION_ROADMAP.md), not a replacement for its durable-state, evaluation-harness, privacy, and controlled-pilot gates. That roadmap currently treats voice as a later extension to the generic interview flow; this plan defines an application-submit-triggered screening → AI-interview-ready flow as the end state, while validating the queue/session/report contracts with mocked/text paths before enabling live voice for candidates.

## 2. Product objective and boundaries

### Objective

For a candidate with a ready profile who applies to an enabled posting, provide an automatic screening-to-interview journey that:

- Starts from the candidate’s own application to one published role/posting. The candidate can upload a resume for parsing into editable professional details and save it, or manually create the structured profile; application readiness is validated before submission.
- On application submission, automatically queues the posting’s versioned screening policy without a recruiter action. A clear pass automatically creates an interview-ready session/invitation and notifies the candidate; a recruiter does not trigger screening, invite, or schedule each person individually.
- Transparently identifies the interviewer as AI, explains the interview format and data handling, and supports accommodations and a text alternative.
- Conducts one coherent role-relevant interview from introduction to close, with technical and behavioral phases defined by the posting’s competency plan.
- Starts at the job’s declared level (for example, entry, mid, or senior) and may move one bounded difficulty band at a time based on evidence in the candidate’s preceding answer. Core competencies remain covered for every candidate; difficulty path and question IDs are recorded for fair scoring.
- Uses natural turn-taking and bounded follow-ups to clarify evidence, repeat or rephrase a question when needed, and recover from temporary connection loss.
- Produces a recruiter-facing report tied to that exact application and the rubric version used, with evidence references to transcript turns.

### Profile readiness and application contract

- Complete profile setup before applying. Resume upload is the fast path: extract likely headline, summary, skills, work experience, and education; show an editable review; save only after candidate confirmation. The alternative is a structured manual profile with equivalent relevant fields.
- Profile readiness means required job-relevant information is present and valid, not that the candidate owns a particular file format or has a specific degree. A posting may require objective evidence (for example, a certification or work-authorization answer) only when it is explicitly configured and disclosed.
- At application submission, freeze the profile snapshot and application answers for that posting. Later profile edits do not change an assessment already underway.
- A posting must have an approved, versioned automated-screening/interview policy before this automatic path is enabled. Recruiters configure it once per posting, not once per applicant. A posting without it must follow an explicitly selected alternative process rather than silently leaving applications unprocessed.
- Publishing or materially updating a job creates a new immutable policy/rubric revision. Applications submitted after that publication pin the new revision; applications already submitted keep their original revision and are not silently re-screened or re-scored. Any exceptional migration/re-screen of in-flight applications must be explicit, authorized, audited, and governed by candidate notice and applicable policy.

### Explicit non-goals for the first release

- Autonomous final hire/no-hire or rejection decisions, and unrestricted application-stage transitions. A deterministic, published policy may advance a clear pass from screening to AI-interview-ready; a model cannot directly mutate stage.
- Scoring emotion, honesty, personality, enthusiasm, confidence, “culture fit,” accent, speaking rate, facial expression, or appearance.
- Mandatory webcam use, covert recording, or proctoring.
- Scraping LinkedIn, GitHub, or other external profiles to enrich candidates.
- General-purpose autonomous agents with unrestricted tools, or agent-to-agent debate used as a substitute for evaluation.
- Replacing the existing candidate application, recruiter campaign, scheduling, or generic sandbox products.
- Running candidate-submitted code on the API server. A secure work-sample environment is a later, separately assessed feature.

## 3. What exists today and the integration gap

| Existing capability | Current behavior and implication for this feature |
|---|---|
| Profile and application submission | The application endpoint requires a profile row and required posting answers, but does not currently validate resume/profile completeness. It snapshots profile data and creates the application; it does not enqueue a screening job. The active profile UI already supports resume parsing, editable review, and explicit save, but manual structured profile completion and an apply-readiness gate need to be made equivalent. See [profile UI](../frontend/app/profile/page.tsx), [hiring schema](../backend/app/config/hiring_schema.py), and [candidate application routes](../backend/app/candidate/controller.py). |
| Resume screening | Screening is currently a separate recruiter-triggered `POST .../applications/{id}/screen` action. It runs in the request path, attaches an evaluation, and does not conduct the technical/behavioral interview end to end. The implementation uses resume/profile snapshot plus posting title; it does not yet run the requested versioned hard-constraint and application-answer screening policy. See [hiring controller](../backend/app/hiring/controller.py). |
| Generic AI evaluation | A separate five-stage evaluation pipeline supports screening, technical, behavioral, recommendation, and committee work. Its generic start payload is resume + role + candidate name, not a fully authorized application interview. The candidate UI for that pipeline is text-oriented. See [evaluation routes](../backend/app/evaluation/controller_v1.py), [evaluation DTOs](../backend/app/evaluation/dto.py), and [candidate interview UI](../frontend/app/interview/page.tsx). |
| Scheduled interviews | The hiring domain stores recruiter-scheduled interviews, participants, timezone, and optional meeting URL. That is a calendar record, not an AI media session. The automated AI path must not require a recruiter to create a schedule for each passing applicant; create an interview-ready invitation/window automatically and link to a calendar record only when a customer explicitly wants one. See [hiring schema](../backend/app/config/hiring_schema.py) and [interview routes](../backend/app/hiring/controller.py). |
| Posting criteria and report | Criteria are stored per posting. The current report is one-per-application and scores competencies through heuristic round-name/keyword matching. That is a useful display surface, not a sufficient transcript-grounded scoring engine. The report model will need interview-session history and evidence links. See [criteria schema](../backend/app/config/interview_criteria_schema.py), [report service](../backend/app/interview_criteria/service.py), and [recruiter posting UI](../frontend/app/org/postings/[id]/page.tsx). |
| Durable execution | The backend has an additive durable `/v1` evaluation API and a database-backed worker/job pattern, but the current application-submit path does not admit screening work and the recruiter screening action runs synchronously. Use durable jobs for automatic screening, notification, and post-interview scoring/reporting; commit application and screening/outbox admission atomically. See [worker](../backend/app/worker/job_worker.py), [candidate application routes](../backend/app/candidate/controller.py), and [durable evaluation controller](../backend/app/evaluation/controller_v1.py). |
| Auth and campaign scope | Authentication, organization capabilities, application authorization, and campaign-assignment checks already exist. Every new candidate and recruiter operation must use those server-side checks; frontend visibility alone is not access control. See [authz](../backend/app/shared/authz.py) and the [application report controller](../backend/app/interview_criteria/controller.py). |
| Voice/media | No microphone capture, voice-interview transport, speech transcription, or interview-media retention workflow was found in the active candidate interview path. This is a net-new capability and requires a provider/privacy decision. The existing local OpenAI-compatible model configuration is not, by itself, a production real-time voice architecture. |

### Main design gaps to close

- The candidate apply endpoint creates the application but no screening job. The current per-application recruiter screen endpoint is the manual trigger; replace that as the normal flow with atomic application + screening-job admission.
- Apply currently checks that a profile exists, not that it has the job-relevant details needed by screening. Add a readiness gate backed by either reviewed resume extraction or structured manual profile entry.
- The current screening call does not evaluate a versioned set of posting constraints/application answers and runs synchronously. The automated flow needs explicit deterministic eligibility rules, evidence-bearing model assessment, durable retries, and safe exception states.
- A passing screen currently does not automatically create an interview-ready invitation/session. Add the pass → ready event, candidate notification, and candidate-controlled start without a recruiter action per applicant.
- `applications.evaluation_id` is a single nullable pointer, while interviews need multiple attempts, restarts, and report history. Do not use that field as the new feature’s only session identity.
- The current `application_interview_reports` key permits one report per application. Model report/session history explicitly, and preserve the existing application-level report endpoint as a compatibility summary if feasible.
- Current posting criteria can be updated in place. An in-progress or completed interview must retain the exact question/rubric snapshot it used.
- The current heuristic report does not prove that a candidate answer supports a competency score. Add structured, answer-linked evidence and abstention/insufficient-evidence handling.
- Voice connection lifecycle, candidate consent/notice, transcript correction, accessibility, retention/deletion, and provider failure recovery need first-class contracts and tests.

## 4. Research findings and how they affect the design

### Supplied SSRN paper

The supplied PDF is titled **“AI Agents in Recruitment: A Multi-Agent System for Interview, Evaluation, and Candidate Scoring”** by Gangesh Pathak and Divya Pandey. The copy describes an asynchronous, chat-based workflow with modular sourcing, vetting, evaluation, and decision roles. It reports a three-month deployment with engineering candidates in India and Latin America (PDF pp. 13–14), including **65% faster time-to-hire**, **91% alignment with human reviewers**, and **4.6/5 candidate experience**; it also reports lower AI-versus-human performance for soft-skill evaluation (**67% vs. 85%**, PDF pp. 18–19).

**Evidence caveat:** The supplied copy reports **more than 500 candidates** during the three-month deployment, but does not give an exact cohort count or composition, the number who completed each measure, the survey-response count, a reproducible baseline definition, confidence intervals, a detailed measurement protocol, or an independently described fairness audit. The PDF also contains an apparent stray editorial instruction on p. 13. Its claims are therefore treated here as the paper’s reported results—not independently validated benchmarks. Its modular workflow, rubric, logging, and recruiter-review ideas are useful hypotheses. Its reported percentage improvements, “bias reduction” statements, and tool choices are not adopted as evidence that this product will achieve similar outcomes. The paper describes asynchronous chat; it does not establish that live voice interviewing is reliable or fair.

| Source | Evidence relevant to this feature | Architectural consequence |
|---|---|---|
| OPM, [Structured Interviews](https://www.opm.gov/policy-data-oversight/assessment-and-selection/structured-interviews/) | OPM describes asking candidates the same predetermined questions in the same order and evaluating responses with the same rating scale/standards. | Freeze core questions and anchored rubric per posting version. Permit only bounded, job-related clarification probes with explicit triggers; measure whether adaptive probes change comparability. |
| NIST, [AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) | A voluntary risk-management framework organized around Govern, Map, Measure, and Manage; NIST also publishes a Generative AI Profile. | Assign a product/risk owner, map the interview’s intended use and affected people, measure model/speech performance and failures, and set monitoring/response plans before a hiring pilot. This is a governance framework, not a certification. |
| EEOC, [ADA and software/algorithms/AI in applicant assessment](https://www.eeoc.gov/laws/guidance/americans-disabilities-act-and-use-software-algorithms-and-artificial-intelligence-assess-job-applicants-and-employees) | The EEOC resource addresses disability-related screening risks and reasonable accommodation in technology-mediated applicant assessment. | Offer an equivalent text/human accommodation path, do not penalize speech-recognition or device failures, and obtain qualified review of assessment design and notices. |
| NYC DCWP, [Automated Employment Decision Tools](https://www.nyc.gov/site/dca/about/automated-employment-decision-tools.page) | For tools and employers covered by Local Law 144, requirements include a bias audit, public audit information, and candidate/employee notices; scope is fact-specific. | Add a jurisdictional applicability gate. A dashboard’s informal selection-rate metric is not a substitute for any required independent audit or notice. |
| European Union, [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng) | Annex III, point 4 includes certain AI uses for recruitment and selection among high-risk use cases. Whether a particular system and use are in scope requires legal analysis. | Do not assume “human in the loop” alone resolves obligations. Keep technical documentation, version provenance, risk controls, and human review in the plan; confirm applicable duties and dates with counsel for intended markets. |
| MDN, [WebRTC API](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API) and [`getUserMedia()`](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) | Browser media access requires user permission; `getUserMedia()` is restricted to secure contexts, and WebRTC supports real-time media/data connections. | Use HTTPS, explicit device preflight, clear microphone state, permission-denied handling, text fallback, and a scoped real-time media connection. Do not expose durable provider credentials in the browser. |
| FastAPI, [Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) | FastAPI positions in-process background tasks for work that can happen after a response and recommends larger task systems for heavy work distributed across processes/servers. | Use the existing durable job/worker design for final scoring/report delivery, retries, and recovery; keep the live conversation stream separate from report processing. |
| Pathak & Pandey, [SSRN manuscript, DOI 10.2139/ssrn.5242372](https://doi.org/10.2139/ssrn.5242372) and the user-supplied PDF | Useful design themes: modular agent roles, rubrics, a recruiter-visible report, operational logs. Quantitative results and fairness claims lack enough disclosed method in the supplied copy for independent reliance. | Borrow modular boundaries as a design option, not an autonomous agent swarm or performance guarantee. Build our own role-specific pilot and evaluation set before making product claims. |
| Dishant1804, [multi-agent-interviewer](https://github.com/Dishant1804/multi-agent-interviewer) | The README and inspected [interview system](https://github.com/Dishant1804/multi-agent-interviewer/blob/master/interview_system.py) / [agent implementations](https://github.com/Dishant1804/multi-agent-interviewer/tree/master/agents) separate interviewer, topic manager, evaluator, and orchestrator; they illustrate one-question-at-a-time turns, adaptive topic/depth, and per-turn feedback. The implementation uses LangChain `ChatOpenAI` prompt chains and an in-memory `InterviewContext`; the session wrapper reads resume/job-description file paths. `EvaluatorAgent` regex-parses prose and falls back to score 5 on parsing/evaluation errors. LangGraph appears in dependencies, but the inspected orchestrator directly calls Python objects; the reviewed path does not show a LangGraph graph driving the flow. | Reuse the *separation of responsibilities* and the idea of bounded topic/depth progression. Do not port its in-memory session, CLI/file-path boundary, free-form parsing/default score, or fully model-chosen topic/level into a multi-tenant hiring workflow. Keep policy/state deterministic and use typed, evidence-cited results. This is a useful prototype reference, not production-readiness or quality evidence. |

## 5. Target architecture and boundaries

Keep the current deployment shape initially: Next.js web app, FastAPI modular backend, existing relational database, and existing worker. Add a clear interview-session module and typed contracts. Split into independently deployed services only if measured traffic, provider constraints, or operations require it.

### Components

1. **Recruiter posting policy UI (one-time per posting/revision)** — Extend the posting criteria/settings surface. Configure eligibility constraints, required profile fields, job family and target level, competencies, difficulty bands, core question plan, follow-up limits, scoring anchors, interview window, modality/fallback, and automation behavior. Publishing the posting pins a version. Recruiters do not start screening or invite/schedule individual applicants.
2. **Candidate profile and application UI** — Make profile completion a prerequisite to applying. Offer resume parse → editable review → explicit save, plus a structured manual profile path. Display which job-relevant required details are missing; application answers can fill only configured posting-specific gaps.
3. **Application submit and pipeline dispatcher** — On `POST /jobs/{posting_id}/apply`, atomically persist the application, immutable profile/answer snapshot, application event, and an idempotent screening/outbox job. Return a screening-queued status immediately; never wait for model screening in the HTTP request.
4. **Automatic screening worker** — Load the frozen application/posting snapshots. Run explicit deterministic knockout/eligibility rules on structured fields first, then a constrained resume/application evidence assessor against the published screening policy. Persist result and provenance. A validated pass automatically changes the pipeline state to interview-ready and creates a session invitation plus notification job. Borderline, missing evidence, provider failure, or model disagreement becomes an exception/review state; it does not silently reject the candidate.
5. **Candidate pipeline and interview UI** — The candidate tracker shows `SCREENING_QUEUED`, `SCREENING_IN_PROGRESS`, `AI_INTERVIEW_READY`, `AI_INTERVIEW_IN_PROGRESS`, and `REPORT_PENDING/REVIEW` progress. On pass, the candidate receives an in-app/email invitation and a configurable window; they choose when to start and accept the disclosed modality. This is not a recruiter-per-applicant scheduling action.
6. **FastAPI pipeline/session API** — Authenticates the actor, resolves application → posting → campaign → organization from the database, validates every transition, and never trusts client-supplied associations. Candidate start is allowed only for the ready session owned by that candidate; recruiter report access remains capability/campaign-scoped.
7. **Interview session service/state machine** — Owns an attempt, immutable policy/rubric snapshot, consent record, interview phase, turn order, difficulty band, allowed question IDs, idempotency, time limits, resume/reconnect behavior, and completion. It is deterministic application code, not an LLM.
8. **Conversation and provider adapters** — A provider-neutral interface for real-time media, transcription, and model/TTS events. Compare an integrated real-time provider with composed speech-to-text + LLM + text-to-speech. Select only after testing latency, barge-in, transcript quality, regional/data terms, retention, reliability, and cost. Browser credentials are session-scoped and short-lived; otherwise media is relayed through a controlled gateway.
9. **Bounded interview and assessment agents** — The interviewer asks the next approved technical/behavioral question or a permitted level-aware follow-up. The assessor returns typed evidence and rubric-level assessments. Neither agent can query arbitrary external sources, modify records, select/reject candidates, or change stage. Server-side code validates question IDs, level transitions, competency coverage, and turn limits.
10. **Scoring/report pipeline and worker** — After completion, a durable job evaluates each competency against the exact rubric/difficulty snapshot, validates cited transcript evidence, computes any displayed weighted values deterministically, and stores report history. Invalid output, missing evidence, low transcription quality, or provider failure becomes `REVIEW_REQUIRED`/`INSUFFICIENT_EVIDENCE`, never a candidate failure.
11. **Persistence and audit** — PostgreSQL remains production source of truth; preserve SQLite parity for tests. Persist screening attempts/policy versions, application pipeline events, session state, turns/transcript, provenance, evidence references, consent/notice version, and reviewer actions. Do not use local files or browser storage as authoritative state.
12. **Recruiter report surface** — Show the full pipeline and report under the exact posting/application. Recruiters can review, correct, request a repeat, or make the final stage decision. Application-read, organization, and campaign-assignment policy applies to reports, transcripts, and history.

### Automated screening and pass-to-interview contract

- A published posting policy distinguishes **hard eligibility rules** from **scored job qualifications**. Hard rules use explicit structured inputs (for example, an applicant’s answer to a disclosed required-authorization question); do not infer knockout facts from free-form text when the evidence is missing.
- The screening assessor returns a strict structured result: per-constraint outcome, competency/evidence matches with references to profile or application fields, coverage/uncertainty, policy version, and one of `PASS`, `REVIEW_REQUIRED`, or a configured non-eligible state. Invalid output is an execution error, never a fail score.
- The application pipeline service—not the LLM—checks that every required constraint passed and that the versioned screening rule is satisfied. Only then does it move the application to `AI_INTERVIEW`, create a `READY` session, and notify the candidate.
- All valid applications on an enabled posting enter the same automatic screening path. There is no recruiter click to start screening or invite a clear-pass candidate. Borderline results, missing facts, invalid model responses, and worker/provider failures are visible exceptions; they do not automatically reject.
- Preserve a distinct audit event and candidate-visible status for each stage. A candidate may update their profile before applying; once submitted, later edits do not rewrite the frozen assessment snapshot.

### Component flow

```text
Candidate profile/apply UI

  └─ HTTPS ─> FastAPI apply endpoint
       └─ one DB transaction: application + immutable snapshot + screening job/outbox
            └─ screening worker ─> objective rules + constrained resume/application assessor
                 ├─ PASS ─> create AI-interview-ready session + candidate notification
                 └─ REVIEW_REQUIRED / configured hard-constraint exception ─> recruiter exception queue

Candidate tracker ─> candidate starts ready session after disclosure/consent
  ├─ HTTPS control plane ─> FastAPI session API ─> session state / turns / rubric ─> PostgreSQL
  └─ permissioned voice ─> provider adapter <─> bounded interviewer
       └─ validated turns/events ─> session service
            └─ completion job ─> report worker ─> evidence report

Recruiter posting dashboard <── scoped progress/report API <── application, policy, report and reviewer events
```

The media path is separate from application authorization and report reads. Screening and report jobs run outside the request path; the candidate chooses when to start the automatically prepared interview. Exact transport/provider selection is a Phase 0 decision; the browser never receives a long-lived service secret.

### Conceptual request/data paths

- **Application pipeline:** Candidate profile/apply page → authenticated submit → atomic application + screening admission → durable screening worker → automatic ready invitation on pass, or an exception state.
- **Control plane:** Candidate or recruiter Next.js page → authenticated HTTPS API → application authorization + pipeline/session services → database.
- **Live media plane:** Candidate browser microphone → permissioned real-time transport/provider adapter → constrained conversation flow. Session control, consent, and persistence remain application-owned. Do not send persistent API secrets to the browser.
- **Completion plane:** Session completion → durable scoring/report job → schema/evidence validation → report/history persistence → recruiter application detail UI.
- **Fallback plane:** Permission denied, unsupported browser, accommodation request, low-confidence transcription, or provider outage → text-based interview or human rescheduling/review; infrastructure failure must not become a negative score.

### Agent roles are responsibilities, not autonomous services

| Role | Responsibility | Forbidden behavior |
|---|---|---|
| Application pipeline controller | Consume the application-submitted event, enforce the published policy version, queue screening, create the interview-ready session after a validated pass, and move exceptions to review. | Letting a model call write application state, or requiring a recruiter to click screen/invite for each application. |
| Eligibility gate | Apply explicitly configured, deterministic hard constraints to structured profile/application fields; report missing/ambiguous data distinctly. | Guessing missing candidate facts or deriving knockout rules from free-form model output. |
| Resume/application assessor | Compare candidate-provided evidence and application answers with the posting rubric; return typed evidence references and `PASS`/`REVIEW_REQUIRED`/configured non-eligible recommendation. | Treating model confidence as calibrated, inventing evidence, or independently rejecting a candidate. |
| Session controller | Deterministic interview state, phase/level coverage, allowed difficulty changes, time/turn limits, idempotency, handoff/recovery. | Asking a model to decide authorization, application identity, or an unbounded transition. |
| Question planner | Map the approved posting rubric, target job level, and difficulty bank to the frozen core question plan before the session. | Adding unapproved competencies, protected-trait questions, or external candidate data. |
| Conversational interviewer | Present questions naturally, acknowledge answers, ask allowed clarifying follow-ups, and explain repeats/pauses. | Pretending to be human, diagnosing personality/emotion, making employment decisions, or changing application stage. |
| Competency assessor | Produce a typed assessment for each rubric dimension with exact transcript-turn evidence and an insufficiency state. | Score voice/appearance proxies, cite evidence not present in the transcript, or treat a transcript error as candidate incompetence. |
| Report formatter | Render validated assessments, evidence, caveats, and deterministic aggregation for recruiter review. | Inventing evidence, silently changing the rubric, or turning an advisory threshold into an automatic reject. |

The application remains responsible for authorization, state transitions, persistence, eligibility rules, notification, scoring arithmetic, and recruiter actions. A “multi-agent” label is not a quality or fairness guarantee; compare the constrained design against simpler baselines in evaluation.

### CrewAI decision and runtime boundary

**Recommendation: reuse CrewAI selectively, but do not put the live interview loop inside a Crew.** The current Evalia backend already defines five CrewAI agents in [evaluation/agents.py](../backend/app/evaluation/agents.py) and constructs a `Crew` and calls `crew.kickoff()` from [evaluation/runner.py](../backend/app/evaluation/runner.py). The runner wraps that synchronous call in a thread and applies Pydantic output validation/retries. The generic `/v1` evaluation path has durable worker admission, but the current recruiter application-screen endpoint still awaits screening in its HTTP request; the automatic application-triggered path in this plan must move screening to a durable job.

- **Automatic resume/application screening:** initially reuse the existing CrewAI screening adapter from a durable screening worker, refactoring its prompt/DTO to consume the pinned posting policy and frozen application evidence. Deterministic eligibility constraints, application state, pass/exception routing, retries, and notifications stay in ordinary application services—not in the Crew or LLM.
- **Live interviewer:** do not instantiate a multi-agent Crew for every spoken turn. The session controller owns the durable turn/question/level state; a provider adapter handles low-latency streamed voice/text; one bounded interviewer call proposes the next allowed question or clarification, and server code validates it. CrewAI does not provide the browser media transport, consent lifecycle, application authorization, or persistence boundary this feature needs.
- **Final scoring/report:** run after session submission as a durable worker job. Start with one constrained scorer/structured output call; reuse CrewAI here only if a comparison against a direct provider-adapter call shows it improves rubric evidence quality or maintainability without violating the agreed latency/cost budget. Do not add recommendation-plus-committee agents merely to increase agent count.
- **No framework sprawl:** do not add LangGraph just because the linked repository lists it. The linked sample is a useful example of role separation and adaptive turn flow, but its inspected implementation calls agent objects directly and keeps state in memory. Evalia should keep one deterministic application/session state machine and one provider interface; CrewAI is an implementation detail behind offline task adapters, not the owner of workflow state.

Before committing any scorer/provider wiring, test a narrow vertical slice with mocked providers and a measured, approved live-provider experiment: structured-output validity, evidence reference correctness, p50/p95 turn latency, reconnect behavior, token/audio cost per session, and scenario-level human review. No numeric target is inferred from the GitHub sample.

### Natural, human-centered interaction without deception

- Use one consistent interviewer persona and a warm, professional voice; disclose plainly that it is an AI interviewer before the session starts.
- Speak one concise question at a time. Let the candidate finish, tolerate a deliberate thinking pause, and avoid interrupting except when the candidate requests it or the connection needs recovery.
- Acknowledge the content briefly and specifically, then ask a relevant follow-up only when the rubric indicates an evidence gap. Avoid generic praise, simulated emotional intimacy, or pretending the system has human feelings or judgment.
- Offer repeat, rephrase, pause, skip/flag, and “I need a moment” controls. If speech recognition is uncertain, confirm or repeat the transcript rather than interpreting the uncertainty as a weak answer.
- Close clearly: summarize that the interview is submitted, explain what happens next, and do not promise a hiring outcome or reveal a score as if it were final.
- Keep the same core question plan, interviewer behavior, and follow-up limits for candidates using the same posting/rubric version. Any adaptation beyond clarification must be explicitly approved and evaluated for comparability.

### Leveling and adaptive follow-up contract

- The recruiter chooses the **target level of the job** when publishing the posting (for example, entry, mid, or senior); the system does not infer the level from protected characteristics or silently re-level the job from a candidate’s demographic/profile proxy.
- Each posting policy maps competencies to a fixed core question and tagged difficulty bands. Use the same core baseline and competency coverage for every candidate applying under that policy version.
- After an answer, a constrained assessor may return structured evidence coverage and one permitted next-question/level recommendation. The deterministic controller validates it against the posting’s branch table: clarify missing evidence, remain at target level, or move by at most one band. The model cannot invent an unapproved question or jump difficulty arbitrarily.
- Technical questions can increase depth (for example, from correct implementation to trade-offs, scale, reliability, or debugging); behavioral questions can probe the same job-related behavior at increasing scope (individual task, team collaboration, cross-team/ambiguous ownership). Do not score personality or presumed “culture fit.”
- Store question ID, competency, item level, branch rule, and reason alongside each turn. Score the answer against the anchors for the question actually asked. Do not compare raw totals across adaptive paths until a reviewed calibration study shows that the alternate paths are comparable; otherwise show the item-level evidence and mark cross-path totals advisory.

## 6. End-to-end workflow

1. **Complete candidate profile before apply.** Candidate registers and either uploads a resume for extraction, edits the suggested professional profile, and saves it, or enters the equivalent structured profile manually. The apply page shows profile readiness and asks only for missing job-specific screening answers. The server enforces the same readiness requirements.
2. **Configure/version the posting once.** An authorized recruiter sets the posting’s screening constraints, required evidence, rubric/competencies, role family and target level, interview difficulty bands, question plan, follow-up policy, interview window, candidate notice, and review exceptions. Publishing validates and freezes a policy version. An updated job creates a new revision for new applicants; existing applications remain pinned to the revision active when they applied unless an explicit audited migration is approved. No per-applicant screen/invite/scheduling clicks are part of the normal flow.
3. **Submit application and atomically admit screening.** `POST /jobs/{posting_id}/apply` validates posting/profile/required answers, freezes the candidate profile and answers, creates the application and application event, and writes an idempotent screening/outbox job in the same transaction. It returns immediately with a queued status; the candidate tracker shows screening in progress. If the transaction fails, neither a half-created application nor an orphaned screening request remains.
4. **Screen automatically.** A durable worker loads only that application’s snapshot and the pinned posting policy. First run deterministic checks over explicitly structured, disclosed hard constraints. Then use a constrained assessor to map resume/profile/application evidence to job criteria, citing the source fields or answer evidence. Passing requires both eligible hard constraints and the configured rubric pass rule. Missing/ambiguous evidence, invalid model output, or provider failure becomes `REVIEW_REQUIRED`, not a candidate failure. Any objective knockout rule must be explicit, lawful, versioned, and communicated; model-only adverse recommendations never auto-reject.
5. **Automatically prepare and notify the interview after a clear pass.** In a transaction, record the screening outcome and pipeline event, move the application to the AI-interview-ready state, create a ready session against the same application and rubric version, and enqueue candidate notification. No recruiter action or manual meeting creation is needed per passing application. The application tracker is the source of truth if email delivery is delayed or fails; notification delivery is retried independently. The posting policy defines a self-start window or candidate self-scheduling window; the candidate chooses the actual start time.
6. **Candidate starts after disclosure.** On selecting “Start AI interview,” the candidate sees AI identity, data use/retention, accommodations, text fallback, and stop/reschedule controls. Record the applicable acknowledgement and explicit modality choice; only then request mic permission. No camera is requested in the first release.
7. **Conduct one level-aware technical + behavioral interview.** A typical posting might structure the session as: (a) short welcome and format explanation, unscored; (b) technical fundamentals at the target level; (c) role-specific problem-solving/system-design/debugging deep dive; (d) structured behavioral questions about relevant collaboration/ownership situations; and (e) candidate questions and clear close. The exact phases depend on the job family and its published competency plan. The session opens at the posting’s target job level (for example, entry/mid/senior), uses a bounded question bank tagged by difficulty, and asks relevant follow-ups. When the answer supports it, the controller may move at most one difficulty band up; when evidence is incomplete, it can clarify or remain at level. Every question, difficulty, branch reason, and answer is recorded. The candidate is not scored on which route they saw alone; the assessor compares the answer with anchored criteria and records the actual item level.
8. **Handle turns and recovery.** Each finalized question/answer has a stable ID and sequence. Persist/acknowledge completed turns before treating them as durable; reconnect resumes from the last acknowledged sequence. Allow repeat, rephrase, pause, end, transcript correction/flagging, and text alternative. A retry with the same idempotency key must not duplicate a turn or score.
9. **Score and produce the report automatically.** On explicit completion or deterministic configured limit, close the live media session and enqueue a report job. The assessor receives the frozen rubric/difficulty map and authorized transcript evidence, not unrelated applications. It produces per-competency anchored scores, evidence spans, evidence gaps, and transcription/technical caveats. Deterministic validation checks that cited turn IDs exist and quotes match stored text. The report is advisory and never changes the hiring outcome.
10. **Recruiter reviews the report in the specific job context.** The posting’s applicant view shows screening state, interview status, report history, rubric version, technical/behavioral scores, question difficulty path, cited transcript snippets/timestamps, evidence gaps, and AI/model provenance. Recruiters can review/correct/escalate or request another step; each action is stored as a separate attributed event.
11. **Human owns the hiring decision.** The pipeline controller may advance a validated clear pass from screening to the next assessment stage using the published policy. After the interview report is ready, only an authorized recruiter/hiring manager makes the hiring disposition (advance beyond assessment, hold, or reject) through the existing application transition route. A failed interview, screen exception, missing evidence, cancellation, empty report, or infrastructure failure must not silently become an automatic rejection.

## 7. Data model and API contracts

### Proposed data concepts

| Concept | Key fields/invariants |
|---|---|
| `posting_pipeline_policy_versions` (or equivalent immutable revision) | Posting/org, revision, explicitly structured eligibility constraints, profile/question requirements, screening rubric, target job level, competency weights/anchors, technical/behavioral question bank tagged by difficulty, follow-up/adaptive-level rules, interview window, modality/fallback, exception route, candidate notice, author/approver, created time. Publishing pins this revision; it is immutable. |
| `application_pipeline_runs` | Application ID, policy revision, overall state, screening job/attempt IDs, hard-constraint results, screening evidence references, reviewer-required reason, auto-invitation/session link, timestamps, and idempotency key. Unique per application/policy run unless a separately authorized retry is recorded. This is the auditable screening-to-interview orchestration record, not an LLM transcript. |
| `interview_sessions` | Session/attempt ID, application ID, organization ID, posting ID (derived/verified), optional scheduled-interview ID only when customer requests a calendar appointment, policy/rubric revision + snapshot, status (`READY`, `IN_PROGRESS`, `REPORT_PENDING`, etc.), modality, candidate/user link, consent/notice version and timestamps, prompt/model/provider version, started/ended times, and idempotency/retry metadata. A passing screen creates a `READY` session automatically; multiple attempts/history are supported. |
| `interview_turns` | Session ID, monotonic sequence, stable question/turn ID, speaker, final transcript text, timestamps, transcription source/status, correction/flag metadata, and optional confidence class. Unique `(session_id, sequence)`; no raw recording blob in this table. |
| `interview_events` | Append-oriented lifecycle events such as screening-passed, interview-ready, candidate-notified, consented, started, reconnected, difficulty-band-selected, completed, provider-failed, report-ready, and recruiter-reviewed; actor, time, and minimal structured metadata. Do not log prompts/raw audio by default. |
| `interview_assessments` | Session ID, rubric revision, competency key, asked question/level IDs, anchored score or null, evidence-sufficiency state, evidence references to turn IDs/time ranges, short rationale, schema/model/prompt version, validation status. Missing evidence remains missing; it is not silently reweighted into a decisive score. |
| `application_interview_reports` | Report ID, session ID, application/posting/org, rubric revision, report status, validated assessments/summary, deterministic weighted score if configured, generation provenance, reviewer state. Migrate from one-row-per-application to session/report history; keep a latest-summary read path for compatibility. |
| Consent and optional media metadata | Versioned notice/consent or other applicable lawful basis, collection scope, timestamps, revocation/retention. Raw media, if later approved, belongs in separate encrypted storage with its own access, deletion, and expiry controls—not report JSON or logs. |
| Existing `background_jobs` / outbox | `screen_application`, candidate-notification, and post-session evaluation/report jobs keyed by application/session ID, policy revision, and idempotency key; minimal payload; no resume/transcript copied into an unprotected job payload when the worker can reload it through authorized repository methods. Application creation and screening admission must commit atomically (job row/outbox in the same transaction). |

For tenant safety, every recruiter read/write must verify the same organization across application, posting, and session. Store `campaign_id` only if needed for efficient read models, and derive/validate it from the posting. Add suitable foreign keys/composite constraints where compatible with both SQLite and PostgreSQL; otherwise enforce the relationship in one repository transaction and test it. Add indexes for recruiter access by `(org_id, posting_id, application_id, created_at)` and candidate-owned access by `(candidate_user_id, status)` after confirming query patterns.

Keep broad application stage, screening job state, interview-session state, and hiring outcome separate. A proposed application-stage path is `APPLIED → SCREENING → AI_INTERVIEW → PENDING_REVIEW`; add/migrate the `AI_INTERVIEW` stage and update UI/funnel analytics if the existing enum cannot represent it. The pipeline run stores execution details such as `QUEUED`, `RUNNING`, `PASS`, `REVIEW_REQUIRED`, and retryable/terminal operational failure. A passing screen moves to `AI_INTERVIEW` and makes a session `READY`; report completion moves to `PENDING_REVIEW`. Suggested session progression is `READY → IN_PROGRESS → SUBMITTED → REPORT_PENDING → REPORT_READY → CLOSED`. Exceptional session states include `CANCELLED`, `EXPIRED`, `PROVIDER_FAILED`, and `REVIEW_REQUIRED`. A transient disconnect is recoverable and is not a terminal candidate outcome. Enforce legal transitions and optimistic version/idempotency guards server-side.

### Illustrative API surface (to refine before implementation)

| Actor | Operation | Authorization/contract |
|---|---|---|
| Recruiter | Configure/publish the posting’s automated pipeline policy and rubric revision. | One-time per posting/revision, with organization capability and campaign assignment; validate hard constraints, profile requirements, level map, score anchors, interview window, exception route, and candidate notice. |
| Candidate | Load application readiness, complete/save own profile, then submit application with required posting answers. | Extend the application-form response with profile readiness, required profile fields, and unanswered posting questions. Backend enforces the same contract. Application, snapshot, answers, and an idempotent screening job/outbox record commit atomically. No separate recruiter screen request is part of the normal path. |
| System worker | Screen every valid application submitted to a posting with automation enabled and prepare the next step. | Load the frozen posting policy; apply deterministic constraints and validated evidence assessment. On clear pass, automatically create an interview-ready session and notification. Borderline/provider/model exceptions go to review; model output cannot reject. |
| Candidate | View own application pipeline state and start a ready interview session. | Authenticated candidate must own the application; only `AI_INTERVIEW_READY` sessions can start; one-time or short-lived session capability and expiry checks. |
| Candidate | Submit disclosure/consent acknowledgement and request a session-scoped media connection. | Explicit versions and scope; return only ephemeral provider credentials if supported, never provider master keys. |
| Candidate | Stream real-time media/events or submit text turns. | Session-scoped authorization, bounded payloads/rate limits, sequence and idempotency, validated event types. Exact WebSocket/SDK route depends on provider spike. |
| Candidate | Complete, pause/resume, or report transcription problem. | Candidate owns session; completion is idempotent; technical failure maps to retry/review. |
| Recruiter | Read application pipeline, sessions, screening exceptions, and report history; record exception/final review actions. | Application-read plus current org and campaign checks; transcript detail is separately permissioned/audited where appropriate. No per-candidate screen/invite action is required for a clear pass. |

Use the existing candidate/recruiter route families and API client conventions. The exact endpoint names are intentionally illustrative until reviewed against current API contracts. Keep all state-changing operations as `POST`/`PUT`/`PATCH` with expected state/version or idempotency key. Status reads should be safe, scoped, and non-mutating.

## 8. Report design and scoring policy

The report is about **job-related evidence from this interview**, not a universal ranking of the person.

Recommended report fields:

- Application, posting, campaign, session, completion time, and exact rubric revision.
- The automatic screening outcome, pinned screening-policy revision, explicit constraints passed/missing, and why the candidate was made interview-ready; this remains distinct from the interview score.
- Each rubric competency’s anchored rating, evidence-sufficiency status, short explanation, and transcript turn/time references.
- Evidence gaps and unresolved questions, not just strengths/weaknesses.
- Transcript quality and any candidate-flagged or provider-detected uncertainty; a speech/transcription error is not scored as a weak answer.
- Model/provider/prompt/schema versions and report generation status for traceability.
- Clearly advisory overall weighted score, only if the recruiter configured one; show missing criteria and never quietly renormalize missing scores into a misleading total.
- The exact technical/behavioral question IDs, target level, difficulty bands encountered, and permitted branch reasons; scores from different adaptive paths remain non-comparable until the paths are validated/calibrated.
- Human reviewer decision and edits as separate, timestamped, attributable events.

Do not expose a self-reported LLM confidence value as a calibrated probability. Do not infer candidate characteristics from vocal or visual cues. A scoring failure or unsupported evidence citation must produce a report error/review state, not a score of zero or candidate rejection. The current keyword-matching report logic should not be reused as the new assessment logic; keep old historical reports identifiable as legacy if the representation changes.

## 9. Privacy, security, accessibility, and hiring governance

### Data minimization and retention

- Voice-only by default; request no camera permission in the MVP. Do not retain raw audio unless a separately reviewed need, clear notice, explicit storage decision, and retention/deletion plan justify it.
- Retain only finalized transcript turns, answer evidence needed for the report, version/provenance, and required audit metadata. Avoid raw model chain-of-thought and full prompt logs.
- Document transcript/audio/provider processing, processors/subprocessors, region, retention, model-training settings, deletion semantics, and incident contact before choosing a vendor.
- Define a retention period and deletion job across database, provider artifacts, observability, exports, and backups. A report/transcript should not live indefinitely because an application row still exists.
- Use the immutable application snapshot taken at application time. Later candidate profile edits must not silently change interview context.

### Candidate experience and access

- Disclose AI identity and recording/transcription behavior before the interview begins; do not impersonate a human recruiter.
- Provide a text equivalent, accommodation request route, repeat/rephrase/pause controls, visible mic state, keyboard/screen-reader support, and clear error/reconnect messages.
- Candidate can correct/flag a transcription issue or request human assistance. Keep interview language and supported accents explicit; never assume an accent is a capability measure.
- Treat resume, application answers, and candidate speech as untrusted content, not as instructions to the agent. Enforce role/competency allow-lists in code.

### Hiring process and legal review

- Human recruiters retain final hiring/selection and rejection authority. A deterministic, versioned pipeline policy may move a clearly eligible candidate automatically to `AI_INTERVIEW_READY`; this is permission to take the next assessment step, not a hiring disposition. For the first release, hard-constraint failures, borderline evidence, and model-only adverse outputs go to an exception/review state rather than auto-rejecting. Test that an LLM verdict cannot directly mutate an application stage; only the deterministic pipeline service may apply a validated policy transition.
- Before any external pilot, identify jurisdictions, employer/customer roles, and intended use; counsel/compliance must determine applicable employment, disability, privacy, recording/consent, automated decision, notice, and retention duties. NYC Local Law 144 and EU AI Act examples above are not exhaustive and are not interchangeable.
- If lawful and approved, evaluate quality and outcomes across appropriate candidate groups with a qualified audit design and adequate sample-size review. Do not infer fairness from uniform prompts or a small test set, and do not collect sensitive demographic data for an audit without approved purpose, access, retention, and legal basis.
- Never present an internal pass-rate ratio or model agreement as a formal bias audit, compliance finding, or proof of neutrality.

### Authorization and threat controls

- Candidate: own-application/session scope only. Recruiter: capability + org + application/posting consistency + assigned campaign. Platform admin access remains privileged and audited.
- Use short-lived, revocable session grants for live media; constrain them to a single session, duration, and permissions. Keep signing/provider secrets server-side.
- Validate all provider callbacks with signatures/replay protection; limit media/text duration, size, concurrency, and spend per org/session; redact personal data from logs/metrics.
- Persist the transcript/report through authorized repositories and tenant keys. Test horizontal privilege escalation across organizations/campaigns for every report, transcript, and session endpoint.

## 10. Reliability, quality measurement, and test plan

### Reliability behavior

- In one database transaction, save the application/profile snapshot/answers and an idempotent screening outbox/job record. Return a queued status; do not run a paid LLM screen inside the apply request. A durable worker retries/reclaims screening and records terminal exception states.
- After a validated screening pass, atomically persist the pass, `AI_INTERVIEW_READY` state, ready session, and candidate-notification job. If any part fails, an outbox/retry can complete it without losing the candidate or creating duplicate invitations.
- Failed hard constraints, uncertain profile evidence, model errors, and exhausted retries are visible pipeline exceptions. They cannot be mistaken for a completed screen or silently converted into rejection.
- Persist session state and turns in the database; the browser is a view/cache, never the source of truth.
- Use idempotent create/join/complete operations and a monotonic turn sequence. A disconnect resumes from the last acknowledged state; duplicate provider callbacks cannot duplicate a scored answer.
- Keep synchronous real-time turn response independent from the report job. Completion returns an explicit pending/report status; a poll or bounded event stream updates the recruiter view.
- Apply typed provider errors, timeouts, bounded retries/backoff, and a dead-letter/review state. Never let a late result overwrite a cancelled/revised session.
- Use the existing worker/job table pattern for long scoring/report tasks. Do not hold a database transaction open while waiting for a model/provider.
- Keep per-session model, prompt, rubric, transcript, and deployment provenance so a report can be explained and reproduced as far as provider determinism permits.

### Validation layers

1. **Domain tests:** profile readiness through resume-review and manual-entry paths; immutable posting policy; screening hard-constraint rules; pass/exception routing; target-level question selection; difficulty-step cap; rubric/question coverage; legal state transitions; completion/cancellation idempotency; missing-evidence behavior.
2. **Authorization tests:** candidate cannot apply with another user’s profile, join/read another candidate’s session, or view another application; recruiter cannot cross org or unassigned campaign; wrong posting/campaign/session IDs fail closed.
3. **Scoring contract tests:** required fields/enums/range bounds, every citation resolves to a stored turn, exact quote matches, unsupported/empty output becomes review-required, deterministic total arithmetic.
4. **Worker tests:** application submit admits exactly one screening job; duplicate/replayed jobs; retries; crash/restart/reclaim; candidate notification and ready session created once on pass; notification failure leaves the ready session visible in the tracker; provider timeout/rate limit; cancellation; stale worker result; one report per session revision.
5. **Provider contract tests:** mocked provider for CI; live-provider tests are secret-gated and spend-capped. Verify scoped credentials, reconnects, turn completion, transcript event ordering, and deletion/retention assumptions.
6. **Frontend tests:** incomplete profile blocks apply with resume-import/manual-entry options; application submit shows screening queued; passing screen makes the AI interview ready without recruiter action; candidate disclosure, permission denied, text fallback, mic stop indicator, level-aware technical/behavioral turns, pause/reconnect, transcript flag, interview completion; recruiter sees progress/report only under the correct posting/application and can record human review.
7. **PostgreSQL tests:** real migration on an existing DB, unique constraints, concurrent joins/submissions, tenant predicates, and atomic job claims. SQLite tests alone are not concurrency proof.
8. **Accessibility and device tests:** keyboard/screen-reader flow, reduced motion, mobile/narrow viewport, supported browser permissions, no HTTPS/media access assumptions in insecure production pages.
9. **Fairness/quality evaluation:** a reviewed role-specific case set with acceptable evidence/scoring anchors, clear insufficient-evidence cases, transcription-error cases, prompt injection, paraphrases, and adversarial polished-but-wrong answers. Hold out cases from prompt tuning; use human adjudication and report sample counts/disagreement.

### Pilot metrics (measure; do not pre-claim)

- Profile completion, application submit → screening-start and screening-completion latency, exception rate, pass-to-interview-ready latency, notification delivery, and candidate invitation → join → completion/abandonment; report denominators and population.
- Recruiter actions per application before interview-ready, exception queue size/age, and percentage of clear-pass applications that reached interview-ready without manual intervention. This directly tests the no-click operational goal.
- Real-time turn latency, transcription/task-critical error rates, reconnect success, provider/API error rate, and report completion time.
- Per-competency human/AI agreement and score disagreement by target job level and asked difficulty band; reviewer corrections/overrides; evidence citation failure rate; insufficient-evidence and escalation rates.
- Candidate feedback on clarity, respect, accessibility, and trust, with response count and survey wording.
- Cost per completed interview and cost per recruiter-reviewed report, including retries, speech, infrastructure, and human review.
- Outcome/fairness analyses only under approved governance; publish slice counts and uncertainty. Do not use SSRN’s claimed 65%, 91%, or 4.6/5 as this product’s targets or results.

Set numeric service-level and quality thresholds only after the selected provider and baseline workload are measured. Any cross-tenant access, candidate outcome changed by infrastructure failure, ungrounded scored claim, consent/retention violation, or unreviewed automatic rejection is a release blocker.

## 11. Phased implementation plan and exit gates

| Phase | Deliverables | Exit gate |
|---|---|---|
| **0 — Policy, legal, and provider decisions** | Select pilot role(s), rubric owner, target job levels, required profile fields/constraints, core question/difficulty bank, target jurisdictions, exception policy, candidate self-start interview window, accommodation route, retention/notice model, provider criteria, and cost ceiling. Explicitly approve the intended operating model: recruiters configure once per posting and do not screen/invite/schedule each applicant. Run a synthetic real-time voice spike without candidate data. | Policy owner approves criteria, deterministic pass/exception routing, and the no-per-applicant-click operating model; privacy/legal review path is identified; provider supports required session, transcript, security, and deletion controls or a text-first pilot is selected. |
| **1 — Profile readiness and automatic screening** | Strengthen profile onboarding with resume parse → editable review → save and a complete structured manual-entry alternative. Version posting eligibility/screening policy. Update application submit so app + snapshot + answers + screening outbox/job are atomic. Add durable screening worker, evidence-linked outcome, retry, idempotency, candidate status, and exception queue. Remove the recruiter screen button/action from the normal path; retain a controlled retry/review tool only for failures. | Submitting a valid application automatically queues exactly one screen; incomplete profile is stopped before submission; passing rules never depend on a recruiter click; model/provider failures become visible exceptions, not candidate outcomes. |
| **2 — Automatic interview-ready transition** | On a validated screening pass, atomically record the outcome, move the application to `AI_INTERVIEW_READY`, create a ready session pinned to the policy, and enqueue candidate notification. Add candidate tracker progress/start action and recruiter application-level pipeline visibility. No per-app recruiter invite or meeting creation. | A passing synthetic application reaches a ready session and candidate notice without a recruiter action; duplicate worker execution creates neither duplicate invitation nor session; candidate can start only their own ready session. |
| **3 — Level-aware technical/behavioral interview** | Build the candidate lobby/session, AI disclosure, consent/device check, text alternative, real-time voice adapter, fixed core questions, target-level start, bounded adaptive difficulty and follow-ups across technical and behavioral phases, persisted turns, pause/reconnect/complete. Use mocked provider in CI and no webcam by default. | A candidate completes a role/level-specific interview; every question/branch is allowed and logged; spoken/text path is accessible; reconnect/provider failures do not count against the candidate. |
| **4 — Assessment, report, and human decision** | Add rubric- and difficulty-aware scoring, citation validation, deterministic aggregation, durable report generation/history, recruiter evidence UI, exception review, and separate human stage-change events. Replace or version the current heuristic report for new sessions. | Every displayed score maps to an anchored criterion and valid evidence or an explicit gap; no model-only rejection or final decision; recruiter can inspect the exact application/posting/rubric and record a decision. |
| **5 — Controlled pilot and hardening** | Seed reviewed screen/interview cases; independent rubric review; provider/database fault tests; privacy/retention/delete rehearsal; candidate UX study; queue/latency/cost baseline; runbook; limited pilot under approvals. | Quality, accessibility, cost, automation-coverage, and legal/privacy owners sign off against observed evidence; exceptions, sample counts, and limitations are documented before expansion. |

No calendar estimate is committed here. A credible estimate depends on Phase 0 decisions, real-time provider availability, legal/vendor review, and the number of supported roles/languages. The voice provider spike and report-per-session schema are the highest-risk early tasks.

## 12. Suggested repository ownership map

Keep files grouped by domain rather than adding interview logic across unrelated application controllers.

| Area | Proposed ownership |
|---|---|
| Application pipeline | Add a bounded service around candidate application submission for profile readiness, immutable snapshots, and atomic application + screening-job/outbox admission. Keep the existing candidate controller as a thin HTTP boundary. |
| Screening/session domains | A proposed `backend/app/application_pipeline/` package owns versioned hard constraints, screening assessment, pass/exception routing, and notification admission. A new `backend/app/ai_interview/` package owns session state, conversation orchestration, provider protocols/adapters, transcript turns, and score/report validation. |
| Schemas/migrations | Add additive SQLite/PostgreSQL schema and ordered migration entries for policy versions, pipeline runs/events, sessions, turns, and report history; update application/report repositories with compatibility reads. Do not hand-edit only one dialect. |
| Criteria | Extend `backend/app/interview_criteria/` for immutable eligibility, role-level/difficulty, rubric revisions, and validated scoring anchors; retain current read APIs while new applications use pinned revision IDs/snapshots. |
| Worker | Register application-screening, candidate-notification, and post-session score/report jobs in `backend/app/worker/job_worker.py`; payloads contain IDs and trace metadata, not raw candidate content. |
| Candidate UI | Strengthen `frontend/app/profile/page.tsx` and the job apply page with resume-import/manual profile readiness; add pipeline status and an AI-interview lobby/session route plus reusable media/session hooks. |
| Recruiter UI | Extend the posting-level configuration once and the applicant drawer in `frontend/app/org/postings/[id]/page.tsx` with aggregate pipeline progress, exception queue, evidence report, history, and human review. Do not require a per-applicant screen/invite action. |
| API client | Add typed request/response methods in the existing frontend API client. Avoid ad-hoc `fetch` calls with unvalidated report shapes. |
| Tests/docs | Add backend domain/API/worker tests, PostgreSQL migration tests, Playwright candidate and recruiter flows, evaluation fixtures, and update API/data-model/security docs alongside implementation. |

These are proposed ownership boundaries, not files created in this planning task.

## 13. Decisions required before implementation

1. Which first role family and which exact, job-related competencies/anchors? Who approves the rubric and example answers?
2. Confirm the default interview window and whether any pilot customer requires calendar appointments. The proposed default is an automatically created, candidate-started session within a posting-defined window; calendar scheduling is optional. What text/accommodation fallback is required?
3. Which launch jurisdictions and employer customers are in scope? Who signs off disability accommodation, recording/transcription notice, privacy, and AEDT/high-risk assessment?
4. Which voice/model provider passes data residency, no-training/retention, scoped credentials, transcript, latency, accessibility, reliability, and cost review?
5. Will the product retain transcript text only, and for how long? Is any raw audio retention necessary? Who can read full transcripts versus report excerpts?
6. What is the recruiter workflow after report: reviewer approval required for every report, or risk/insufficiency-based review? The human still owns application transitions either way.
7. What languages and expected device/browser/network ranges must the first pilot support?
8. What volume/concurrency, maximum interview length, per-org budget, and report latency are acceptable? Establish through a measured pilot, not the attached paper.

## 14. Research and code references

All web sources were reviewed on **2026-10-01**. Legal sources are for product-risk identification; applicability and current effective requirements must be checked with qualified counsel.

1. Pathak, Gangesh & Pandey, Divya. “AI Agents in Recruitment: A Multi-Agent System for Interview, Evaluation, and Candidate Scoring.” SSRN, DOI [10.2139/ssrn.5242372](https://doi.org/10.2139/ssrn.5242372). Reviewed against the user-supplied `ssrn-5242372.pdf`; findings/limitations above refer to that copy.
2. Dishant1804, [multi-agent-interviewer](https://github.com/Dishant1804/multi-agent-interviewer), especially its [interview loop](https://github.com/Dishant1804/multi-agent-interviewer/blob/master/interview_system.py), [agent modules](https://github.com/Dishant1804/multi-agent-interviewer/tree/master/agents), and [dependencies](https://github.com/Dishant1804/multi-agent-interviewer/blob/master/requirements.txt). Inspected 2026-10-01; the limitations above are based on the README and listed source files, not on a production deployment or independent evaluation.
3. U.S. Office of Personnel Management, [Structured Interviews](https://www.opm.gov/policy-data-oversight/assessment-and-selection/structured-interviews/).
4. NIST, [AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework) and [Generative AI Profile (NIST AI 600-1)](https://doi.org/10.6028/NIST.AI.600-1).
5. U.S. Equal Employment Opportunity Commission, [The Americans with Disabilities Act and the Use of Software, Algorithms, and Artificial Intelligence to Assess Job Applicants and Employees](https://www.eeoc.gov/laws/guidance/americans-disabilities-act-and-use-software-algorithms-and-artificial-intelligence-assess-job-applicants-and-employees).
6. NYC Department of Consumer and Worker Protection, [Automated Employment Decision Tools (AEDT)](https://www.nyc.gov/site/dca/about/automated-employment-decision-tools.page).
7. European Union, [Regulation (EU) 2024/1689 (Artificial Intelligence Act)](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng), especially Article 6 and Annex III, point 4.
8. MDN Web Docs, [WebRTC API](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API) and [MediaDevices.getUserMedia()](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).
9. FastAPI, [Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
10. Current application integration anchors: [hiring schema](../backend/app/config/hiring_schema.py), [candidate controller](../backend/app/candidate/controller.py), [hiring controller](../backend/app/hiring/controller.py), [evaluation worker](../backend/app/worker/job_worker.py), [criteria/report service](../backend/app/interview_criteria/service.py), and [recruiter posting page](../frontend/app/org/postings/[id]/page.tsx).
