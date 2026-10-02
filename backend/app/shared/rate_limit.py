"""
Minimal in-memory sliding-window per-client-IP rate limiting middleware.

Scope and honest limitations (see docs/SECURITY.md "Known gaps"):
    - This is a sliding-window log held in a single process's memory. It
    stops the most basic single-instance abuse (e.g. a script hammering
    POST /start, which triggers a paid LLM call per request) without adding
    any external dependency (Redis, etc.).
  - It is NOT a substitute for a real distributed rate limiter once Evalia
    runs behind more than one worker process or instance — each process
    would enforce its own independent limit. It is also not a substitute
    for authentication/authorization or per-tenant spend budgets (see
    PRODUCTION_ROADMAP.md P1/T010, still open).
    - The window is a simple deque of monotonic timestamps per client IP, not
        a token bucket. A client can still make its full allowance in a short
        burst; this is an accepted trade-off for simplicity.
"""

from collections import defaultdict, deque
from math import ceil
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window request limiter, keyed by client IP.

    Set ``requests_per_window <= 0`` to disable the limiter entirely (used
    by the automated test suite, which exercises business logic, not this
    middleware).
    """

    _CLEANUP_INTERVAL = 256

    def __init__(self, app, requests_per_window: int, window_seconds: float):
        if requests_per_window > 0 and window_seconds <= 0:
            raise ValueError(
                "window_seconds must be positive when rate limiting is enabled"
            )
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._requests_until_cleanup = self._CLEANUP_INTERVAL

    def _prune_expired_clients(self, window_start: float) -> None:
        """Discard stale IP buckets, including clients that never return."""
        expired_clients = []
        for client_ip, client_hits in self._hits.items():
            while client_hits and client_hits[0] <= window_start:
                client_hits.popleft()
            if not client_hits:
                expired_clients.append(client_ip)
        for client_ip in expired_clients:
            self._hits.pop(client_ip, None)

    async def dispatch(self, request: Request, call_next):
        if self.requests_per_window <= 0:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = monotonic()
        window_start = now - self.window_seconds
        self._requests_until_cleanup -= 1
        if self._requests_until_cleanup <= 0:
            self._prune_expired_clients(window_start)
            self._requests_until_cleanup = self._CLEANUP_INTERVAL

        hits = self._hits[client_ip]

        while hits and hits[0] <= window_start:
            hits.popleft()

        if len(hits) >= self.requests_per_window:
            retry_after = max(1, ceil(self.window_seconds - (now - hits[0])))
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
