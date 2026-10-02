# API reference

Base URL: the FastAPI app root (`http://127.0.0.1:8000` in local dev, or
whatever `BACKEND_URL` points the frontend's `/api/*` proxy at — see
[ARCHITECTURE.md](ARCHITECTURE.md)). All request/response bodies are JSON
unless noted. Hiring, prep, export, deletion, and authenticated evaluation
endpoints require bearer authentication; the public sandbox is token-scoped.
See [SECURITY.md](SECURITY.md).

Every field and status code below was read directly from `routes.py` and
`models.py`; response examples are illustrative, not literal captures,
except where marked "captured from a live test run."

## Conventions used across endpoints

- Mutating endpoints take `evaluation_id` as a **query parameter**, not a
  path parameter (a historical/API-design choice, not a bug):
  `POST /round/2/answer?evaluation_id=123`.
- `AgentOutputError` (malformed/invalid LLM output) always surfaces as
  **HTTP 502** with `{"detail": "<agent> ... invalid response. Please retry."}`
  — never as a PASS/FAIL/HIRE/REJECT decision. The failure is separately
  persisted as a verdict row with `decision="INVALID_OUTPUT"`.
- Any other unhandled exception surfaces as **HTTP 500** with a generic
  `{"detail": "An unexpected server error occurred. Please try again."}` —
  the real exception is logged server-side only, never echoed to the client
  (see [SECURITY.md](SECURITY.md)).
