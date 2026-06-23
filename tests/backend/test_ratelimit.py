"""Tests for app.ratelimit — sliding-window rate limiter."""

from unittest.mock import AsyncMock, MagicMock


async def test_single_request_passes() -> None:
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
    from app.ratelimit import RATE_LIMIT, RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    # Saturate the rate limit
    ip = "5.6.7.8"
    for _ in range(RATE_LIMIT):
        request = MagicMock()
        request.url.path = "/api/weather/sensors"
        request.state.real_ip = ip
        call_next = AsyncMock()
        call_next.return_value = MagicMock(status_code=200)
        resp = await middleware.dispatch(request, call_next)
        assert resp.status_code == 200

    # One more should be rejected
    request = MagicMock()
    request.url.path = "/api/weather/sensors"
    request.state.real_ip = ip
    call_next = AsyncMock()
    resp = await middleware.dispatch(request, call_next)
    assert resp.status_code == 429
    call_next.assert_not_called()


async def test_rate_limit_returns_retry_after_header() -> None:
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
    from app.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    def make_request(ip: str) -> MagicMock:
        req = MagicMock()
        req.url.path = "/api/weather/sensors"
        req.state.real_ip = ip
        return req

    # Saturate ip_a
    ip_a = "10.0.0.1"
    ip_b = "10.0.0.2"

    for _ in range(100):
        call_next = AsyncMock()
        call_next.return_value = MagicMock(status_code=200)
        await middleware.dispatch(make_request(ip_a), call_next)

    # ip_a should be limited now
    call_next = AsyncMock()
    resp = await middleware.dispatch(make_request(ip_a), call_next)
    assert resp.status_code == 429

    # ip_b should still pass
    call_next = AsyncMock()
    call_next.return_value = MagicMock(status_code=200)
    resp = await middleware.dispatch(make_request(ip_b), call_next)
    assert resp.status_code == 200


async def test_cleanup_removes_expired_entries() -> None:
    from app.ratelimit import RateLimitMiddleware

    middleware = RateLimitMiddleware(MagicMock())

    request = MagicMock()
    request.url.path = "/api/weather/sensors"
    request.state.real_ip = "expired_ip"
    call_next = AsyncMock()
    call_next.return_value = MagicMock(status_code=200)

    await middleware.dispatch(request, call_next)

    assert "expired_ip" in middleware._windows

    # Simulate time passing by manipulating the window directly
    import time

    old_time = time.monotonic() - 120  # older than window
    middleware._windows["expired_ip"] = type(middleware._windows["expired_ip"])(
        [old_time]
    )

    # Force cleanup via request count
    for _ in range(99):
        other_req = MagicMock()
        other_req.url.path = "/api/weather/sensors"
        other_req.state.real_ip = "other"
        other_call = AsyncMock()
        other_call.return_value = MagicMock(status_code=200)
        await middleware.dispatch(other_req, other_call)

    # 100th request triggers cleanup
    trigger_req = MagicMock()
    trigger_req.url.path = "/api/weather/sensors"
    trigger_req.state.real_ip = "trigger"
    trigger_call = AsyncMock()
    trigger_call.return_value = MagicMock(status_code=200)
    await middleware.dispatch(trigger_req, trigger_call)

    assert "expired_ip" not in middleware._windows
