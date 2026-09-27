# API reference

Base URL: the FastAPI app root (`http://127.0.0.1:8000` in local dev, or
whatever `BACKEND_URL` points the frontend's `/api/*` proxy at — see
[ARCHITECTURE.md](ARCHITECTURE.md)). All request/response bodies are JSON
unless noted. **No endpoint requires authentication** — see
[SECURITY.md](SECURITY.md).

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

---

## `POST /start`

Creates a new evaluation and runs round 1 (screening), and — if the
candidate passes — generates round 2's technical questions in the same
call.

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
