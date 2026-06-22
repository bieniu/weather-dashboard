"""Pydantic schemas for weather data."""

from pydantic import BaseModel
from datetime import datetime


class WeatherReadingOut(BaseModel):
    """Output schema for a weather reading in the REST API."""

    id: int
    parameter: str
    value: float | None = None
    unit: str = ""
    value_str: str | None = None
    icon: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}