- Exceeding the in-memory rate limit surfaces as **HTTP 429** with a
  `Retry-After` header (see [ARCHITECTURE.md](ARCHITECTURE.md#rate-limiting)).

### Authentication

Authenticated endpoints expect a bearer token:

```
Authorization: Bearer <access_token>
X-Org-Id: 7          # optional; selects the active organization
```

The active organization is chosen **per request** via `X-Org-Id` rather than
being baked into the token. This lets a user who belongs to several
organizations switch context without re-authenticating, and means a revoked
membership takes effect on the very next request rather than when the token
expires.

**Cross-tenant requests return 404, not 403.** A 403 would confirm that a
resource exists, letting a competitor enumerate another company's IDs.

---

## Identity

### `POST /auth/register`

Creates an account. New accounts have no organization membership — they begin
as candidates.

```json
{ "email": "jane@example.com", "password": "at-least-12-chars", "full_name": "Jane Doe" }
```

| Status | When |
|---|---|
| 201 | Created; returns `{access_token, token_type, expires_in}` |
| 409 | Email already registered |
| 422 | Invalid email, or password shorter than 12 characters |

> Password minimum is length-based (12) rather than composition-based.
> Composition rules push users toward predictable substitutions; length is
> what actually resists offline cracking (NIST SP 800-63B).

### `POST /auth/login`

| Status | When |
|---|---|
| 200 | `{access_token, token_type, expires_in}` |
| 401 | Unknown email **or** wrong password — deliberately indistinguishable, and with comparable response time, so the endpoint cannot be used to enumerate accounts |

### `POST /auth/refresh`

Renews a normal authenticated session while the current bearer token is still
valid. The frontend asks for explicit user consent in the final 15 minutes of
the session before calling this endpoint. The response has the same shape as
login and registration: `{access_token, token_type, expires_in}`.

Impersonation tokens cannot be renewed; they retain their separate 30-minute
maximum lifetime and remain attributable to the originating administrator.

### `GET /auth/me`

Returns the caller's identity, active org context, capabilities, and all
memberships.

```json
{
  "user_id": 42, "email": "jane@example.com", "full_name": "Jane Doe",
  "is_platform_admin": false,
  "active_org_id": 7, "active_role": "recruiter",
  "capabilities": ["application:read", "campaign:create", "..."],
  "memberships": [{"org_id": 7, "org_name": "Acme", "org_slug": "acme", "role_name": "recruiter"}]
}
```

`capabilities` is intended for the frontend to decide which controls to
render. That is a UX affordance only — every capability is re-checked
server-side on each request.

### `GET /auth/me/export`

Returns the authenticated user's portable profile, memberships, applications,
AI-interview invitation/consent metadata and owned turns (including saved
drafts and transcript/source), human interview agenda, notifications, and owned
evaluation summaries. Recruiter-only screening inputs and assessment scores,
password hashes, and token secrets are never included.

### `DELETE /auth/me`

Anonymizes the account and removes candidate-owned profile/application/prep
data, including AI-interview turns/reports; queued or running AI-interview
jobs are cancelled/requested to cancel. The request is rejected with `409`
while the user is an active owner of an organization. Completed interview data
for still-active accounts follows any configured retention policy; no universal
automatic expiry policy is currently enabled.

---

## Organizations

| Endpoint | Capability required | Notes |
|---|---|---|
| `POST /orgs` | *(any authenticated user)* | Creator becomes `org_owner` in the same request — an org without an owner would be unadministrable |
| `GET /orgs/{org_id}` | `org:settings:read` | 404 across tenants |
| `GET /orgs/{org_id}/members` | `org:settings:read` | |
| `POST /orgs/{org_id}/members` | `org:member:invite` | Adds an already-registered user directly |
| `POST /orgs/{org_id}/invitations` | `org:member:invite` | Creates a hashed, expiring invitation; SMTP delivery is best-effort |
| `GET /orgs/{org_id}/invitations` | `org:settings:read` | Lists invitation metadata without token secrets |
| `POST /auth/invitations/accept` | authenticated | Accepts a token only for the invited email |
| `PATCH /orgs/{org_id}/members/{user_id}` | `org:member:role:set` | 409 if it would demote the last owner |
| `DELETE /orgs/{org_id}/members/{user_id}` | `org:member:remove` | 409 if it would remove the last owner |

Assignable org roles: `org_owner`, `org_admin`, `recruiter`,
`hiring_manager`, `interviewer`. `candidate` is **not** assignable to an
organization and is rejected with 400 — it is a platform-level persona, not
an org role.

---

## Durable interview commands

The `/v1` commands return `202` after durable admission. Run
`python job_worker.py` separately to execute jobs. They reuse the existing
agent functions and do not change the legacy synchronous route behavior.

| Endpoint | Purpose |
|---|---|
| `POST /v1/evaluations` | Queue screening; supports `Idempotency-Key` |
| `POST /v1/evaluations/{id}/answers` | Persist an answer and queue technical/behavioral evaluation |
| `POST /v1/evaluations/{id}/finalize` | Queue recommendation and committee finalization |
| `GET /v1/evaluations/{id}` | Read scoped evaluation and durable job status |

---

## Preparation suite

All require authentication and are user-scoped. The current suite is
text-first: submissions are recorded for review, never executed, and never
automatically marked as verified skills.

| Endpoint | Purpose |
|---|---|
| `GET /prep/topics` | Curated topic graph nodes |
| `GET /prep/problems` / `GET /prep/problems/{id}` | Starter problem catalog |
| `POST /prep/roadmaps` | Create a deterministic roadmap |
| `GET /prep/roadmaps` / `GET /prep/roadmaps/{id}` | Read owned roadmaps |
| `POST /prep/roadmaps/{id}/nodes/{node_id}/complete` | Record progress and XP |
| `POST /prep/problems/{id}/submissions` | Record an unverified written response |
| `GET /prep/me/stats` | Read prep XP/streak state |

---

## Administration

All require platform-admin capabilities and are audited at Tier 1.

| Endpoint | Purpose |
|---|---|
| `GET /admin/audit` | Search the audit log. Non-platform-admins are forcibly scoped to their own org regardless of the `org_id` they request |
| `GET /admin/audit/verify` | Walk the hash chain; `{"valid": false, "broken_at_id": N}` means the log was altered and should be treated as an incident |
| `POST /admin/impersonate` | Issue a 30-minute token acting as another user. Requires a written `reason` (min 10 chars) stored permanently in the audit log. Refuses self-impersonation and admin-on-admin impersonation |
| `GET /admin/organizations` | Cross-tenant organization listing |

---

## Candidate: profile vault

All operate on the **caller's own** data — every query is keyed on the
authenticated user ID, never on an ID from the request, so there is no path
by which one candidate reads another's profile.

| Endpoint | Purpose |
|---|---|
| `GET /me/profile` | The complete vault in one call: profile, experience, education, skills, preferences, saved answers |
| `PUT /me/profile` | Create or update. Idempotent. Stamps data-processing consent on creation |
| `POST /me/profile/experience` · `DELETE /me/profile/experience/{id}` | Work history. Deletes are scoped by profile, so a guessed ID returns 404 |
| `POST /me/profile/education` | Education history |
| `PUT /me/profile/skills` | Replace claimed skills. **Skills verified by in-platform performance keep their verified flag** — a profile edit cannot fabricate or erase that signal |
| `PUT /me/profile/preferences` | Target roles, locations, comp band, notice period |
| `PUT /me/profile/vault` | Save a reusable answer directly |

## Candidate: jobs and applications

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /jobs` | none | Public job board. Published postings only, across all orgs. Filters: `q`, `location`, `remote_policy` |
| `GET /jobs/{id}` | none | Posting detail. 404 unless published |
| `GET /jobs/{id}/application-form` | required | **The "fill it once" endpoint.** Returns posting questions with `prefilled_answer`, `unanswered_count`, `profile_complete`, and `missing_profile_fields`. A profile is ready when it has resume text or a professional headline plus at least one skill or experience entry |
| `POST /jobs/{id}/apply` | required | Submit. Answers not supplied are taken from the vault; supplied answers are written back unless `save_answers_to_vault: false`. The server requires profile readiness and required answers (400 otherwise), returns 409 on duplicate, and atomically creates the application, frozen screening snapshot, interview session, and idempotent screening job. Returns 201 with `status: SCREENING_QUEUED` |
| `GET /me/applications` | required | Application tracker |
| `GET /me/applications/{id}` | required | Detail plus timeline. **Internal recruiter notes are deliberately excluded** |
| `POST /me/applications/{id}/withdraw` | required | Withdraw. Allows re-applying later, since the uniqueness index excludes withdrawn rows |

### Candidate: application-linked AI interview

Applications are automatically checked against recruiter-set minimum
criteria and evidence-screened by the durable worker. A clear pass prepares an
AI interview invitation without per-applicant recruiter scheduling. Candidate
answers are spoken in the browser, transcribed into captions, and submitted as
voice-sourced text; the AI asks questions as text. Evalia stores the transcript,
not raw audio. A text-answer accommodation remains available.

| Endpoint | Purpose |
|---|---|
| `GET /me/applications/{application_id}/ai-interview` | Read own pipeline/interview state, question turns, modality, invitation expiry, rubric and notice versions. Other candidates receive 404 |
| `POST /me/applications/{application_id}/ai-interview/start` | Start after acknowledging `{ "accepted": true, "notice_version": "ai-interview-v1", "modality": "VOICE" }`; `TEXT` is available as an accommodation. A stale notice version returns 409 |
| `POST /me/applications/{application_id}/ai-interview/text-accommodation` | During an active voice interview, submit `{ "notice_version": "ai-interview-v1" }` to switch to text. Candidate ownership and the acknowledged notice version are re-checked; the choice is audited and idempotent |
| `POST /me/applications/{application_id}/ai-interview/answers` | Submit `{ "turn_id": 123, "answer": "...", "source": "VOICE" }`; returns 202 while a durable worker assesses the transcript. `source` defaults to `TEXT` for older clients. Replays are idempotent |
| `GET /me/interviews` | Unified candidate/interviewer agenda of AI screening/invitation state and scheduled human calls; AI items include `join_href`/`can_join` |
| `POST /me/interviews/{interview_id}/join` | Return a two-minute, room-scoped WebSocket ticket and ICE server configuration for an assigned participant during the scheduled join window. Configured coturn URLs receive user/room-bound HMAC credentials expiring after 10 minutes; the shared secret is never returned |

The WebSocket endpoint is `/ws/interviews/{interview_id}`. The client sends
`Sec-WebSocket-Protocol: evalia-meeting-v1, <ticket>` and relays only WebRTC
`offer`, `answer`, and `ice_candidate` messages. Media is peer-to-peer; the
server is a process-local signaling relay.

Candidate-visible session statuses include `SCREENING_QUEUED`, `SCREENING`,
`INTERVIEW_READY`, `INTERVIEW_IN_PROGRESS`, `ANSWER_PROCESSING`,
`REPORT_PENDING`, `REPORT_READY`, `REVIEW_REQUIRED`, `CANCELLED`, and
`EXPIRED`. `PENDING_REVIEW` is an application stage, not a session status. A
clear screen advances the application to `AI_INTERVIEW`; report publication
moves it to `PENDING_REVIEW` only if a recruiter has not already advanced it.

### Recruiter: criteria, reports, decisions, and team

These routes require the organization header, tenant check, and campaign
assignment check. Posting criteria writes require `campaign:update`; interview
and report reads require `application:read`; approving a screening exception
requires `application:read` and `application:advance`.

| Endpoint | Purpose |
|---|---|
| `GET /orgs/{org_id}/postings/{posting_id}/criteria` | Read the posting rubric and interview settings |
| `PUT /orgs/{org_id}/postings/{posting_id}/criteria` | Configure competencies (including technical and behavioral categories), screening threshold, role level, core question counts, custom questions, and bounded follow-up count for future applications |
| `GET /orgs/{org_id}/applications/{application_id}/ai-interview` | Read screening status/evidence and recruiter-authorized persisted interview turns |
| `POST /orgs/{org_id}/applications/{application_id}/ai-interview/approve-screening-exception` | Explicitly approve an uncertain screening exception with a required 10–2000 character reason; approval is audited and prepares the interview |
| `GET /orgs/{org_id}/applications/{application_id}/report` | Read the application-linked screening and interview report. Returns 404 until the report is published |
| `POST /orgs/{org_id}/applications/{application_id}/decision` | `{ "action": "PROMOTE", "target_stage": "TECHNICAL", "scheduled_start": "...", "scheduled_end": "...", "interviewer_user_ids": [42], "reason": "..." }`; human-only promote/hold/reject. Promotion schedules an in-app round atomically; rejection/hold and nudge overrides require a reason. `OFFER` is allowed only after a completed human round |
| `POST /orgs/{org_id}/applications/{application_id}/ai-interview/reinvite` | Re-open an expired invitation with a required reason and a fresh expiry/reminder cycle |
| `GET /orgs/{org_id}/team` | List active members with interview skills, timezone, availability, capacity, and scheduled load |
| `PUT /orgs/{org_id}/members/{user_id}/interview-profile` | Update the caller's interview title/skills/timezone/capacity/availability; org role managers can update another member |
| `POST /orgs/{org_id}/interviews/{interview_id}/scorecard` | Assigned interviewer submits independent 1–5 ratings; every category requires at least 10 characters of job-related evidence, plus an ADVANCE/HOLD recommendation and notes |
| `GET /orgs/{org_id}/interviews/{interview_id}/scorecards` | Recruiter reads panel status; individual ratings are hidden until every assigned interviewer submits. Assigned interviewers can read only their own submission until then |

AI interview report recommendations are `HUMAN_REVIEW_REQUIRED`; the
adaptive-path weighted total is withheld pending calibration. The report is
advisory evidence, not a hiring decision.

## Recruiter: campaigns, postings, pipeline

All require `X-Org-Id` and a capability. Every query is org-scoped in SQL as
well as checked at the route layer.

| Endpoint | Capability |
|---|---|
| `POST /orgs/{org_id}/campaigns` | `campaign:create` |
| `GET /orgs/{org_id}/campaigns` · `GET .../campaigns/{id}` | `campaign:read:assigned`; list accepts `include_archived=true` for the archive view |
| `PATCH /orgs/{org_id}/campaigns/{id}` | `campaign:update` — partial edit of name, description, department, hiring manager, priority, targets, close date, and `ACTIVE`/`CLOSED` status |
| `DELETE /orgs/{org_id}/campaigns/{id}` | `campaign:update` — soft-archive; closes published roles and preserves application/interview history |
| `POST /orgs/{org_id}/campaigns/{id}/restore` | `campaign:update` — restore as `CLOSED`; roles remain closed until individually reopened |
| `POST /orgs/{org_id}/postings` | `campaign:create` — created as `DRAFT`; cannot attach to another org's campaign |
| `GET /orgs/{org_id}/postings` · `GET .../postings/{id}` | `campaign:read:assigned`; list accepts `include_archived=true` |
| `PATCH /orgs/{org_id}/postings/{id}` | `campaign:update` — edit role details, requirements, application questions, and compensation/experience ranges; in-flight applications retain their frozen snapshots |
| `DELETE /orgs/{org_id}/postings/{id}` | `campaign:update` — soft-archive; hides the role from candidates and preserves applications/reports |
| `POST /orgs/{org_id}/postings/{id}/restore` | `campaign:update` — restore as `DRAFT` or `CLOSED`; publishing is still a separate action |
| `POST /orgs/{org_id}/postings/{id}/status` | `posting:publish` — publish, close, or explicitly reopen; publishing is blocked if the parent campaign is closed/archived |
| `GET /orgs/{org_id}/postings/{id}/applications` | `application:read` — returns applicants plus per-stage funnel counts |
| `GET /orgs/{org_id}/applications/{id}` | `application:read` — **audited at Tier 3** as a sensitive read |
| `POST /orgs/{org_id}/applications/{id}/transition` | `application:advance`, **plus `application:reject` to reject** |

The legacy `POST /orgs/{org_id}/applications/{id}/screen` remains for older
applications without an AI-interview workflow. It returns 409 for new
applications already admitted to automatic screening; it is not part of the
normal applicant flow.

### Campaign and role lifecycle

Closing a campaign also closes any published postings within it. Reopening a
campaign does **not** republish its roles; each role must be explicitly
reopened. The edit/delete icons on the campaign and role cards use reversible
soft-archive operations rather than SQL `DELETE`, so applications, answers,
events, AI-interview turns, and reports are not cascaded away. Archived items
are available from the `Archived` filter and can be restored. Restoring a role
does not publish it, and restoring a campaign leaves it closed until the
recruiter reopens it. This prevents accidental public hiring or loss of
applicant history while still allowing old campaigns and roles to be cleaned
out of the active workspace.

### Application stages

```
APPLIED → SCREENING → AI_INTERVIEW → PENDING_REVIEW → INTERVIEW → OFFER → HIRED
  ↓          ↓            ↓              ↓
     PENDING_REVIEW (screening exception or AI report awaiting a human)
                ↓
          REJECTED / WITHDRAWN  (terminal)
```

The legacy `TECHNICAL` and `BEHAVIORAL` stages remain supported for existing
workflows; the new application-linked text interview uses `AI_INTERVIEW` and
then `PENDING_REVIEW`.

Transitions are validated against an explicit table — an out-of-order or
replayed request returns **409** rather than corrupting pipeline history.
Terminal stages have no exits.

`PENDING_REVIEW` exists because the application-linked AI flow does not make
model-only rejection or final hiring decisions. Unclear screening evidence
and completed interview reports are presented for human review. See
[DECISIONS.md](DECISIONS.md) D-10.

---

## Candidate: recommendations & referrals

| Endpoint | Purpose |
|---|---|
| `GET /me/recommended-jobs` | Every open posting the candidate hasn't applied to, ranked by the matching engine, each with a human-readable `explanation` |
| `GET /me/referrals` | Referrals made *to* this candidate's email, across every organization — matched by normalized email, not requiring the referrer to know the candidate has an account |

## Recruiter: sourcing, referrals, analytics

| Endpoint | Capability | Purpose |
|---|---|---|
| `GET /orgs/{org_id}/candidates/search` | `candidate:search` | Talent-pool search. Only returns profiles with `is_discoverable = true` — enforced in the query itself, not a post-filter. **Audited at Tier 3**: browsing people who haven't applied to you is a different act than reading your own pipeline |
| `GET /orgs/{org_id}/postings/{id}/recommended-candidates` | `candidate:search` | Discoverable candidates ranked against this posting by the same matching engine used for job recommendations |
| `POST /orgs/{org_id}/postings/{id}/referrals` | `candidate:refer` | Refer a candidate by email. 409 on a duplicate open referral for the same posting |
| `GET /orgs/{org_id}/referrals` | `application:read` | Referrals made by this organization's recruiters |
| `GET /orgs/{org_id}/analytics/funnel` | `campaign:read:org` | Stage-to-stage conversion. Gated at org-wide read (hiring manager and above), not the narrower `campaign:read:assigned` a plain recruiter holds |
| `GET /orgs/{org_id}/analytics/selection-rates` | `campaign:read:org` | Disparate-impact-style selection-rate divergence by `source` or `experience_band` |

### The matching engine (Stage 1: deterministic)

Every score is a weighted average of five explainable components —
skills (40%), experience fit (25%), location/remote fit (20%), compensation
overlap (10%), profile recency (5%) — scaled to 0–10. **Every score ships
with its own explanation**; a bare number nobody can interrogate is not a
recommendation, it's a black box.

```json
{
  "score": 8.4,
  "components": {"skills": 0.9, "experience": 1.0, "location": 1.0, "compensation": 0.7, "recency": 1.0},
  "matched_skills": ["Python", "FastAPI", "PostgreSQL"],
  "missing_skills": ["Kubernetes"],
  "explanation": "Strong overlap on Python, FastAPI, PostgreSQL. Gap: missing Kubernetes. 5 years is within the 4-7 year requirement. posting location matches a candidate preference."
}
```

The same scoring function ranks both directions (jobs→candidate and
candidates→job); only which side is held fixed differs at the call site. See
[PRODUCT_BLUEPRINT.md §8.1](PRODUCT_BLUEPRINT.md) for why semantic (Stage 2)
and learned (Stage 3) ranking are deliberately deferred — Stage 3 in
particular requires real outcome data that does not exist yet.

A verified skill (demonstrated in-platform, not self-claimed) earns a bonus
within the skills component, capped so it cannot alone guarantee a match —
see [SECURITY.md](SECURITY.md) for why this is weighted conservatively
rather than treated as a hard filter.

### Selection-rate divergence — what it is and isn't

`GET /analytics/selection-rates` reports the same four-fifths-rule ratio a
formal EEO bias audit would use (lowest selection rate ÷ highest, flagged
below 0.8), computed over `source` or a derived `experience_band` —
deliberately **not** a protected characteristic, since none is collected
(see [DECISIONS.md](DECISIONS.md) D-05). This is the mechanism, tested and
working; it is explicitly **not** a substitute for a compliant bias audit,
and the response's own `note` field says so. A `flag_adverse_impact: true`
result is itself audited at Tier 1.

---



## `POST /start`

Creates a new evaluation and runs round 1 (screening), and — if the
candidate passes — generates round 2's technical questions in the same
call.

**Authentication is optional.** With credentials, the evaluation is
attributed to that user (and organization, if `X-Org-Id` is sent) and an
`evaluation.created` audit event is written. Without them it is created
unowned, exactly as before the identity layer existed. An invalid or expired
token degrades to anonymous rather than failing the request.

**Request body** (`StartRequest`):

```json
{
  "resume": "string, 1-20000 chars, required",
  "role": "string, 1-200 chars, required — must be one of GET /roles",
  "candidate_name": "string, 0-200 chars, optional, default ''"
}
```

**Responses:**

| Status | When | Body shape |
|---|---|---|
| 200 | Screening ran successfully (PASS/BORDERLINE → `IN_PROGRESS`, FAIL → `REJECTED`) | See below |
| 400 | Empty resume, empty role, or role not in `AVAILABLE_ROLES` | `{"detail": "..."}` |
| 502 | Screening or technical-question-generation agent returned invalid output | `{"detail": "..."}` |

Body on **PASS/BORDERLINE** (advances):

```json
{
  "evaluation_id": 1,
  "round": 1,
  "decision": "PASS",
  "verdict": { "...": "full ScreeningVerdict object" },
  "verdict_text": "raw agent output",
  "status": "IN_PROGRESS",
  "next_round": 2,
  "question": "1. ...\n2. ...\n3. ..."
}
```

Body on **FAIL** (rejected):

```json
{
  "evaluation_id": 1,
  "round": 1,
  "decision": "FAIL",
  "verdict": { "...": "full ScreeningVerdict object" },
  "verdict_text": "raw agent output",
  "status": "REJECTED",
  "message": "The candidate did not pass the screening round."
}
```

---

## `POST /round/2/answer?evaluation_id={id}`

Submits the candidate's technical answer and runs the technical evaluation
agent; on PASS, also generates round 3's behavioral question.

**Request body** (`AnswerRequest`): `{"answer": "string, 1-10000 chars"}`

| Status | When |
|---|---|
| 200 | Evaluated successfully (PASS → `IN_PROGRESS`/round 3, FAIL → `REJECTED`) |
| 400 | Empty answer, evaluation not found is **404** not 400 (see below), or evaluation status isn't `IN_PROGRESS` (e.g. already `REJECTED`/`COMPLETE`) |
| 404 | `evaluation_id` does not exist |
| 409 | `current_round != 2` (wrong round for this evaluation), or a canonical round-2 verdict already exists (duplicate submission) |
| 502 | Technical evaluation or next-question-generation agent returned invalid output |

Body on PASS is structurally identical to `/start`'s PASS body but with
`"round": 2` and `"next_round": 3`. Body on FAIL is identical in shape with
`"status": "REJECTED"`.

---

## `POST /round/3/answer?evaluation_id={id}`

Submits the candidate's behavioral answer and runs the behavioral
evaluation agent. **Does not** run the recommendation/committee agents —
those only run from `/final-decision`.

**Request body:** same `AnswerRequest` shape as round 2.

| Status | When |
|---|---|
| 200 | Evaluated (PASS/BORDERLINE → `status: "COMPLETE"` meaning *answer phase* complete, not the whole pipeline; FAIL → `REJECTED`) |
| 400 / 404 / 409 / 502 | Same semantics as round 2, but checked against round 3 |

Body on PASS/BORDERLINE:

```json
{
  "evaluation_id": 1,
  "round": 3,
  "decision": "PASS",
  "verdict": { "...": "full BehavioralVerdict object" },
  "verdict_text": "raw agent output",
  "status": "COMPLETE",
  "next": "/final-decision"
}
```

**Important nuance:** this response's `"status": "COMPLETE"` describes the
*answer-submission phase*, not the evaluation row's `status` column in the
database — the DB row's `status` stays `"IN_PROGRESS"` until
`/final-decision` actually runs the recommendation and committee agents and
sets `final_decision`. Don't confuse the two.

---

## `GET /final-decision?evaluation_id={id}`

Runs the Hiring Recommendation agent (round 4) and Committee Evaluator
(round 5), computes `overall_score`, and marks the evaluation `COMPLETE`.
**Idempotent**: calling it again after completion replays the persisted
result instead of re-invoking (and re-billing) the agents.

| Status | When |
|---|---|
| 200 | Success, replay, or early-rejected short-circuit (see below) |
| 202 | Finalization is queued or owned by another worker; retry after the `Retry-After` header |
| 400 | `current_round < 4` (rounds 1–3 not all finished yet) |
| 404 | `evaluation_id` does not exist |
| 409 | A round-4 or round-5 canonical verdict already exists but the evaluation isn't yet marked `COMPLETE` (a concurrent finalize is in flight) |
| 502 | Recommendation or committee agent returned invalid output |

Body if the evaluation was **already rejected** in an earlier round (short
circuit — recommendation/committee agents are never invoked):

```json
{
  "evaluation_id": 1,
  "decision": "REJECT",
  "verdict": {"decision": "REJECT", "reason": "Candidate was rejected in an earlier round."},
  "verdict_text": "Candidate was rejected in an earlier round.",
  "rationale": "Candidate was rejected in an earlier round.",
  "status": "REJECTED"
}
```

Body on a **fresh successful finalize** (captured from a live test run
against a real LLM, 2026-09-27):

```json
{
  "evaluation_id": 1,
  "decision": "HIRE",
  "verdict": { "...": "full CommitteeDecision object" },
  "verdict_text": "raw committee agent output",
  "rationale": "raw committee agent output",
  "recommendation": { "...": "full HiringRecommendation object" },
  "recommendation_text": "raw recommendation agent output",
  "overall_score": 8.2,
  "confidence": 0.93,
  "status": "COMPLETE"
}
```

`overall_score` is the average of **only** the round 1/2/3 scores — the
round 4 recommendation's own score is deliberately excluded because it
already synthesizes those three and would otherwise double-count in the
average (see `routes.py`'s `final_decision` handler comment).

Calling this endpoint again for the same, now-`COMPLETE` evaluation returns
the identical body (byte-for-byte `decision`/`overall_score`/`confidence`)
without re-running any agent — verified in
`backend/tests/test_routes.py::TestHappyPath::test_full_pipeline_reaches_hire`.

---

## `GET /roles`

Returns the fixed list of selectable roles.

```json
{"roles": ["SDE 1", "SDE 2", "Senior Software Engineer", "AI Engineer", "ML Engineer", "Backend Developer", "Frontend Developer", "Full-Stack Developer", "DevOps Engineer", "Data Scientist"]}
```

This list lives in `state.py`'s `AVAILABLE_ROLES` constant — it is not
configurable per-deployment or versioned as a rubric (see
[GAP_ANALYSIS.md](GAP_ANALYSIS.md) P3).

---

## `GET /status?evaluation_id={id}`

Lightweight status/poll endpoint, PII-safe (uses `get_evaluation_public`).

```json
{
  "evaluation_id": 1,
  "round": 5,
  "status": "COMPLETE",
  "role": "Backend Developer",
  "candidate_name": "Jane Doe",
  "verdicts": {"round1": true, "round2": true, "round3": true, "round4": true, "round5": true}
}
```

404 if `evaluation_id` does not exist. `verdicts.roundN` is `true` only if a
**canonical** (non-`INVALID_OUTPUT`) verdict exists for that round.

---

## `GET /evaluations`

List evaluations. **Never includes `resume_text`** (verified in
`backend/tests/test_routes.py::TestPiiSafety`).

Query params: `status` (optional filter), `limit` (1–100, default 50),
`offset` (default 0).

```json
{
  "evaluations": [
    {
      "id": 1, "candidate_name": "Jane Doe", "role": "Backend Developer",
      "status": "COMPLETE", "current_round": 5, "overall_score": 8.2,
      "final_decision": "HIRE", "created_at": "...", "updated_at": "...",
      "verdict_count": 5,
      "verdicts_summary": [
        {"agent_type": "screening", "round_number": 1, "decision": "PASS", "score": 9.0}
      ]
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

`verdicts_summary` for every listed evaluation is fetched in a **single
batched query** (`db.get_verdict_summaries`) rather than one query per
evaluation — this replaced an original N+1 query pattern (see
[CHANGELOG.md](CHANGELOG.md)).

---

## `GET /evaluations/{eval_id}`

Full verdict history for one evaluation (including `INVALID_OUTPUT` rows,
for audit purposes). **Never includes `resume_text`.**

```json
{
  "evaluation": { "...": "same shape as one item in GET /evaluations" },
  "verdicts": [
    {"id": 1, "evaluation_id": 1, "agent_type": "screening", "round_number": 1,
     "verdict_json": {"...": "full ScreeningVerdict"}, "verdict_text": "raw", "score": 9.0,
     "decision": "PASS", "confidence": 0.9, "created_at": "..."}
  ]
}
```

404 if not found.

---

## `GET /evaluations/{eval_id}/report`

Structured, per-stage pipeline view — used by the frontend result/dashboard
pages. **Never includes `resume_text`.**

```json
{
  "evaluation_id": 1, "candidate_name": "Jane Doe", "role": "Backend Developer",
  "status": "COMPLETE", "overall_score": 8.2, "final_decision": "HIRE",
  "pipeline": [
    {"stage": 1, "name": "Resume Screening", "agent": "Screening Agent",
     "status": "complete", "score": 9.0, "decision": "PASS", "verdict": {"...": "..."}},
    {"stage": 2, "...": "..."},
    {"stage": 3, "...": "..."},
    {"stage": 4, "name": "Hiring Recommendation", "agent": "Recommendation Agent",
     "status": "complete", "score": 8.5, "decision": "HIRE", "verdict": {"...": "..."}},
    {"stage": 5, "name": "Committee Decision", "agent": "Committee Evaluator",
     "status": "complete", "score": null, "decision": "HIRE", "verdict": {"...": "..."}}
  ],
  "verdicts": [ "...": "same as GET /evaluations/{eval_id} verdicts" ],
  "created_at": "...", "updated_at": "..."
}
```

Per-stage `status` values: `pending`, `active` (current round, evaluation
still `IN_PROGRESS`), `complete`, `failed` (canonical decision was
FAIL/REJECT), `agent_output_invalid` (only `INVALID_OUTPUT` rows exist for
that stage, no canonical verdict yet — surfaces the failure distinctly
instead of hiding it as `pending`).

---

## `GET /evaluations/{eval_id}/pipeline`

A slightly leaner, `PipelineStatus`-typed variant of the same per-stage
data (no `verdict` payload, no `verdict_json`) — returns a Pydantic-typed
response (`models.PipelineStatus`) rather than a raw dict.

---

## `GET /dashboard/stats`

Aggregate counters across **all** evaluations (no per-tenant scoping — see
[SECURITY.md](SECURITY.md)).

```json
{
  "total": 10, "completed": 6, "in_progress": 2, "rejected": 2,
  "hired": 4, "hire_rate": 66.7, "avg_score": 7.8
}
```

`hire_rate` is `hired / completed * 100` (0 if no completed evaluations).
`avg_score` is the mean of `overall_score` across all evaluations where it's
non-null (0 if none).

---

## `POST /reset`

Deprecated no-op retained only for backward compatibility with older
frontend builds that used to call a global session reset. Always returns
`{"status": "ok", "message": "No shared session state to reset."}`. There is
no shared session state left to reset (see [ARCHITECTURE.md](ARCHITECTURE.md)).

---

## `GET /`

Service metadata (name, version, agent list, endpoint list) — a
human-oriented landing response, not meant for programmatic use.
