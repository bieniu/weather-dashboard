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
