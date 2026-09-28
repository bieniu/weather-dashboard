"""Tests for app.models — WeatherReading ORM model."""

from datetime import UTC, datetime

import pytest
from freezegun import freeze_time
from sqlalchemy import inspect, select, text


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

    assert r.timestamp == datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)
    assert r.timestamp.tzinfo is UTC


async def test_utc_datetime_reads_naive_db_value_as_aware_utc(db_session) -> None:
    """A naive DATETIME stored by SQLite loads back as an aware UTC datetime."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    await db_session.execute(
        text(
            "INSERT INTO weather_readings (parameter, unit, valid_to, timestamp) "
            "VALUES ('alerts', '', '2026-06-23 18:00:00.000000', "
            "'2026-06-23 12:00:00.000000')"
        )
    )
    row = (await db_session.execute(select(WeatherReading))).scalar_one()

    assert row.timestamp == datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)
    assert row.timestamp.tzinfo is UTC
    assert row.valid_to == datetime(2026, 6, 23, 18, 0, 0, tzinfo=UTC)
    assert row.valid_to.tzinfo is UTC


async def test_utc_datetime_stores_other_offsets_as_utc(db_session) -> None:
    """An aware non-UTC datetime is converted to UTC before SQLite drops the offset."""
    from datetime import timedelta, timezone

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    warsaw_summer = timezone(timedelta(hours=2))
    db_session.add(
        WeatherReading(
            parameter="temperature",
            value=1.0,
            unit="°C",
            timestamp=datetime(2026, 6, 23, 14, 0, 0, tzinfo=warsaw_summer),
        )
    )
    await db_session.commit()

    stored = (
        await db_session.execute(text("SELECT timestamp FROM weather_readings"))
    ).scalar_one()
    assert stored == "2026-06-23 12:00:00.000000"


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
