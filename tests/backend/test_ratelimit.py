"""Tests for app.ratelimit — sliding-window rate limiter."""

from unittest.mock import AsyncMock, MagicMock


async def test_single_request_passes() -> None:
    """A single request under the limit is allowed through."""
    from app.ratelimit import RateLimitMiddleware

    request = MagicMock()
    request.url.path = "/api/weather/sensors"
    request.state.real_ip = "1.2.3.4"

    call_next = AsyncMock()
    call_next.return_value = MagicMock(status_code=200)

    middleware = RateLimitMiddleware(MagicMock())
    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200


async def test_rate_limit_exceeded() -> None:
    """Requests beyond the rate limit return 429."""
    from app.ratelimit import RATE_LIMIT, RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    ip = "5.6.7.8"
    for _ in range(RATE_LIMIT):
        request = MagicMock()
        request.url.path = "/api/weather/sensors"
        request.state.real_ip = ip
        call_next = AsyncMock()
        call_next.return_value = MagicMock(status_code=200)
        resp = await middleware.dispatch(request, call_next)
        assert resp.status_code == 200

    request = MagicMock()
    request.url.path = "/api/weather/sensors"
    request.state.real_ip = ip
    call_next = AsyncMock()
    resp = await middleware.dispatch(request, call_next)
    assert resp.status_code == 429
    call_next.assert_not_called()


async def test_rate_limit_returns_retry_after_header() -> None:
    """A 429 response includes a Retry-After header."""
    from app.ratelimit import RATE_LIMIT, RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    ip = "9.10.11.12"
    for _ in range(RATE_LIMIT):
        request = MagicMock()
        request.url.path = "/api/weather/sensors"
        request.state.real_ip = ip
        call_next = AsyncMock()
        call_next.return_value = MagicMock(status_code=200)
        await middleware.dispatch(request, call_next)

    request = MagicMock()
    request.url.path = "/api/weather/sensors"
    request.state.real_ip = ip
    call_next = AsyncMock()
    resp = await middleware.dispatch(request, call_next)
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "60"


async def test_websocket_path_bypasses_rate_limit() -> None:
    """The WebSocket endpoint is excluded from rate limiting."""
    from app.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    request = MagicMock()
    request.url.path = "/api/weather/ws"
    request.state.real_ip = "1.2.3.4"
    call_next = AsyncMock()
    call_next.return_value = MagicMock(status_code=200)

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200


async def test_different_ips_have_separate_windows() -> None:
    """Rate limit windows are isolated per IP address."""
    from app.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    def make_request(ip: str) -> MagicMock:
        req = MagicMock()
        req.url.path = "/api/weather/sensors"
        req.state.real_ip = ip
        return req

    ip_a = "10.0.0.1"
    ip_b = "10.0.0.2"

    for _ in range(100):
        call_next = AsyncMock()
        call_next.return_value = MagicMock(status_code=200)
        await middleware.dispatch(make_request(ip_a), call_next)

    call_next = AsyncMock()
    resp = await middleware.dispatch(make_request(ip_a), call_next)
    assert resp.status_code == 429

    call_next = AsyncMock()
    call_next.return_value = MagicMock(status_code=200)
    resp = await middleware.dispatch(make_request(ip_b), call_next)
    assert resp.status_code == 200


async def test_cleanup_removes_expired_entries() -> None:
    """The periodic cleanup removes stale IP entries from the window."""
    from app.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    request = MagicMock()
    request.url.path = "/api/weather/sensors"
    request.state.real_ip = "expired_ip"
    call_next = AsyncMock()
    call_next.return_value = MagicMock(status_code=200)

    await middleware.dispatch(request, call_next)

    assert "expired_ip" in middleware._windows

    import time

    old_time = time.monotonic() - 120
    middleware._windows["expired_ip"] = type(middleware._windows["expired_ip"])(
        [old_time]
    )

    for _ in range(99):
        other_req = MagicMock()
        other_req.url.path = "/api/weather/sensors"
        other_req.state.real_ip = "other"
        other_call = AsyncMock()
        other_call.return_value = MagicMock(status_code=200)
        await middleware.dispatch(other_req, other_call)

    trigger_req = MagicMock()
    trigger_req.url.path = "/api/weather/sensors"
    trigger_req.state.real_ip = "trigger"
    trigger_call = AsyncMock()
    trigger_call.return_value = MagicMock(status_code=200)
    await middleware.dispatch(trigger_req, trigger_call)

    assert "expired_ip" not in middleware._windows
