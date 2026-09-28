"""Tests for app.main — app setup, middleware, lifecycle."""

from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time


async def test_cloudflare_ip_middleware_sets_real_ip(
    async_client,
) -> None:
    """The CloudflareIP middleware sets real_ip from Cf-Connecting-IP header."""
    resp = await async_client.get(
        "/api/weather/sensors",
        headers={"Cf-Connecting-IP": "203.0.113.1"},
    )
    assert resp.status_code == 200


async def test_rate_limit_is_keyed_by_cloudflare_ip(async_client) -> None:
    """Through the real stack, the limiter sees Cf-Connecting-IP per client."""
    from app.ratelimit import RATE_LIMIT  # ty: ignore[unresolved-import]

    ip_a = {"Cf-Connecting-IP": "198.51.100.1"}
    ip_b = {"Cf-Connecting-IP": "198.51.100.2"}

    for _ in range(RATE_LIMIT):
        resp = await async_client.get("/api/weather/sensors", headers=ip_a)
        assert resp.status_code == 200

    resp = await async_client.get("/api/weather/sensors", headers=ip_a)
    assert resp.status_code == 429

    resp = await async_client.get("/api/weather/sensors", headers=ip_b)
    assert resp.status_code == 200


async def test_rate_limit_skips_static_paths(async_client) -> None:
    """An exhausted API budget does not block the frontend's static files."""
    from app.ratelimit import RATE_LIMIT  # ty: ignore[unresolved-import]

    ip = {"Cf-Connecting-IP": "198.51.100.3"}
    for _ in range(RATE_LIMIT):
        await async_client.get("/api/weather/sensors", headers=ip)
    resp = await async_client.get("/api/weather/sensors", headers=ip)
    assert resp.status_code == 429

    resp = await async_client.get("/", headers=ip)
    assert resp.status_code == 200
    resp = await async_client.get("/health", headers=ip)
    assert resp.status_code == 200


async def test_csp_middleware_adds_header(async_client) -> None:
    """Every response includes a Content-Security-Policy header."""
    resp = await async_client.get("/api/weather/sensors")
    assert "Content-Security-Policy" in resp.headers
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self';" in csp  # Chart.js is vendored, no CDN host
    assert "jsdelivr" not in csp


