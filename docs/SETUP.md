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

- **Gemini (as documented/originally intended):** set `GEMINI_API_KEY` in
  `.env`, and in `backend/agents.py`, delete or comment out the second
  `LLM_MODEL = LLM(...)` assignment so the `gemini/gemini-2.5-flash` line
  takes effect. See [ARCHITECTURE.md](ARCHITECTURE.md#llm-provider-configuration).
- **Local OpenAI-compatible proxy (current default in this repo):** no
  `GEMINI_API_KEY` needed; the hardcoded `LLM(base_url="http://127.0.0.1:9999/v1", ...)`
  assignment in `agents.py` is what actually runs. You must have something
  listening on that port implementing the `/v1/chat/completions` wire
  format, or every agent call will fail with a connection error.

Database: leave `DATABASE_URL` unset for local SQLite (`backend/evalia.db`,
auto-created). Set it to a PostgreSQL connection string to use Postgres
instead (see `docker-compose.yml` for a local option, or `.env.example` for
managed-provider examples).

Run the server:

```powershell
cd backend
uvicorn main:app --reload --port 8000
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The dev server proxies `/api/*` to
`http://127.0.0.1:8000` by default (override with the `BACKEND_URL`
environment variable — see `next.config.js`).

### Known environment issue: `next build` and Google Fonts

`app/layout.tsx` uses `next/font/google`, which fetches font files from
`fonts.googleapis.com` **at build time**. In a network-restricted
environment (e.g. a sandboxed CI runner or an offline machine), `npm run
build` will hang/fail with `ECONNRESET` retrying that fetch indefinitely.
This is an environment limitation, not a code defect. Two ways to make
progress without full internet access:

- Type-check only: `npm run typecheck` (added in this documentation pass —
  runs `tsc --noEmit`, no network required).
- If you must run `next build` without reliable access to Google Fonts,
  switch `app/layout.tsx` to a locally-bundled font or `next/font/local`.
  This has not been done in this repository (out of scope for this
  documentation pass — see [GAP_ANALYSIS.md](GAP_ANALYSIS.md)).

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
# Backend — should show 38 passed, 0 failed (see docs/TESTING.md)
cd backend
pytest -v

# Frontend — should produce no output (success)
cd frontend
npm run typecheck
```
