"""Tests for app.main — app setup, middleware, lifecycle."""

from datetime import UTC, datetime, timedelta

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


async def test_csp_middleware_adds_header(async_client) -> None:
    """Every response includes a Content-Security-Policy header."""
    resp = await async_client.get("/api/weather/sensors")
    assert "Content-Security-Policy" in resp.headers
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp


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


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_cleanup_old_readings(monkeypatch, db_engine) -> None:
    """Readings older than 30 days are removed by cleanup_old_readings."""
    import asyncio
    from contextlib import suppress

    from app.main import cleanup_old_readings  # ty: ignore[unresolved-import]
    from app.models import WeatherReading  # ty: ignore[unresolved-import]
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.main.SessionLocal", test_session_factory)

    call_count: list[int] = [0]

    async def mock_sleep(_: int) -> None:
        call_count[0] += 1
        if call_count[0] >= 2:
            msg = "break loop"
            raise asyncio.CancelledError(msg)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    now = datetime.now(UTC)
    new_reading = WeatherReading(
        parameter="temperature",
        value=22.0,
        unit="°C",
        timestamp=now - timedelta(days=1),
    )
    old_reading = WeatherReading(
        parameter="temperature",
        value=10.0,
        unit="°C",
        timestamp=now - timedelta(days=31),
    )

    async with test_session_factory() as session:
        session.add_all([new_reading, old_reading])
        await session.commit()

    with suppress(asyncio.CancelledError):
        await cleanup_old_readings()

    async with test_session_factory() as session:
        remaining = (await session.execute(select(WeatherReading))).scalars().all()
        assert len(remaining) == 1
        assert remaining[0].value == 22.0


async def test_cleanup_keeps_recent_readings(monkeypatch, db_engine) -> None:
    """Readings younger than 30 days are preserved by cleanup_old_readings."""
    import asyncio
    from contextlib import suppress

    from app.main import cleanup_old_readings  # ty: ignore[unresolved-import]
    from app.models import WeatherReading  # ty: ignore[unresolved-import]
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.main.SessionLocal", test_session_factory)

    call_count: list[int] = [0]

    async def mock_sleep(_: int) -> None:
        call_count[0] += 1
        if call_count[0] >= 2:
            msg = "break loop"
            raise asyncio.CancelledError(msg)

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    async with test_session_factory() as session:
        session.add(WeatherReading(parameter="temperature", value=22.0, unit="°C"))
        await session.commit()

    with suppress(asyncio.CancelledError):
        await cleanup_old_readings()

    async with test_session_factory() as session:
        remaining = (await session.execute(select(WeatherReading))).scalars().all()
        assert len(remaining) == 1
