# Setup guide

## Prerequisites

- Python 3.11 (the repo's `.python-version`/`backend/.python-version` pins
  `3.11.12`; `3.11.9` has also been used successfully for this
  documentation/testing pass — any 3.11.x has worked in practice).
- Node.js 18+ (Next.js 14 requirement).
- Optionally: Docker, if you want a local PostgreSQL instead of the SQLite
  fallback (`docker-compose.yml` at the repo root).

## Backend

```powershell
cd backend
python -m venv ../.venv        # or your preferred venv location
../.venv/Scripts/Activate.ps1  # Windows PowerShell; use `source ../.venv/bin/activate` on POSIX
pip install -r requirements.txt
```

For running tests or contributing, also install dev dependencies:

```powershell
pip install -r requirements-dev.txt
```

Copy the environment template and fill in what you need:

```powershell
Copy-Item ../.env.example ../.env
```

At minimum, decide which LLM provider you're using:

- **Gemini (default):** set `GEMINI_API_KEY` in `.env`; the default model is
  `gemini/gemini-2.5-flash`.
- **OpenAI-compatible endpoint:** set `AGENT_BASE_URL` and `AGENT_MODEL`, and
  set `AGENT_API_KEY` if the endpoint requires a key. `AGENT_MODEL` alone can
  select a different Gemini model when `AGENT_BASE_URL` is unset. API and
  worker processes must be able to reach the configured endpoint; `localhost`
  inside a container refers to that container, not the developer host.

The application-linked screening and interview assessor use the configured
CrewAI provider in the durable worker. AI-interview integration tests replace
these calls with deterministic fakes; no real provider call is required for
the test suite. Do not send real candidate data until the provider's retention,
training, residency, access, and data-processing terms have been reviewed.

Database: leave `DATABASE_URL` unset for local SQLite (`backend/evalia.db`,
auto-created). Set it to a PostgreSQL connection string to use Postgres
instead (see `docker-compose.yml` for a local option, or `.env.example` for
managed-provider examples).

Run the server:

```powershell
cd backend
../.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

generation, and interview-ready email notifications also require the durable
The durable command API is available under `/v1` when a worker is running.
Automatic application screening, interview-answer assessment, report
generation, invitation reminders/expiry, recruiter report notifications,
end-of-day digests, and human-interview notifications require the durable
worker. Start it in a second backend terminal:

```powershell
cd backend
../.venv/Scripts/python.exe -m app.worker.job_worker
```

Applications are screened automatically against recruiter-defined posting
criteria. Candidates who pass see an AI interview invitation in `/interviews`
with a Join action and expiry window. The AI interview presents questions as
text and uses browser speech recognition for spoken answers, with live captions
and a text accommodation path. The recruiter receives an evidence report and
an advisory fit nudge; the human decision remains explicit. Speech recognition
availability/retention depends on the candidate's browser and its provider; no
audio recording is stored by Evalia.

Scheduled human rounds use an in-app peer-to-peer WebRTC room at
`/meeting/{interviewId}`. The FastAPI backend relays room signaling; audio/video
media is exchanged directly between browsers. Configure
`NEXT_PUBLIC_BACKEND_WS_URL` in the frontend deployment to the backend's
WebSocket origin (for example `ws://127.0.0.1:8000` locally or `wss://...` in
production). The development fallback uses the page hostname on port 8000.
Without `TURN_URLS` and `TURN_SHARED_SECRET`, the room falls back to STUN only,
so restrictive corporate firewalls/NATs may prevent a direct connection. For
production, configure a coturn-compatible service with REST/HMAC authentication
and set both backend-only variables in `.env` or a secret store. The API returns
credentials bound to the user and room that expire after 10 minutes; never put
the shared secret in a `NEXT_PUBLIC_*` variable. Signaling remains process-local,
so multi-worker hosting needs sticky routing or a shared signaling service. The
AI round is a single-candidate voice/text interview UI, not a LiveKit/SFU room;
speech recognition runs in the candidate browser and model inference in the
configured backend. Email is optional: in-app notifications and the interview
agenda remain the source of truth.

The legacy interview routes remain available for compatibility. New clients
that need process-loss recovery should use `POST /v1/evaluations`,
`POST /v1/evaluations/{id}/answers`, and
`POST /v1/evaluations/{id}/finalize`.

Use the venv's `python.exe` explicitly (`-m uvicorn`) rather than a bare
`uvicorn` command. If another Python install on `PATH` also has `uvicorn`
installed (e.g. a prior `pip install --user uvicorn`), a bare `uvicorn`
command can silently resolve to *that* install instead of the venv — it
still launches, but immediately fails with `ModuleNotFoundError: No module
named 'crewai'` because the dependencies were installed into the venv, not
into whichever Python actually has `uvicorn` on `PATH`. Confirm with
`where uvicorn` (or `Get-Command uvicorn -All` in PowerShell) if this
happens — the venv's activation script is supposed to shadow `PATH`
correctly, but a fresh terminal that skipped the `Activate.ps1` step, or a
second `uvicorn` install ahead of the venv on `PATH`, will hit this.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The dev server proxies `/api/*` to
`http://127.0.0.1:8000` by default (override with the `BACKEND_URL`
environment variable — see `next.config.js`).

`npm run dev` uses Turbopack for fast incremental route compilation.
Next.js 14.2 still labels Turbopack as beta; if Fast Refresh becomes
unreliable on a particular machine, compare the stable Webpack server with
`npm run dev:webpack`. Stop and restart the dev process after changing modes.
Playwright uses a separate `.next-playwright` output directory so its server
on port 3100 cannot overwrite the live dev server's `.next` files. Avoid
running two Next dev servers against the same output directory.

Candidate preparation is available at `/prep`. It currently provides a
curated text-first topic/problem catalog, deterministic roadmaps, progress,
and unverified practice submissions. It does not execute submitted code.

### Production build and performance checks

The current `app/layout.tsx` uses the system font stack from
`app/globals.css`; it does not import `next/font/google` or fetch Google Fonts
at build time. The earlier Google Fonts warning was stale and has been
removed. Development mode compiles routes on demand and is not a production
performance measurement. To check production behavior, run `npm run build`
and then `npm run start`; set `BACKEND_URL` to the backend you intend to use.

### `npx tsc` gotcha

Do not run a bare `npx tsc` in this project. It has been observed (in this
exact environment) to ignore the locally installed `typescript`
devDependency and instead prompt to install an unrelated npm package
literally named `tsc` (`tsc@2.0.4`, an unmaintained package with nothing to
do with TypeScript). Always use `npm run typecheck`, or call the local
binary directly: `./node_modules/.bin/tsc --noEmit -p tsconfig.json` (POSIX)
/ `.\node_modules\.bin\tsc --noEmit -p tsconfig.json` (Windows PowerShell).

## Running everything at once

`dev.sh` at the repo root starts both backend and frontend together. It
assumes a POSIX shell and a `venv`/`.venv` at a specific relative path — it
has not been verified on Windows in this documentation pass; on Windows,
run the backend and frontend commands above in two separate terminals
instead.

## Verifying your setup

```powershell
# Backend — should show the current passing count (see docs/TESTING.md)
cd backend
../.venv/Scripts/python.exe -m pytest -v

# Frontend — should produce no output (success)
cd frontend
npm run typecheck
```

## Local Docker stack

```powershell
docker compose up --build
```

This starts PostgreSQL and the backend on `http://localhost:8000`. The
frontend remains a separate Next.js process; set `BACKEND_URL` if it is not
using the default local backend address.
