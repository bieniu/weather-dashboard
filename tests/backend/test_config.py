"""Tests for app.config — Settings and SensorConfig."""


def test_sensor_config_defaults() -> None:
    """SensorConfig applies default type='numeric', round=1, unit=''."""
    from app.config import SensorConfig

    config = SensorConfig(name="Test", icon="mdi:test", color="#000")
    assert config.type == "numeric"
    assert config.round == 1
    assert config.unit == ""


def test_sensor_config_explicit() -> None:
    """SensorConfig accepts all fields explicitly."""
    from app.config import SensorConfig

    config = SensorConfig(
        name="Pressure",
        icon="mdi:speed",
        color="#009688",
        type="numeric",
        round=0,
        unit="hPa",
    )
    assert config.name == "Pressure"
    assert config.round == 0
    assert config.unit == "hPa"


def test_settings_loads_sensors() -> None:
    """Settings reads all sensor keys from config.yaml."""
    from app.config import settings

    assert "temperature" in settings.sensors
    assert "humidity" in settings.sensors


def test_settings_topic_prefix() -> None:
    """Settings reads topic_prefix from config.yaml."""
    from app.config import settings

    assert settings.topic_prefix == "weather-dashboard"


def test_settings_cors_origins() -> None:
    """Settings.cors_origins returns expected list of origins."""
    from app.config import settings

    origins = settings.cors_origins
    assert f"{settings.scheme}://{settings.domain}:{settings.port}" in origins
    assert "http://127.0.0.1:8332" in origins
    assert len(origins) == 2
