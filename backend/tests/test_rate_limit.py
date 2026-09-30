"""
Unit tests for rate_limit.InMemoryRateLimitMiddleware, in isolation from the
full application (no database, no agents, no crewai import — fast).
"""

import time

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.shared.rate_limit import InMemoryRateLimitMiddleware


async def _ping(request):
    return PlainTextResponse("ok")


def _make_app(requests_per_window: int, window_seconds: float):
    app = Starlette(routes=[Route("/ping", _ping)])
    app.add_middleware(
        InMemoryRateLimitMiddleware,
        requests_per_window=requests_per_window,
        window_seconds=window_seconds,
    )
    return app


class TestRateLimitMiddleware:
    def test_allows_requests_under_the_limit(self):
        client = TestClient(_make_app(requests_per_window=3, window_seconds=60))
        for _ in range(3):
            resp = client.get("/ping")
            assert resp.status_code == 200

    def test_blocks_requests_over_the_limit_with_429_and_retry_after(self):
        client = TestClient(_make_app(requests_per_window=2, window_seconds=60))
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 200

        blocked = client.get("/ping")
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert blocked.json()["error_type"] == "rate_limit"

    def test_disabled_when_requests_per_window_is_zero(self):
        client = TestClient(_make_app(requests_per_window=0, window_seconds=60))
        for _ in range(20):
            assert client.get("/ping").status_code == 200

    def test_window_resets_after_it_elapses(self):
        client = TestClient(_make_app(requests_per_window=1, window_seconds=0.2))
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 429

        time.sleep(0.3)
        assert client.get("/ping").status_code == 200

