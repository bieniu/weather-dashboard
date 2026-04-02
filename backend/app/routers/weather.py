"""REST + WebSocket router for weather data."""

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timezone, timedelta

from ..config import settings
from ..database import get_db
from ..models import WeatherReading
from ..schemas import WeatherReadingOut
from ..mqtt_client import manager

router = APIRouter(prefix="/api/weather", tags=["weather"])


@router.get("/sensors")
async def get_sensors() -> dict:
    """Return sensor configuration from config.yaml."""
    return {
        key: sensor.model_dump() for key, sensor in settings.sensors.items()
    }


@router.get("/current", response_model=dict[str, WeatherReadingOut | None])
async def get_current(db: AsyncSession = Depends(get_db)) -> dict:
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
    hours: int = 12,
    db: AsyncSession = Depends(get_db),
) -> list[WeatherReadingOut]:
    """Return reading history for the last `hours` hours (default 12)."""
    if parameter not in settings.sensors:
        raise HTTPException(status_code=400, detail="Invalid parameter")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(WeatherReading)
        .where(
            WeatherReading.parameter == parameter,
            WeatherReading.timestamp >= since,
        )
        .order_by(WeatherReading.timestamp)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket — push new readings to frontend clients."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive / ping
    except WebSocketDisconnect:
        manager.disconnect(websocket)
