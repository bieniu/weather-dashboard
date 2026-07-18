"""Tests for app.routers.weather — REST and WebSocket endpoints."""

from datetime import UTC, datetime

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.timeout(10)


async def test_get_sensors(async_client) -> None:
    """GET /api/weather/sensors returns sensor config from config.yaml."""
    resp = await async_client.get("/api/weather/sensors")
    assert resp.status_code == 200
    data = resp.json()
    assert "temperature" in data
    assert data["temperature"]["name"] == "Temperatura"
    assert data["temperature"]["unit"] == "°C"


async def test_get_current_empty_db(async_client) -> None:
    """GET /api/weather/current returns null values when DB is empty."""
    resp = await async_client.get("/api/weather/current")
    assert resp.status_code == 200
    data = resp.json()
    for value in data.values():
        assert value is None


async def test_get_current_with_data(async_client, seed_data) -> None:
    """GET /api/weather/current returns the latest reading per sensor."""
    resp = await async_client.get("/api/weather/current")
    assert resp.status_code == 200
    data = resp.json()

    assert data["temperature"] is not None
    assert data["temperature"]["parameter"] == "temperature"
    assert data["temperature"]["value"] == 24.0

    assert data["humidity"] is not None
    assert data["humidity"]["value"] == 55.0

    assert data["condition"] is not None
    assert data["condition"]["value_str"] == "sunny"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_history(async_client, db_session) -> None:
    """GET /api/weather/history/{param} filters by hours and returns ordered results."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    import datetime as dt

    old = WeatherReading(
        parameter="temperature",
        value=10.0,
        unit="°C",
        timestamp=now - dt.timedelta(hours=24),
    )
    recent = WeatherReading(
        parameter="temperature",
        value=20.0,
        unit="°C",
        timestamp=now - dt.timedelta(hours=2),
    )
    db_session.add_all([old, recent])
    await db_session.commit()

    resp = await async_client.get("/api/weather/history/temperature")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["value"] == 20.0

    resp = await async_client.get("/api/weather/history/temperature?hours=48")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_get_history_invalid_parameter(async_client) -> None:
    """GET /api/weather/history/{param} with unknown sensor returns 400."""
    resp = await async_client.get("/api/weather/history/nonexistent")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid parameter"


async def test_get_sensors_structure(async_client) -> None:
    """GET /api/weather/sensors returns all expected keys with required fields."""
    resp = await async_client.get("/api/weather/sensors")
    data = resp.json()
    expected_sensors = {
        "alerts",
        "condition",
        "air_quality",
        "temperature",
        "apparent_temperature",
        "humidity",
        "pressure",
        "pm1",
        "pm10",
        "pm25",
        "water_level",
    }
    assert set(data.keys()) == expected_sensors
    for sensor in data.values():
        assert "name" in sensor
        assert "icon" in sensor
        assert "color" in sensor
        assert "type" in sensor
        assert "history_hours" in sensor
    assert data["water_level"]["history_hours"] == 24
    assert data["temperature"]["history_hours"] == 24


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_alerts_empty_db(async_client) -> None:
    """GET /api/weather/alerts returns empty list when no alerts exist."""
    resp = await async_client.get("/api/weather/alerts")
    assert resp.status_code == 200
    assert resp.json() == []


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_alerts_filters_expired(async_client, db_session) -> None:
    """GET /api/weather/alerts returns only valid alerts (valid_to > now)."""
    from datetime import timedelta

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    valid = WeatherReading(
        parameter="alerts",
        value_str="burze",
        level="yellow",
        valid_to=now + timedelta(hours=24),
        timestamp=now,
    )
    expired = WeatherReading(
        parameter="alerts",
        value_str="stare",
        level="red",
        valid_to=now - timedelta(hours=1),
        timestamp=now - timedelta(hours=2),
    )
    db_session.add_all([valid, expired])
    await db_session.commit()

    resp = await async_client.get("/api/weather/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["value_str"] == "burze"
    assert data[0]["level"] == "yellow"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_alerts_ordered_newest_first(async_client, db_session) -> None:
    """GET /api/weather/alerts returns valid alerts ordered by timestamp DESC."""
    from datetime import timedelta

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    older = WeatherReading(
        parameter="alerts",
        value_str="older",
        level="yellow",
        valid_to=now + timedelta(hours=24),
        timestamp=now - timedelta(hours=2),
    )
    newer = WeatherReading(
        parameter="alerts",
        value_str="newer",
        level="orange",
        valid_to=now + timedelta(hours=24),
        timestamp=now,
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    resp = await async_client.get("/api/weather/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["value_str"] == "newer"
    assert data[1]["value_str"] == "older"


async def test_get_sun_no_data(async_client) -> None:
    """GET /api/weather/sun returns null when no sun data exists."""
    resp = await async_client.get("/api/weather/sun")
    assert resp.status_code == 200
    data = resp.json()
    assert data["parameter"] is None
    assert data["value"] is None
    assert data["timestamp"] is None


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_sun_with_data(async_client, db_session) -> None:
    """GET /api/weather/sun returns the latest sun reading."""
    from datetime import UTC, datetime

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    older = WeatherReading(
        parameter="sun", value_str="below_horizon", timestamp=now
    )
    newer = WeatherReading(
        parameter="sun",
        value_str="above_horizon",
        timestamp=now,
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    resp = await async_client.get("/api/weather/sun")
    assert resp.status_code == 200
    data = resp.json()
    assert data["value"] == "above_horizon"
    assert data["timestamp"] == "2026-06-23T12:00:00+00:00"
    assert data["parameter"] == "sun"


async def test_get_analytics_disabled(async_client) -> None:
    """GET /api/weather/analytics returns {} when Umami is not configured."""
    resp = await async_client.get("/api/weather/analytics")
    assert resp.status_code == 200
    assert resp.json() == {}


async def test_get_analytics_enabled(async_client) -> None:
    """GET /api/weather/analytics returns host and id when configured."""
    from app.config import settings  # ty: ignore[unresolved-import]

    host = "https://umami.example.com"
    uid = "1234-4567-5678"
    settings.umami_host = host
    settings.umami_id = uid
    try:
        resp = await async_client.get("/api/weather/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"host": host, "id": uid}
    finally:
        settings.umami_host = None
        settings.umami_id = None
