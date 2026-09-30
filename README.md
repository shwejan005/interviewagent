# Evalia — Multi-Agent Interview Evaluation System

Evalia is a five-stage candidate evaluation pipeline built on **CrewAI**:
resume screening, a technical round, a behavioral round, a synthesized
hiring recommendation, and a final committee decision that is deliberately
isolated from the candidate's resume and raw answers to reduce
resume-based bias. Every agent's output is validated against a strict
Pydantic schema before it can become a business decision — malformed or
invalid LLM output is recorded as a distinct execution failure, never
silently turned into a PASS/FAIL/HIRE/REJECT verdict.

> **Full documentation lives in [`docs/`](docs/README.md).** This README is
> a short entry point; `docs/` has the complete, source-verified detail on
> architecture, the API contract, the database schema, setup, testing, and
> — importantly — an honest account of what is and isn't production-ready
> yet ([`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) and
> [`docs/SECURITY.md`](docs/SECURITY.md)).

## What this is (and isn't)

This is a working prototype with authenticated candidate/recruiter flows,
tenant-scoped marketplace data, durable interview admission, strict output
validation, PII-safe responses, idempotent finalization, and a database-driven
DSA preparation suite with sandboxed Judge0 execution for local development.
The project has an automated backend suite, frontend type-check/build gates,
real-Postgres RLS/concurrency verification, and Playwright recovery coverage.
It is **not production-certified**: cloud deployment, managed secrets, real
Postgres load/restore exercises, benchmark quality evidence, and a consented
pilot remain open. See [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) and
[`docs/SECURITY.md`](docs/SECURITY.md).

Two other documents at the repository root describe **planning**, not
current state: [`CODEBASE_REVIEW.md`](CODEBASE_REVIEW.md) (a prior
evidence-based review of bugs and gaps) and
[`PRODUCTION_ROADMAP.md`](PRODUCTION_ROADMAP.md) (a proposed multi-phase
plan to close them). [`docs/GAP_ANALYSIS.md`](docs/GAP_ANALYSIS.md) is the
up-to-date, task-by-task comparison of that roadmap against what has
actually been implemented.

## Architecture, in brief

```
Resume → Screening Agent → Technical Agent → Behavioral Agent → Recommendation Agent → Committee Evaluator
              ↓ recommendation/review state, not an unattended hiring decision
```

The Recommendation and Committee agents receive **only** prior agents'
structured verdicts — never the resume or raw candidate answers — by
explicit, function-argument-level context passing (no shared/global state).
See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full request
lifecycle, the LLM provider configuration (this repository currently points
at a local OpenAI-compatible proxy, not Gemini, by default — see that doc
before assuming otherwise), and exactly what this design does and doesn't
protect against.

- **Frontend:** Next.js 14 (App Router) + Tailwind CSS
- **Backend:** FastAPI (Python 3.11) + Pydantic v2
- **Agent framework:** CrewAI
- **Persistence:** PostgreSQL (when `DATABASE_URL` is set) or local SQLite
  (fallback) — see [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)

## Project structure

## Local demo data

The default `DATABASE_URL=` setting uses SQLite at `backend/evalia.db`. Seed a
complete local workspace with demo recruiter, candidate, job, application, and
evaluation records by running this from the repository root:

```powershell
python backend/seed_demo.py
```

The command is idempotent and refuses to run when `DATABASE_URL` points to
PostgreSQL. It prints the demo login emails and shared development password.
The seeded workspace includes two recruiter accounts, four candidate accounts,
eight published jobs, one draft job, and applications in several pipeline
stages. All demo accounts use `EvaliaDemo2026!`.

```
interviewagent/
├── backend/
│   ├── main.py              # FastAPI entry point, CORS, rate limiting, startup validation
│   ├── routes.py            # API endpoints — orchestration only, no decision logic
│   ├── database.py          # PostgreSQL/SQLite persistence layer
│   ├── models.py            # Pydantic schemas (strict enums, bounded fields)
│   ├── agents.py            # 5 CrewAI agent definitions + LLM provider config
│   ├── tasks.py             # Per-round prompt/task definitions
│   ├── crew_runner.py       # Orchestration, output parsing/validation
│   ├── state.py             # Static constants + per-evaluation verdict paths
│   ├── rate_limit.py        # Basic in-memory per-IP rate limiting middleware
│   ├── tests/                # pytest suite — see docs/TESTING.md
│   ├── verdicts/             # Per-evaluation decision-memory files (gitignored)
│   └── requirements.txt / requirements-dev.txt
├── frontend/
│   └── app/                  # interview/, round/[id]/, result/, dashboard/, etc.
├── docs/                     # Full documentation set — start at docs/README.md
└── .github/workflows/ci.yml  # Backend tests + frontend type-check on every PR
```

## Quick start

Full instructions (including environment variables, Windows-specific
notes, and known environment gotchas) are in
[`docs/SETUP.md`](docs/SETUP.md). Short version:

```powershell
# Backend
cd backend
pip install -r requirements.txt
# copy ../.env.example to ../.env and configure GEMINI_API_KEY or your LLM provider
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Running the tests

```powershell
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest -v

cd ../frontend
npm run typecheck
```

Both are run on every push/PR via `.github/workflows/ci.yml`. See
[`docs/TESTING.md`](docs/TESTING.md) for what is and isn't covered.

## API summary

See [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) for the complete,
field-by-field contract (request/response shapes, every status code and
when it occurs). Endpoints at a glance:

| Method | Endpoint | Purpose |
|--------|----------|-------------|
| `POST` | `/start` | Create an evaluation, run screening (+ generate technical questions on PASS) |
| `POST` | `/round/2/answer` | Submit + evaluate the technical answer |
| `POST` | `/round/3/answer` | Submit + evaluate the behavioral answer |
| `GET`  | `/final-decision` | Run recommendation + committee agents; idempotent |
| `GET`  | `/status` | Lightweight per-evaluation status poll |
| `GET`  | `/roles` | List selectable target roles |
| `GET`  | `/evaluations` | List evaluations (PII-safe, paginated) |
| `GET`  | `/evaluations/{id}` | Full verdict history for one evaluation (PII-safe) |
| `GET`  | `/evaluations/{id}/report` | Structured per-stage pipeline report |
| `GET`  | `/dashboard/stats` | Aggregate counters across all evaluations |

## License

MIT
