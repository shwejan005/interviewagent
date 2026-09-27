"""
FastAPI Application Entry Point.

Evalia — Multi-Agent Interview Evaluation System
─────────────────────────────────────────────────
5 specialized CrewAI agents conduct a multi-stage interview evaluation.
Each round produces a structured verdict. The final committee agent
reviews all verdicts (without seeing the resume) and makes a hiring decision.

Pipeline:
  1. Screening Agent     — evaluates resume fit
  2. Technical Agent     — evaluates technical answers
  3. Behavioral Agent    — evaluates behavioral/STAR responses
  4. Recommendation Agent — synthesizes a hiring recommendation
  5. Committee Evaluator — makes final HIRE/HOLD/REJECT decision

Memory Architecture:
  1. SESSION CONTEXT  — in-memory (state.py)
  2. DECISION MEMORY  — flat files (verdicts/*.txt) + SQLite (database.py)
  3. AGENT CONTEXT    — explicit passing (crew_runner.py)
"""

import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Must run before importing routes/database — database.py reads DATABASE_URL
# at import time, so loading .env after that import would silently miss it.
load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.requests import Request  # noqa: E402

from routes import router  # noqa: E402
from database import init_db  # noqa: E402
from rate_limit import InMemoryRateLimitMiddleware  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Application Lifecycle ────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    logger.info("Initializing Evalia backend...")
    if not os.getenv("GEMINI_API_KEY"):
        logger.warning(
            "GEMINI_API_KEY is not set. Agent calls will fail until it is configured."
        )
    _validate_startup_config()
    init_db()
    logger.info("Database initialized.")
    yield
    # Shutdown
    logger.info("Shutting down Evalia backend.")


def _validate_startup_config() -> None:
    """Fail loudly (but not fatally) on configuration combinations that are
    silently insecure or inappropriate for a real deployment. This does not
    replace a full settings/validation layer (PRODUCTION_ROADMAP.md P1/T010
    remains open) — it catches the cheapest, highest-value mistakes.
    """
    app_env = os.getenv("APP_ENV", "development").strip().lower()

    if "*" in cors_origins:
        logger.warning(
            "CORS_ORIGINS includes '*' while allow_credentials=True. Browsers reject "
            "this combination outright, and it is not narrowed to trusted origins. "
            "Set CORS_ORIGINS to an explicit comma-separated allowlist."
        )

    if app_env == "production" and not os.getenv("DATABASE_URL", "").strip():
        logger.warning(
            "APP_ENV=production but DATABASE_URL is not set — falling back to a local "
            "SQLite file. SQLite has not been validated for concurrent multi-worker "
            "production use; set DATABASE_URL to a managed PostgreSQL instance."
        )

    if app_env == "production" and not os.getenv("GEMINI_API_KEY"):
        logger.warning(
            "APP_ENV=production but no GEMINI_API_KEY is set. Confirm agents.py is "
            "intentionally pointed at a non-Gemini provider (see LLM_MODEL in agents.py) "
            "before deploying — a hardcoded local-proxy override left in place would "
            "silently break in any environment where that proxy isn't reachable."
        )


app = FastAPI(
    title="Evalia — Multi-Agent Interview Evaluation System",
    description=(
        "A distributed interview evaluation pipeline comprising 5 autonomous AI agents "
        "for resume screening, technical assessment, behavioral evaluation, hiring "
        "recommendations, and an isolated committee decision."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


# ── Rate limiting ────────────────────────────────────────────────────
# Basic single-process abuse protection (e.g. a script hammering /start,
# which triggers a paid LLM call per request). Set RATE_LIMIT_REQUESTS=0 to
# disable. See rate_limit.py for scope and honest limitations.
#
# Registered BEFORE CORSMiddleware below: Starlette builds its middleware
# stack so the LAST-registered middleware ends up outermost. CORS must be
# outermost so that a response short-circuited by the rate limiter (e.g. a
# 429) still gets CORS headers attached — otherwise a browser client sees
# an opaque CORS failure instead of the actual 429 + Retry-After response.

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

app.add_middleware(
    InMemoryRateLimitMiddleware,
    requests_per_window=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)


# ── CORS ─────────────────────────────────────────────────────────────

cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handler ────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {error_msg}")

    # Detect rate-limit / quota errors from Gemini
    if "429" in error_msg or "quota" in error_msg.lower() or "rate" in error_msg.lower():
        return JSONResponse(
            status_code=429,
            content={
                "detail": "AI rate limit reached. Please wait a moment and try again.",
                "error_type": "rate_limit",
            },
        )

    # Never echo raw exception text to the client — it can leak internal
    # paths, queries, or provider error details. Full details are logged above.
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again."},
    )


# ── Routes ───────────────────────────────────────────────────────────

app.include_router(router)


@app.get("/")
async def root():
    return {
        "service": "Evalia — Multi-Agent Interview Evaluation System",
        "version": "2.0.0",
        "status": "running",
        "agents": [
            "Screening Agent",
            "Technical Agent",
            "Behavioral Agent",
            "Recommendation Agent",
            "Committee Evaluator",
        ],
        "endpoints": [
            "POST /start",
            "POST /round/2/answer",
            "POST /round/3/answer",
            "GET  /final-decision",
            "GET  /status",
            "GET  /roles",
            "GET  /evaluations",
            "GET  /evaluations/{id}",
            "GET  /evaluations/{id}/report",
            "GET  /evaluations/{id}/pipeline",
            "GET  /dashboard/stats",
        ],
    }
