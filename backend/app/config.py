"""Application configuration — loading environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the .env file."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mqtt_broker: str
    mqtt_port: int = 1883
    mqtt_user: str
    mqtt_password: str


settings = Settings()
