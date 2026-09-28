"""Application configuration — loading environment variables."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

# Upper bound for history windows (config and the /history API). Readings older
# than 30 days are deleted by ``cleanup_old_readings`` in ``main.py``, so a
# longer window could never return more data.
MAX_HISTORY_HOURS = 24 * 30
# Default window for charts; the frontend's HISTORY_HOURS mirrors this value.
DEFAULT_HISTORY_HOURS = 24


def _load_config_yaml() -> dict:
    with (ROOT_DIR / "config.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


_yaml_config = _load_config_yaml()


class SensorType(StrEnum):
    """How a sensor's MQTT payload is parsed, stored and rendered."""

    NUMERIC = "numeric"
    CONDITION = "condition"
    TEXT = "text"
    ALERTS = "alerts"
    FORECAST = "forecast"


class SensorConfig(BaseModel):
    """Configuration for a single sensor."""

    name: str
    icon: str = ""
    color: str | None = None
    type: SensorType = SensorType.NUMERIC
    round: int = 1
    unit: str = ""
    history_hours: int = Field(
        default=DEFAULT_HISTORY_HOURS, ge=1, le=MAX_HISTORY_HOURS
    )


class Settings(BaseSettings):
    """Application settings loaded from the .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
    )

    mqtt_broker: str
    mqtt_port: int = 1883
    mqtt_user: str
    mqtt_password: str = ""
    domain: str = "localhost"
    port: int = 8332
    scheme: str = "http"
    umami_host: str | None = None
    umami_id: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    topic_prefix: str = _yaml_config["topic_prefix"]
    sensors: dict[str, SensorConfig] = {
        k: SensorConfig(**v) for k, v in _yaml_config["sensors"].items()
    }

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        """Accept ``info``/``Debug`` from .env; logging level names are upper-case."""
        return value.upper() if isinstance(value, str) else value

    def key_for_type(self, sensor_type: SensorType) -> str | None:
        """Return the key of the first sensor of ``sensor_type``, or ``None``."""
        return next(
            (key for key, s in self.sensors.items() if s.type == sensor_type), None
        )

    @property
    def allowed_origins(self) -> list[str]:
        """Origins accepted for CORS and for WebSocket handshakes.

        Behind the Cloudflare tunnel the browser talks to ``{scheme}://{domain}``
        on the scheme's default port, so that origin carries no port. The
        ``{domain}:{port}`` form keeps direct LAN access working, and the
        loopback entries keep local development working. Browsers send the host
        lower-cased, hence ``domain.lower()``.
        """
        domain = self.domain.lower()
        origins = [
            f"{self.scheme}://{domain}",
            f"{self.scheme}://{domain}:{self.port}",
            f"http://localhost:{self.port}",
            f"http://127.0.0.1:{self.port}",
        ]
        return list(dict.fromkeys(origins))  # de-duplicate (domain=localhost)


settings = Settings()
