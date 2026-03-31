"""ORM models for weather readings."""

from sqlalchemy import Column, Integer, Float, String, DateTime, Index
from datetime import datetime, timezone

from .database import Base


class WeatherReading(Base):
    """Single weather reading (temperature or humidity)."""
    __tablename__ = "weather_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter = Column(String(50), nullable=False)  # "temperature" | "humidity"
    value = Column(Float, nullable=False)
    unit = Column(String(10), nullable=False)  # "°C" | "%"
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_weather_parameter_timestamp", "parameter", "timestamp"),
    )
