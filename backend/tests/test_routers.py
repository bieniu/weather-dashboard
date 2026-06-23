"""Tests for app.routers.weather — REST and WebSocket endpoints."""

from datetime import UTC, datetime

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.timeout(10)


async def test_get_sensors(async_client) -> None:
    resp = await async_client.get("/api/weather/sensors")
    assert resp.status_code == 200
    data = resp.json()
    assert "temperature" in data
    assert data["temperature"]["name"] == "Temperatura"
    assert data["temperature"]["unit"] == "°C"


async def test_get_current_empty_db(async_client) -> None:
    resp = await async_client.get("/api/weather/current")
    assert resp.status_code == 200
    data = resp.json()
    # All sensor values should be null in empty DB
    for value in data.values():
        assert value is None


async def test_get_current_with_data(async_client, seed_data) -> None:
    resp = await async_client.get("/api/weather/current")
    assert resp.status_code == 200
    data = resp.json()

    # temperature should have latest value (24.0)
    assert data["temperature"] is not None
    assert data["temperature"]["parameter"] == "temperature"
    assert data["temperature"]["value"] == 24.0

    # humidity should have latest value (55.0)
    assert data["humidity"] is not None
    assert data["humidity"]["value"] == 55.0

    # condition should have latest string value
    assert data["condition"] is not None
    assert data["condition"]["value_str"] == "sunny"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_history(async_client, db_session) -> None:
    from app.models import WeatherReading

    now = datetime.now(UTC)
    import datetime as dt

    # Insert readings at different times
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

    # Default hours=12 should only include recent
    resp = await async_client.get("/api/weather/history/temperature")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["value"] == 20.0

    # hours=48 should include both
    resp = await async_client.get("/api/weather/history/temperature?hours=48")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_get_history_invalid_parameter(async_client) -> None:
    resp = await async_client.get("/api/weather/history/nonexistent")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid parameter"


@pytest.mark.skip(reason="Requires real WebSocket over ASGI transport")
async def test_websocket_endpoint(async_client) -> None:
    """WebSocket test placeholder — needs live ASGI lifespan support."""


async def test_get_sensors_structure(async_client) -> None:
    resp = await async_client.get("/api/weather/sensors")
    data = resp.json()
    # Check all sensor keys from config.yaml are present
    expected_sensors = {
        "condition",
        "temperature",
        "apparent_temperature",
        "humidity",
        "pressure",
        "pm1",
        "pm10",
        "pm25",
    }
    assert set(data.keys()) == expected_sensors
    for sensor in data.values():
        assert "name" in sensor
        assert "icon" in sensor
        assert "color" in sensor
        assert "type" in sensor
