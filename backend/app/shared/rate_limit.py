"""
Minimal in-memory per-client-IP rate limiting middleware.

Scope and honest limitations (see docs/SECURITY.md "Known gaps"):
  - This is a fixed-window counter held in a single process's memory. It
    stops the most basic single-instance abuse (e.g. a script hammering
    POST /start, which triggers a paid LLM call per request) without adding
    any external dependency (Redis, etc.).
  - It is NOT a substitute for a real distributed rate limiter once Evalia
    runs behind more than one worker process or instance — each process
    would enforce its own independent limit. It is also not a substitute
    for authentication/authorization or per-tenant spend budgets (see
    PRODUCTION_ROADMAP.md P1/T010, still open).
  - The window is a simple deque of monotonic timestamps per client IP, not
    a token bucket, so bursts exactly at the window boundary are possible.
    This is an accepted trade-off for simplicity over precision.
"""

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window request limiter, keyed by client IP.

    Set ``requests_per_window <= 0`` to disable the limiter entirely (used
    by the automated test suite, which exercises business logic, not this
    middleware).
    """

    def __init__(self, app, requests_per_window: int, window_seconds: int):
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if self.requests_per_window <= 0:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds
        hits = self._hits[client_ip]

        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self.requests_per_window:
            retry_after = max(1, int(self.window_seconds - (now - hits[0])))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down and try again shortly.",
                    "error_type": "rate_limit",
                },
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)
