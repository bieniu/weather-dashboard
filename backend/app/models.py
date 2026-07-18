"""ORM models for weather readings."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, Index, Integer, String

from .database import Base


class WeatherReading(Base):
    """Single weather reading (temperature, humidity, condition, or alert)."""

    __tablename__ = "weather_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter = Column(String(50), nullable=False)  # "temperature" | "humidity" | ...
    value = Column(Float, nullable=True)  # None for condition/alert type
    unit = Column(String(10), nullable=False, default="")  # "°C" | "%" | ""
    value_str = Column(String(100), nullable=True)  # string value for condition/alert
    icon = Column(String(50), nullable=True)  # weather icon for condition sensor
    level = Column(String(20), nullable=True)  # alert level e.g. "yellow"
    valid_to = Column(DateTime(timezone=True), nullable=True)  # alert expiry
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_weather_parameter_timestamp", "parameter", "timestamp"),
        Index("ix_weather_parameter_valid_to", "parameter", "valid_to"),
    )
