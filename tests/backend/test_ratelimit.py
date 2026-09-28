"""Tests for app.ratelimit — client-IP resolution and sliding-window limiter."""

import time
from collections import deque

import pytest
from httpx import ASGITransport, AsyncClient

API_PATH = "/api/weather/sensors"


@pytest.fixture
async def limiter():
    """RateLimitMiddleware around an app that records scopes; plus a client."""
    from app.ratelimit import RateLimitMiddleware  # ty: ignore[unresolved-import]
    from starlette.responses import PlainTextResponse

    seen: list[dict] = []

    async def inner(scope, receive, send) -> None:
        seen.append(scope)
        if scope["type"] == "http":
            await PlainTextResponse("ok")(scope, receive, send)

    middleware = RateLimitMiddleware(inner)
    transport = ASGITransport(app=middleware)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def hit(ip: str, path: str = API_PATH) -> int:
            resp = await client.get(path, headers={"Cf-Connecting-IP": ip})
            return resp.status_code

        yield middleware, client, hit, seen


async def test_single_request_passes_and_sets_real_ip(limiter) -> None:
    """A request under the limit reaches the app with the Cloudflare client IP."""
    _middleware, _client, hit, seen = limiter

    assert await hit("1.2.3.4") == 200
    assert seen[0]["state"]["real_ip"] == "1.2.3.4"


async def test_real_ip_falls_back_to_socket_peer(limiter) -> None:
    """Without Cf-Connecting-IP the socket peer address is the key."""
    middleware, client, _hit, seen = limiter

    resp = await client.get(API_PATH)

    assert resp.status_code == 200
    assert seen[0]["state"]["real_ip"] == "127.0.0.1"  # httpx ASGITransport client
    assert list(middleware._windows) == ["127.0.0.1"]


def test_client_ip_without_client_is_unknown() -> None:
    """A scope without a peer address (e.g. a unix socket) is keyed as unknown."""
    from app.ratelimit import client_ip  # ty: ignore[unresolved-import]

    assert client_ip({"type": "http", "headers": [], "client": None}) == "unknown"


async def test_rate_limit_exceeded_returns_429_with_retry_after(limiter) -> None:
    """Requests beyond the limit get 429 + Retry-After and never reach the app."""
    from app.ratelimit import RATE_LIMIT  # ty: ignore[unresolved-import]

    _middleware, client, hit, seen = limiter
    for _ in range(RATE_LIMIT):
        assert await hit("5.6.7.8") == 200

    resp = await client.get(API_PATH, headers={"Cf-Connecting-IP": "5.6.7.8"})

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"
    assert resp.json() == {"detail": "Too many requests — try again later."}
    assert len(seen) == RATE_LIMIT


@pytest.mark.parametrize("path", ["/", "/index.html", "/style.css", "/health"])
async def test_non_api_path_bypasses_rate_limit(limiter, path) -> None:
    """Paths outside /api/ pass through without consuming the window."""
    middleware, _client, hit, _seen = limiter

    assert await hit("1.2.3.4", path) == 200
    assert "1.2.3.4" not in middleware._windows


async def test_non_http_scope_passes_through_untouched(limiter) -> None:
    """WebSocket (and lifespan) scopes are forwarded without state or counting."""
    middleware, _client, _hit, seen = limiter
    scope = {"type": "websocket", "path": API_PATH, "headers": []}

    async def receive() -> dict:
        return {}

    async def send(_message: dict) -> None:
        pass

    await middleware(scope, receive, send)

    assert seen == [{"type": "websocket", "path": API_PATH, "headers": []}]
    assert not middleware._windows


async def test_different_ips_have_separate_windows(limiter) -> None:
    """Rate limit windows are isolated per IP address."""
    from app.ratelimit import RATE_LIMIT  # ty: ignore[unresolved-import]

    _middleware, _client, hit, _seen = limiter
    for _ in range(RATE_LIMIT):
        await hit("10.0.0.1")

    assert await hit("10.0.0.1") == 429
    assert await hit("10.0.0.2") == 200


async def test_cleanup_removes_expired_entries(limiter) -> None:
    """Every CLEANUP_EVERY counted requests, idle IP entries are dropped."""
    from app.ratelimit import CLEANUP_EVERY  # ty: ignore[unresolved-import]

    middleware, _client, hit, _seen = limiter
    await hit("expired_ip")
    middleware._windows["expired_ip"] = deque([time.monotonic() - 120])

    for _ in range(CLEANUP_EVERY - 2):
        await hit("other")
    assert "expired_ip" in middleware._windows
    await hit("trigger")

    assert "expired_ip" not in middleware._windows
    assert set(middleware._windows) == {"other", "trigger"}


async def test_tracked_ips_are_capped_with_lru_eviction(limiter, monkeypatch) -> None:
    """Beyond MAX_TRACKED_IPS the least recently seen key is dropped, not the newest."""
    from app import ratelimit  # ty: ignore[unresolved-import]

    monkeypatch.setattr(ratelimit, "MAX_TRACKED_IPS", 3)
    middleware, _client, hit, _seen = limiter

    for ip in ("a", "b", "c"):
        await hit(ip)
    await hit("a")  # "a" becomes the most recently seen; "b" is now the oldest
    await hit("d")

    assert list(middleware._windows) == ["c", "a", "d"]


async def test_expired_hits_leave_the_window_on_next_request(limiter) -> None:
    """Hits older than WINDOW_SECONDS are pruned, so a full window admits again."""
    from app import ratelimit  # ty: ignore[unresolved-import]

    middleware, _client, hit, _seen = limiter
    stale = time.monotonic() - ratelimit.WINDOW_SECONDS - 1
    middleware._windows["1.2.3.4"] = deque([stale] * ratelimit.RATE_LIMIT)

    assert await hit("1.2.3.4") == 200
    assert len(middleware._windows["1.2.3.4"]) == 1  # only the fresh hit remains
