"""REST + WebSocket router for weather data."""

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, select

if TYPE_CHECKING:
    from collections.abc import Sequence

from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002  # needed at runtime for get_type_hints
)

from app.config import settings
from app.database import get_db
from app.models import WeatherReading
from app.mqtt_client import manager
from app.schemas import WeatherReadingOut

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/sensors")
async def get_sensors() -> dict:
    """Return sensor configuration from config.yaml."""
    return {key: sensor.model_dump() for key, sensor in settings.sensors.items()}


@router.get("/current", response_model=dict[str, WeatherReadingOut | None])
async def get_current(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the latest reading for each configured sensor."""
    result: dict = {}
    for param in settings.sensors:
        stmt = (
            select(WeatherReading)
            .where(WeatherReading.parameter == param)
            .order_by(desc(WeatherReading.timestamp))
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        result[param] = row
    return result


@router.get("/history/{parameter}", response_model=list[WeatherReadingOut])
async def get_history(
    parameter: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: int = 12,
) -> Sequence[WeatherReading]:
    """Return reading history for the last `hours` hours (default 12)."""
    if parameter not in settings.sensors:
        raise HTTPException(status_code=400, detail="Invalid parameter")

    since = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(WeatherReading)
        .where(
            WeatherReading.parameter == parameter,
            WeatherReading.timestamp >= since,
        )
        .order_by(WeatherReading.timestamp)
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/alerts", response_model=list[WeatherReadingOut])
async def get_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Sequence[WeatherReading]:
    """Return all currently-valid alert readings (valid_to > now), newest first."""
    alerts_key = settings.alerts_key
    if alerts_key is None:
        return []

    now = datetime.now(UTC)
    stmt = (
        select(WeatherReading)
        .where(
            WeatherReading.parameter == alerts_key,
            WeatherReading.valid_to > now,
        )
        .order_by(desc(WeatherReading.timestamp))
    )
    return (await db.execute(stmt)).scalars().all()


@router.get("/sun")
async def get_sun(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the latest sun position reading."""
    stmt = (
        select(WeatherReading)
        .where(WeatherReading.parameter == "sun")
        .order_by(desc(WeatherReading.timestamp))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return {"parameter": None, "value": None, "timestamp": None}
    ts = row.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return {
        "parameter": "sun",
        "value": row.value_str,
        "timestamp": ts.isoformat(),
    }


@router.get("/forecast")
async def get_forecast(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """Return the latest forecast data as parsed JSON."""
    forecast_key = next(
        (k for k, s in settings.sensors.items() if s.type == "forecast"), None
    )
    if forecast_key is None:
        return []

    stmt = (
        select(WeatherReading)
        .where(WeatherReading.parameter == forecast_key)
        .order_by(desc(WeatherReading.timestamp))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return []
    raw = row.value_str
    if raw is None:
        return []
    return json.loads(str(raw))


@router.get("/analytics")
async def get_analytics() -> dict:
    """Return Umami analytics config if both host and ID are configured."""
    if settings.umami_host and settings.umami_id:
        return {"host": settings.umami_host, "id": settings.umami_id}
    return {}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket — push new readings to frontend clients."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive / ping
    except WebSocketDisconnect:
        manager.disconnect(websocket)
