"""Tests for app.schemas — WeatherReadingOut Pydantic model."""

from datetime import UTC, datetime


def test_from_attributes() -> None:
    """WeatherReadingOut can be created from an ORM WeatherReading instance."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]
    from app.schemas import WeatherReadingOut  # ty: ignore[unresolved-import]

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
    from app.schemas import WeatherReadingOut  # ty: ignore[unresolved-import]

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
    from app.schemas import WeatherReadingOut  # ty: ignore[unresolved-import]

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


def test_alert_fields_serialization() -> None:
    """Alert reading with level and valid_to serialises correctly."""
    from app.schemas import WeatherReadingOut  # ty: ignore[unresolved-import]

    data = WeatherReadingOut(
        id=4,
        parameter="alert",
        value=None,
        unit="",
        value_str="burze",
        level="yellow",
        valid_to=datetime(2026, 7, 18, 19, 0, 0, tzinfo=UTC),
        timestamp=datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC),
    )
    serialized = data.model_dump(mode="json")
    assert serialized["level"] == "yellow"
    assert serialized["valid_to"] == "2026-07-18T19:00:00+00:00"
    assert serialized["value_str"] == "burze"
    assert serialized["value"] is None


def test_alert_valid_to_none_serialization() -> None:
    """Alert with valid_to=None serialises valid_to as None."""
    from app.schemas import WeatherReadingOut  # ty: ignore[unresolved-import]

    data = WeatherReadingOut(
        id=5,
        parameter="alert",
        value=None,
        unit="",
        value_str="test",
        level="red",
        valid_to=None,
        timestamp=datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC),
    )
    serialized = data.model_dump(mode="json")
    assert serialized["valid_to"] is None


def test_condition_fields_nullable() -> None:
    """Condition readings serialise value=None, value_str and icon present."""
    from app.schemas import WeatherReadingOut  # ty: ignore[unresolved-import]

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
