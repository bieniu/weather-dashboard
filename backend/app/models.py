"""ORM models for weather readings."""

from datetime import UTC, datetime
from typing import override

from sqlalchemy import DateTime, Dialect, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from .database import Base


class UTCDateTime(TypeDecorator[datetime]):
    """``DATETIME`` column that always hands back timezone-aware UTC values.

    SQLite stores no offset, so a plain ``DateTime(timezone=True)`` reads back
    naive datetimes. Aware values are converted to UTC before they are written.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @override
    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        """Store aware values as UTC (SQLite drops the offset)."""
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC)
        return value

    @override
    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        """Attach UTC to the naive value SQLite returns."""
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class WeatherReading(Base):
    """Single weather reading (temperature, humidity, condition, or alert)."""

    __tablename__ = "weather_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parameter: Mapped[str] = mapped_column(String(50))  # "temperature" | ...
    value: Mapped[float | None]  # None for condition/alert type
    unit: Mapped[str] = mapped_column(String(10), default="")  # "°C" | "%" | ""
    value_str: Mapped[str | None] = mapped_column(String(100))  # condition/alert
    icon: Mapped[str | None] = mapped_column(String(50))  # condition sensor icon
    level: Mapped[str | None] = mapped_column(String(20))  # alert level "yellow"
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime)  # alert expiry
    timestamp: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("ix_weather_parameter_timestamp", "parameter", "timestamp"),
        Index("ix_weather_parameter_valid_to", "parameter", "valid_to"),
        # Retention cleanup filters on timestamp alone (no leading parameter).
        Index("ix_weather_timestamp", "timestamp"),
    )
