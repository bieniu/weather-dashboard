"""Pydantic schemas for weather data."""

from datetime import UTC, datetime

from pydantic import BaseModel, field_serializer


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
        """Serialize timestamp as ISO 8601 string with UTC timezone."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()