async def test_cors_middleware_allows_origins(async_client) -> None:
    """CORS preflight requests from allowed origins succeed."""
    resp = await async_client.options(
        "/api/weather/sensors",
        headers={
            "Origin": "http://127.0.0.1:8332",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:8332"


@pytest.fixture
def cleanup_env(monkeypatch, db_engine):
    """Bind cleanup_old_readings to the test DB and stop the loop after N sleeps."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.main.SessionLocal", session_factory)
    sleeps: list[float] = []

    def stop_after(n: int) -> None:
        async def mock_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) >= n:
                msg = "break loop"
                raise asyncio.CancelledError(msg)

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    return session_factory, sleeps, stop_after


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
@pytest.mark.parametrize(
    ("age_days", "expected_remaining"),
    [(0, 1), (1, 1), (29, 1), (30, 1), (31, 0)],
)
async def test_cleanup_old_readings(cleanup_env, age_days, expected_remaining) -> None:
    """Cleanup runs before the first sleep; only readings older than 30 days go."""
    import asyncio
    from contextlib import suppress

    from app.main import (  # ty: ignore[unresolved-import]
        CLEANUP_INTERVAL_SECONDS,
        cleanup_old_readings,
    )
    from app.models import WeatherReading  # ty: ignore[unresolved-import]
    from sqlalchemy import select

    session_factory, sleeps, stop_after = cleanup_env
    stop_after(1)

    async with session_factory() as session:
        session.add(
            WeatherReading(
                parameter="temperature",
                value=22.0,
                unit="°C",
                timestamp=datetime.now(UTC) - timedelta(days=age_days),
            )
        )
        await session.commit()

    with suppress(asyncio.CancelledError):
        await cleanup_old_readings()

    assert sleeps == [CLEANUP_INTERVAL_SECONDS]
    async with session_factory() as session:
        remaining = (await session.execute(select(WeatherReading))).scalars().all()
        assert len(remaining) == expected_remaining


async def test_cleanup_survives_a_failing_cycle(
    cleanup_env, monkeypatch, caplog
) -> None:
    """A DB error in one cycle is logged and the loop keeps going."""
    import asyncio
    from contextlib import suppress

    from app.main import cleanup_old_readings  # ty: ignore[unresolved-import]

    _session_factory, sleeps, stop_after = cleanup_env
    stop_after(2)

    class BrokenSession:
        async def __aenter__(self):
            msg = "database is locked"
            raise RuntimeError(msg)

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr("app.main.SessionLocal", BrokenSession)

    with caplog.at_level("ERROR"), suppress(asyncio.CancelledError):
        await cleanup_old_readings()

    assert len(sleeps) == 2
    assert "Cleanup of old readings failed" in caplog.text


async def test_health_ok_when_tasks_alive(async_client, monkeypatch) -> None:
    """/health is 200 while every registered background task is still running."""
    import asyncio

    from app import main  # ty: ignore[unresolved-import]

    task = asyncio.create_task(asyncio.sleep(3600))
    monkeypatch.setattr(main, "background_tasks", {"mqtt_listener": task})
    try:
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
    finally:
        task.cancel()


async def test_health_503_when_task_died(async_client, monkeypatch) -> None:
    """/health is 503 and names the task once a background task has stopped."""
    import asyncio

    from app import main  # ty: ignore[unresolved-import]

    async def crash() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    dead = asyncio.create_task(crash())
    await asyncio.sleep(0)
    assert isinstance(dead.exception(), RuntimeError)  # also marks it retrieved
    alive = asyncio.create_task(asyncio.sleep(3600))
    monkeypatch.setattr(
        main, "background_tasks", {"cleanup_old_readings": dead, "mqtt_listener": alive}
    )
    try:
        resp = await async_client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "background tasks stopped: cleanup_old_readings"
    finally:
        alive.cancel()


async def test_log_task_exit_reports_crash_and_ignores_cancel(caplog) -> None:
    """The done-callback logs a crashed task with its traceback, not a cancelled one."""
    import asyncio

    from app.main import _log_task_exit  # ty: ignore[unresolved-import]

    async def crash() -> None:
        msg = "boom"
        raise RuntimeError(msg)

    crashed = asyncio.create_task(crash(), name="crasher")
    await asyncio.sleep(0)
    cancelled = asyncio.create_task(asyncio.sleep(3600), name="sleeper")
    cancelled.cancel()
    await asyncio.sleep(0)

    with caplog.at_level("ERROR"):
        _log_task_exit(crashed)
        _log_task_exit(cancelled)

    assert "Background task crasher died" in caplog.text
    assert "RuntimeError: boom" in caplog.text
    assert "sleeper" not in caplog.text


async def test_log_task_exit_reports_clean_exit(caplog) -> None:
    """A background task that returns (instead of running forever) is reported."""
    import asyncio

    from app.main import _log_task_exit  # ty: ignore[unresolved-import]

    async def finish() -> None:
        return

    task = asyncio.create_task(finish(), name="quitter")
    await asyncio.sleep(0)

    with caplog.at_level("ERROR"):
        _log_task_exit(task)

    assert "Background task quitter exited unexpectedly" in caplog.text


async def test_lifespan_starts_and_stops_background_tasks(monkeypatch) -> None:
    """Startup wires DB init, sun state and both tasks; shutdown cancels them."""
    import asyncio
    import logging
    from unittest.mock import AsyncMock

    from app import main  # ty: ignore[unresolved-import]

    init_db = AsyncMock()
    load_sun_state = AsyncMock()
    basic_config_calls: list[dict] = []
    monkeypatch.setattr(main, "init_db", init_db)
    monkeypatch.setattr(main, "_load_sun_state", load_sun_state)
    # Record instead of touching the root logger pytest is capturing from.
    monkeypatch.setattr(
        logging, "basicConfig", lambda **kw: basic_config_calls.append(kw)
    )

    async def run_forever() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "mqtt_listener", run_forever)
    monkeypatch.setattr(main, "cleanup_old_readings", run_forever)

    async with main.lifespan(main.app):
        assert [c["level"] for c in basic_config_calls] == [main.settings.log_level]
        init_db.assert_awaited_once()
        load_sun_state.assert_awaited_once()
        assert set(main.background_tasks) == {"mqtt_listener", "cleanup_old_readings"}
        started = dict(main.background_tasks)
        for name, task in started.items():
            assert task.get_name() == name
            assert not task.done()

    assert main.background_tasks == {}
    assert all(task.cancelled() for task in started.values())


def test_build_csp_includes_umami_host(monkeypatch) -> None:
    """When analytics is configured, the Umami host is allowed in script-src."""
    from app import main  # ty: ignore[unresolved-import]

    monkeypatch.setattr(main.settings, "umami_host", "https://umami.example.com")
    csp = main._build_csp()

    assert "script-src 'self' https://umami.example.com;" in csp
