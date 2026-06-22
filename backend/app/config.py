"""Application configuration — loading environment variables."""

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_config_yaml() -> dict:
    with (ROOT_DIR / "config.yaml").open() as f:
        return yaml.safe_load(f)


_yaml_config = _load_config_yaml()


class SensorConfig(BaseModel):
    """Configuration for a single sensor."""

    name: str
    icon: str
    color: str
    type: str = "numeric"
    round: int = 1
    unit: str = ""


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
    port: int = 8000
    scheme: str = "http"
    topic_prefix: str = _yaml_config["topic_prefix"]
    sensors: dict[str, SensorConfig] = {
        k: SensorConfig(**v) for k, v in _yaml_config["sensors"].items()
    }

    @property
    def cors_origins(self) -> list[str]:
        """Return allowed CORS origins."""
        return [
            f"{self.scheme}://{self.domain}:{self.port}",
            "http://127.0.0.1:8000",
        ]


settings = Settings()  # ty: ignore
