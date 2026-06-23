"""Tests for app.schemas — WeatherReadingOut Pydantic model."""

from datetime import UTC, datetime


def test_from_attributes() -> None:
    """WeatherReadingOut can be created from an ORM WeatherReading instance."""
    from app.models import WeatherReading
    from app.schemas import WeatherReadingOut

    orm = WeatherReading(
        id=42,
        parameter="temperature",
        value=22.5,
        unit="°C",
        timestamp=datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC),
    )
    schema = WeatherReadingOut.model_validate(orm)
    assert schema.id == 42
    assert schema.parameter == "temperature"
    assert schema.value == 22.5
    assert schema.unit == "°C"


def test_serialize_naive_timestamp_adds_utc() -> None:
    """A naive datetime gets UTC timezone attached during serialization."""
    from app.schemas import WeatherReadingOut

    data = WeatherReadingOut(
        id=1,
        parameter="temperature",
        value=22.5,
        unit="°C",
        timestamp=datetime(2026, 6, 23, 12, 0, 0),  # noqa: DTZ001
    )
    serialized = data.model_dump(mode="json")
    assert serialized["timestamp"].endswith("+00:00")


def test_serialize_utc_timestamp_stays_utc() -> None:
    """A UTC-aware datetime is serialised correctly with +00:00 offset."""
    from app.schemas import WeatherReadingOut

    dt = datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC)
    data = WeatherReadingOut(
        id=2,
        parameter="humidity",
        value=55.0,
        unit="%",
        timestamp=dt,
    )
    serialized = data.model_dump(mode="json")
    assert serialized["timestamp"] == "2026-06-23T12:00:00+00:00"


def test_condition_fields_nullable() -> None:
    """Condition readings serialise value=None, value_str and icon present."""
    from app.schemas import WeatherReadingOut

    data = WeatherReadingOut(
        id=3,
        parameter="condition",
        value=None,
        unit="",
        value_str="sunny",
        icon="mdi:weather-sunny",
        timestamp=datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC),
    )
    assert data.value is None
    assert data.value_str == "sunny"
    assert data.icon == "mdi:weather-sunny"
