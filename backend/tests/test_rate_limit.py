"""
Unit tests for rate_limit.InMemoryRateLimitMiddleware, in isolation from the
full application (no database, no agents, no crewai import — fast).
"""

import pytest
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import app.shared.rate_limit as rate_limit
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

    def test_window_expires_hits_after_the_configured_duration(self, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr(rate_limit, "monotonic", lambda: clock[0])
        client = TestClient(_make_app(requests_per_window=1, window_seconds=0.2))
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 429

        clock[0] += 0.2
        assert client.get("/ping").status_code == 200

    def test_rejects_non_positive_window_when_rate_limiting_is_enabled(self):
        with pytest.raises(ValueError, match="window_seconds must be positive"):
            InMemoryRateLimitMiddleware(Starlette(), requests_per_window=1, window_seconds=0)

    def test_retry_after_rounds_up_to_avoid_retrying_early(self, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr(rate_limit, "monotonic", lambda: clock[0])
        client = TestClient(_make_app(requests_per_window=1, window_seconds=60))
        assert client.get("/ping").status_code == 200

        clock[0] += 0.1
        blocked = client.get("/ping")

        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == "60"

    def test_hits_expire_at_the_exact_sliding_window_boundary(self, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr(rate_limit, "monotonic", lambda: clock[0])
        client = TestClient(_make_app(requests_per_window=2, window_seconds=10))
        assert client.get("/ping").status_code == 200
        clock[0] += 5
        assert client.get("/ping").status_code == 200

        clock[0] = 110.0
        assert client.get("/ping").status_code == 200

    def test_periodic_cleanup_removes_idle_client_buckets(self):
        middleware = InMemoryRateLimitMiddleware(
            Starlette(), requests_per_window=1, window_seconds=10
        )
        middleware._hits["198.51.100.1"].append(100.0)
        middleware._hits["198.51.100.2"].append(105.0)

        middleware._prune_expired_clients(window_start=102.0)

        assert "198.51.100.1" not in middleware._hits
        assert list(middleware._hits["198.51.100.2"]) == [105.0]

    def test_rate_limit_response_keeps_cors_headers(self):
        app = _make_app(requests_per_window=1, window_seconds=60)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://app.example.com"],
            allow_methods=["GET"],
            allow_headers=["*"],
        )
        client = TestClient(app)
        request_headers = {"Origin": "https://app.example.com"}

        assert client.get("/ping", headers=request_headers).status_code == 200
        blocked = client.get("/ping", headers=request_headers)

        assert blocked.status_code == 429
        assert blocked.headers["access-control-allow-origin"] == "https://app.example.com"
        assert blocked.headers["Retry-After"] == "60"

