"""Pydantic schemas for weather data."""

from pydantic import BaseModel
from pydantic import field_serializer
from datetime import datetime, timezone


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

    @field_serializer("timestamp")
    def ensure_utc(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()



