"""Tests for app.config — Settings and SensorConfig."""

import pytest


def test_sensor_config_defaults() -> None:
    """SensorConfig applies default type, round, unit, history_hours."""
    from app.config import SensorConfig  # ty: ignore[unresolved-import]

    config = SensorConfig(name="Test", icon="mdi:test", color="#000")
    assert config.type == "numeric"
    assert config.round == 1
    assert config.unit == ""
    assert config.history_hours == 24  # DEFAULT_HISTORY_HOURS


@pytest.mark.parametrize("history_hours", [0, -1, 721])
def test_sensor_config_rejects_history_hours_out_of_range(history_hours) -> None:
    """history_hours outside 1..720 fails at config load, not as a runtime 422."""
    from app.config import SensorConfig  # ty: ignore[unresolved-import]
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SensorConfig(name="Test", history_hours=history_hours)


def test_sensor_config_rejects_unknown_type() -> None:
    """A typo in ``type:`` fails at config load instead of per message."""
    from app.config import SensorConfig  # ty: ignore[unresolved-import]
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SensorConfig(name="Test", type="forecasts")


@pytest.mark.parametrize(
    ("sensor_type", "expected"),
    [("alerts", "alerts"), ("forecast", "forecast"), ("condition", "condition")],
)
def test_settings_key_for_type(sensor_type, expected) -> None:
    """key_for_type returns the configured sensor key of that type."""
    from app.config import SensorType, settings  # ty: ignore[unresolved-import]

    assert settings.key_for_type(SensorType(sensor_type)) == expected


def test_settings_key_for_type_missing() -> None:
    """key_for_type returns None when no sensor of that type is configured."""
    from app.config import SensorType, Settings  # ty: ignore[unresolved-import]

    settings = Settings(_env_file=None, mqtt_broker="b", mqtt_user="u", sensors={})
    assert settings.key_for_type(SensorType.ALERTS) is None


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


def test_settings_mqtt_base_topic_default() -> None:
    """Without MQTT_BASE_TOPIC set, the default keeps CI and no-.env runs working."""
    from app.config import Settings  # ty: ignore[unresolved-import]

    settings = Settings(_env_file=None, mqtt_broker="b", mqtt_user="u")
    assert settings.mqtt_base_topic == "weather-dashboard"


def test_settings_mqtt_base_topic_env_override(monkeypatch) -> None:
    """MQTT_BASE_TOPIC overrides the default topic prefix."""
    from app.config import Settings  # ty: ignore[unresolved-import]

    monkeypatch.setenv("MQTT_BASE_TOPIC", "custom-topic")
    settings = Settings(_env_file=None, mqtt_broker="b", mqtt_user="u")
    assert settings.mqtt_base_topic == "custom-topic"


def test_settings_allowed_origins_defaults() -> None:
    """Defaults allow the public origin with and without port plus loopback."""
    from app.config import Settings  # ty: ignore[unresolved-import]

    settings = Settings(_env_file=None, mqtt_broker="b", mqtt_user="u")
    assert settings.allowed_origins == [
        "http://localhost",
        "http://localhost:8332",
        "http://127.0.0.1:8332",
    ]


def test_settings_allowed_origins_behind_tunnel() -> None:
    """Behind Cloudflare the browser's Origin is https://domain with no port."""
    from app.config import Settings  # ty: ignore[unresolved-import]

    settings = Settings(
        _env_file=None,
        mqtt_broker="b",
        mqtt_user="u",
        scheme="https",
        domain="Pogoda.Example.com",
        port=8332,
    )
    assert settings.allowed_origins[0] == "https://pogoda.example.com"
    assert "https://pogoda.example.com:8332" in settings.allowed_origins
