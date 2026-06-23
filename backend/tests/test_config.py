"""Tests for app.config — Settings and SensorConfig."""

from app.config import SensorConfig, settings


def test_sensor_config_defaults() -> None:
    config = SensorConfig(name="Test", icon="mdi:test", color="#000")
    assert config.type == "numeric"
    assert config.round == 1
    assert config.unit == ""


def test_sensor_config_explicit() -> None:
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
    assert "temperature" in settings.sensors
    assert "humidity" in settings.sensors


def test_settings_topic_prefix() -> None:
    assert settings.topic_prefix == "weather-dashboard"


def test_settings_cors_origins() -> None:
    origins = settings.cors_origins
    assert f"{settings.scheme}://{settings.domain}:{settings.port}" in origins
    assert "http://127.0.0.1:8332" in origins
    assert len(origins) == 2
