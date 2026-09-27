# Deployment

## What exists today

| Artifact | Purpose | Status |
|---|---|---|
| `dev.sh` | Local launcher — starts backend (`uvicorn`) and frontend (`next dev`) together | POSIX-only (assumes a `venv`/`.venv` at a specific relative path and a `source ... /activate` shell). Not verified on Windows in this pass. |
| `docker-compose.yml` | Local PostgreSQL container for development | Provides Postgres only — does not containerize the backend or frontend themselves. |
| `frontend/vercel.json` | Vercel hosting configuration for the Next.js app | Frontend-only; assumes the backend is reachable at whatever `BACKEND_URL` Vercel's environment is configured with. |
| `.github/workflows/ci.yml` (added this pass) | Runs backend pytest + frontend `tsc --noEmit` on every push/PR | **Test/type-check only.** Does not build a deployable artifact, does not deploy anything, does not run against real PostgreSQL. |

There is **no backend deployment definition** (no Dockerfile, no ECS/Fargate
task definition, no Kubernetes manifest, no other IaC) anywhere in this
repository. `PRODUCTION_ROADMAP.md` section 4 recommends "Next.js on
Vercel, API + worker on AWS ECS/Fargate, managed Postgres" as a pragmatic
first shape — none of that AWS-side infrastructure has been created.

## Environment variables that affect runtime behavior

See `.env.example` for the full list with descriptions. The ones that
materially change behavior:

| Variable | Effect |
|---|---|
| `GEMINI_API_KEY` | Required if `agents.py`'s Gemini `LLM_MODEL` assignment is the one actually in effect (see [ARCHITECTURE.md](ARCHITECTURE.md)). Currently overridden by a hardcoded local-proxy assignment in this repo's checked-in `agents.py` — confirm which one is active before deploying anywhere. |
| `DATABASE_URL` | Unset → SQLite file fallback (`backend/evalia.db`) — **not validated for concurrent multi-worker production use**. Set → PostgreSQL via a pooled `psycopg2` connection. |
| `CORS_ORIGINS` | Comma-separated allowlist. Defaults to `localhost:3000`/`127.0.0.1:3000` only. |
| `APP_ENV` | `production` enables extra startup warnings (SQLite fallback, missing `GEMINI_API_KEY`, insecure CORS) — added this pass. Does not change any other runtime behavior (it does not, for example, disable API docs or change log verbosity). |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | Basic in-memory per-IP rate limiting — added this pass. `RATE_LIMIT_REQUESTS=0` disables it. See [SECURITY.md](SECURITY.md) for scope/limits. |

## What's missing before a real production deployment

This list is deliberately blunt — it is the honest complement to
[GAP_ANALYSIS.md](GAP_ANALYSIS.md)'s P6 section:

1. **No authentication/authorization** — do not deploy this to a publicly
   reachable address without putting a separate access-control layer in
   front of it (VPN, reverse-proxy basic auth, IP allowlist, or an actual
   auth integration).
2. **No containerization of the backend** — you would need to write a
   Dockerfile (or equivalent) and test it; none exists.
3. **No production-grade database validation** — the automated test suite
   runs against SQLite only; PostgreSQL concurrency/contract behavior has
   only been exercised manually, not continuously tested (see
   [TESTING.md](TESTING.md)).
4. **No secrets management integration** — `.env`/environment variables
   only; no integration with a secrets manager (AWS Secrets Manager,
   Vault, etc.).
5. **No health/readiness probes** — only `GET /` (informational) exists;
   there's no `/healthz`/`/readyz` distinguishing "process is up" from
   "database is reachable and the app is ready to serve traffic."
6. **No backup/restore procedure has been exercised** for whichever
   PostgreSQL provider is chosen.
7. **The rate limiter is single-process only** — running more than one
   backend instance/worker behind a load balancer means each instance
   enforces its own independent limit, not a shared one (see
   [SECURITY.md](SECURITY.md)).
8. **`next build` requires outbound network access** (Google Fonts fetch at
   build time) — confirm your build environment/CI runner has it, or switch
   to a locally bundled font first (see [SETUP.md](SETUP.md)).

## Recommended immediate next step

Before attempting any real deployment, decide and document (per
`PRODUCTION_ROADMAP.md` section 14, "Decisions to confirm before
implementation"): who the first real user is, what data-retention rules
apply, which existing database/auth/cloud accounts must be preserved, and
what monthly cloud/model budget exists. None of these are technical
questions this documentation pass can answer on your behalf.
