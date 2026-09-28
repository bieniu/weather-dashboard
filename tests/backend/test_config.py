"""Tests for app.config — Settings and SensorConfig."""

import pytest


def test_sensor_config_defaults() -> None:
    """SensorConfig applies default type, round, unit, history_hours."""
    from app.config import SensorConfig  # ty: ignore[unresolved-import]

    config = SensorConfig(name="Test", icon="mdi:test", color="#000")
    assert config.type == "numeric"
    assert config.round == 1
    assert config.unit == ""
    assert config.history_hours == 24


@pytest.mark.parametrize("history_hours", [0, -1, 721])
def test_sensor_config_rejects_history_hours_out_of_range(history_hours) -> None:
    """history_hours outside 1..720 fails at config load, not as a runtime 422."""
    from app.config import SensorConfig  # ty: ignore[unresolved-import]
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SensorConfig(name="Test", history_hours=history_hours)


def test_sensor_config_explicit() -> None:
    """SensorConfig accepts all fields explicitly."""
    from app.config import SensorConfig  # ty: ignore[unresolved-import]

    config = SensorConfig(
        name="Pressure",
        icon="mdi:speed",
        color="#009688",
        type="numeric",
        round=0,
        unit="hPa",
        history_hours=48,
    )
    assert config.name == "Pressure"
    assert config.round == 0
    assert config.unit == "hPa"
    assert config.history_hours == 48


def test_settings_loads_sensors() -> None:
    """Settings reads all sensor keys from config.yaml."""
    from app.config import settings  # ty: ignore[unresolved-import]

    assert "temperature" in settings.sensors
    assert "humidity" in settings.sensors


def test_settings_log_level_default() -> None:
    """log_level defaults to INFO."""
    from app.config import settings  # ty: ignore[unresolved-import]

    assert settings.log_level == "INFO"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("info", "INFO"), ("Debug", "DEBUG"), ("WARNING", "WARNING")],
)
def test_settings_log_level_is_case_insensitive(raw, expected) -> None:
    """LOG_LEVEL from .env/compose may be lower-case; it is normalised."""
    from app.config import Settings  # ty: ignore[unresolved-import]

    settings = Settings(_env_file=None, mqtt_broker="b", mqtt_user="u", log_level=raw)
    assert settings.log_level == expected


def test_settings_log_level_rejects_unknown_name() -> None:
    """A non-standard level name fails at startup instead of inside logging."""
    from app.config import Settings  # ty: ignore[unresolved-import]
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, mqtt_broker="b", mqtt_user="u", log_level="loud")


def test_settings_topic_prefix() -> None:
    """Settings reads topic_prefix from config.yaml."""
    from app.config import settings  # ty: ignore[unresolved-import]

    assert settings.topic_prefix == "weather-dashboard"


def test_settings_cors_origins() -> None:
    """Settings.cors_origins returns expected list of origins."""
    from app.config import settings  # ty: ignore[unresolved-import]

    origins = settings.cors_origins
    assert f"{settings.scheme}://{settings.domain}:{settings.port}" in origins
    assert "http://127.0.0.1:8332" in origins
    assert len(origins) == 2
