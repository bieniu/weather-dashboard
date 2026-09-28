"""Pydantic schemas and response shapes for the weather API."""

from datetime import datetime  # noqa: TC003  # pydantic needs it at runtime
from typing import Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, field_serializer


class WeatherReadingOut(BaseModel):
    """Output schema for a weather reading in the REST API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    parameter: str
    value: float | None = None
    unit: str = ""
    value_str: str | None = None
    icon: str | None = None
    level: str | None = None
    valid_to: datetime | None = None
    timestamp: datetime

    @field_serializer("timestamp", "valid_to")
    def iso_format(self, dt: datetime | None) -> str | None:
        """Serialize as ``isoformat()`` (``+00:00``, not Pydantic's ``Z``).

        ``UTCDateTime`` columns always load as aware UTC datetimes.
        """
        return None if dt is None else dt.isoformat()


class SunOut(TypedDict):
    """``GET /sun`` — all fields are ``None`` until the first sun reading."""

    parameter: Literal["sun"] | None
    value: str | None
    timestamp: str | None


class ForecastOut(TypedDict):
    """``GET /forecast`` — the stored forecast list and when it was received."""

    forecast: list[Any]
    timestamp: str | None


class AnalyticsOut(TypedDict):
    """``GET /analytics`` — empty unless Umami host and id are both configured."""

    host: NotRequired[str]
    id: NotRequired[str]
