"""Tests for app.models — WeatherReading ORM model."""

from datetime import UTC, datetime

import pytest
from freezegun import freeze_time
from sqlalchemy import inspect


def test_weather_reading_numeric_creation() -> None:
    """A numeric reading sets value/unit and leaves value_str/icon as None."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    r = WeatherReading(parameter="temperature", value=22.5, unit="°C")
    assert r.parameter == "temperature"
    assert r.value == 22.5
    assert r.unit == "°C"
    assert r.value_str is None
    assert r.icon is None


def test_weather_reading_condition_creation() -> None:
    """A condition reading sets value_str/icon and leaves value as None."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    r = WeatherReading(
        parameter="condition",
        value=None,
        unit="",
        value_str="sunny",
        icon="mdi:weather-sunny",
    )
    assert r.value is None
    assert r.value_str == "sunny"
    assert r.icon == "mdi:weather-sunny"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_default_timestamp(db_session) -> None:
    """A new WeatherReading gets timestamp set to datetime.now(UTC)."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    r = WeatherReading(parameter="temperature", value=22.5, unit="°C")
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)

    # SQLite strips timezone — re-attach UTC like the app does
    ts = r.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    assert ts == datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("name", "columns"),
    [
        ("ix_weather_parameter_timestamp", ["parameter", "timestamp"]),
        ("ix_weather_parameter_valid_to", ["parameter", "valid_to"]),
        ("ix_weather_timestamp", ["timestamp"]),
    ],
)
async def test_index_exists(db_engine, name, columns) -> None:
    """Each index declared on the model is created with the expected columns."""
    async with db_engine.connect() as conn:
        indexes = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes("weather_readings")
        )

    by_name = {idx["name"]: idx["column_names"] for idx in indexes}
    assert by_name.get(name) == columns
