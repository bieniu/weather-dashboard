"""Pydantic schemas for weather data."""

from pydantic import BaseModel
from datetime import datetime


class MqttPayload(BaseModel):
    """MQTT message payload from a weather sensor."""

    value: float
    unit: str


class WeatherReadingOut(BaseModel):
    """Output schema for a weather reading in the REST API."""

    id: int
    parameter: str
    value: float
    unit: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class CurrentReadings(BaseModel):
    """Current temperature and humidity readings."""

    temperature: WeatherReadingOut | None
    humidity: WeatherReadingOut | None
