"""REST + WebSocket router for weather data."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import desc, func, or_, select, union_all

if TYPE_CHECKING:
    from collections.abc import Sequence

from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002  # needed at runtime for get_type_hints
)

from app.config import (
    DEFAULT_HISTORY_HOURS,
    MAX_HISTORY_HOURS,
    MAX_HISTORY_POINTS,
    SensorConfig,
    SensorType,
    settings,
)
from app.database import get_db
from app.models import WeatherReading
from app.mqtt_client import manager
from app.ratelimit import client_key
from app.schemas import AnalyticsOut, ForecastOut, SunOut, WeatherReadingOut

router = APIRouter(prefix="/api/weather", tags=["weather"])

MAX_WS_CONNECTIONS = 500  # bounds memory; the per-client cap does the limiting
MAX_WS_CONNECTIONS_PER_IP = 5
WS_CLOSE_POLICY_VIOLATION = 1008
WS_CLOSE_TRY_AGAIN_LATER = 1013

# Open WebSocket handlers per client key (IPv4 address or IPv6 /64, see
# client_key). Counted synchronously *before* accept() (no await in between), so
# concurrent handshakes cannot overshoot the caps, and a client the broadcaster
# already dropped still counts until its handler ends.
_open_ws_by_ip: Counter[str] = Counter()


async def _latest(db: AsyncSession, parameter: str) -> WeatherReading | None:
    """Return the newest reading of ``parameter`` (ties go to the highest id)."""
    stmt = (
        select(WeatherReading)
        .where(WeatherReading.parameter == parameter)
        .order_by(desc(WeatherReading.timestamp), desc(WeatherReading.id))
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@router.get("/sensors")
async def get_sensors() -> dict[str, SensorConfig]:
    """Return sensor configuration from config.yaml."""
    return settings.sensors


@router.get("/current", response_model=dict[str, WeatherReadingOut | None])
async def get_current(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, WeatherReading | None]:
    """Return the latest reading for each configured sensor in a single query.

    The frontend calls this once at startup (and after a WebSocket reconnect)
    for the card values, instead of downloading full histories.
    """
    # One `... WHERE parameter = ? ORDER BY timestamp DESC LIMIT 1` per sensor,
    # glued with UNION ALL: each branch is an index seek on
    # ix_weather_parameter_timestamp. (A `max(timestamp) GROUP BY parameter`
    # join reads every index entry instead: ~60x slower on a 30-day database.)
    if not settings.sensors:
        return {}
    per_sensor = [
        select(WeatherReading)
        .where(WeatherReading.parameter == parameter)
        .order_by(desc(WeatherReading.timestamp), desc(WeatherReading.id))
        .limit(1)
        .subquery()
        .select()
        for parameter in settings.sensors
    ]
    stmt = select(WeatherReading).from_statement(union_all(*per_sensor))
    result: dict[str, WeatherReading | None] = dict.fromkeys(settings.sensors)
    for row in (await db.execute(stmt)).scalars():
        result[row.parameter] = row
    return result


@router.get("/history/{parameter}", response_model=list[WeatherReadingOut])
async def get_history(
    parameter: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: Annotated[int, Query(ge=1, le=MAX_HISTORY_HOURS)] = DEFAULT_HISTORY_HOURS,
) -> Sequence[WeatherReading]:
    """Return reading history for the last `hours` hours (default 24, max 720).

    Only numeric sensors have a history (text/forecast rows can be 64 kB each).
    At most ``MAX_HISTORY_POINTS`` real rows are returned: a larger window is
    sampled at an even stride over its rows, always keeping the first and the
    last reading. One statement, so the count and the sample share a snapshot.
    """
    if parameter not in settings.sensors:
        raise HTTPException(status_code=400, detail="Invalid parameter")
    if settings.sensors[parameter].type is not SensorType.NUMERIC:
        raise HTTPException(
            status_code=400, detail="History is only available for numeric sensors"
        )

    since = datetime.now(UTC) - timedelta(hours=hours)
    order = (WeatherReading.timestamp, WeatherReading.id)
    numbered = (
        select(
            WeatherReading.id,
            func.row_number().over(order_by=order).label("rn"),
            func.count().over().label("total"),
        )
        .where(
            WeatherReading.parameter == parameter,
            WeatherReading.timestamp >= since,
        )
        .subquery()
    )
    # Integer ceil((total - 1) / (MAX - 1)); `//` renders as integer `/` on SQLite.
    # It fits at most MAX - 1 steps before the last row, so rows 1, 1 + stride,
    # ... plus the forced last row stay within the cap.
    stride = (numbered.c.total + (MAX_HISTORY_POINTS - 3)) // (MAX_HISTORY_POINTS - 1)
    # For total <= 1 the stride is 0 and `% 0` is NULL, but the first arm holds.
    sampled = select(numbered.c.id).where(
        or_(
            numbered.c.total <= MAX_HISTORY_POINTS,
            (numbered.c.rn - 1) % stride == 0,
            numbered.c.rn == numbered.c.total,
        )
    )
    stmt = select(WeatherReading).where(WeatherReading.id.in_(sampled)).order_by(*order)
    return (await db.execute(stmt)).scalars().all()


@router.get("/alerts", response_model=list[WeatherReadingOut])
async def get_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Sequence[WeatherReading]:
    """Return all currently-valid alert readings (valid_to > now), newest first."""
    alerts_key = settings.key_for_type(SensorType.ALERTS)
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
) -> SunOut:
    """Return the latest sun position reading."""
    row = await _latest(db, "sun")
    if row is None:
        return {"parameter": None, "value": None, "timestamp": None}
    return {
        "parameter": "sun",
        "value": row.value_str,
        "timestamp": row.timestamp.isoformat(),
    }


@router.get("/forecast")
async def get_forecast(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForecastOut:
    """Return the latest forecast data as parsed JSON with server timestamp."""
    forecast_key = settings.key_for_type(SensorType.FORECAST)
    row = None if forecast_key is None else await _latest(db, forecast_key)
    if row is None or row.value_str is None:
        return {"forecast": [], "timestamp": None}
    return {
        "forecast": json.loads(row.value_str),
        "timestamp": row.timestamp.isoformat(),
    }


@router.get("/analytics")
async def get_analytics() -> AnalyticsOut:
    """Return Umami analytics config if both host and ID are configured."""
    if settings.umami_host and settings.umami_id:
        return {"host": settings.umami_host, "id": settings.umami_id}
    return {}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket — push new readings to frontend clients.

    Browsers always send ``Origin``; a value outside the allowed list is a
    cross-site connection attempt and is refused. Non-browser clients without
    the header are accepted (the data is public and read-only). A close before
    ``accept()`` reaches the browser as a failed handshake (HTTP 403); the ASGI
    close codes only distinguish the reasons in logs and tests. At most
    ``MAX_WS_CONNECTIONS_PER_IP`` handlers run per client IPv4 address or IPv6
    /64 (``client_key``), and ``MAX_WS_CONNECTIONS`` in total.
    """
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        await websocket.close(code=WS_CLOSE_POLICY_VIOLATION)
        return

    key = client_key(websocket.scope)
    if (
        _open_ws_by_ip.total() >= MAX_WS_CONNECTIONS
        or _open_ws_by_ip[key] >= MAX_WS_CONNECTIONS_PER_IP
    ):
        await websocket.close(code=WS_CLOSE_TRY_AGAIN_LATER)
        return
    _open_ws_by_ip[key] += 1

    try:
        await manager.connect(websocket)
        while True:
            await websocket.receive_text()  # keep-alive / ping
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
        _open_ws_by_ip[key] -= 1
        if _open_ws_by_ip[key] <= 0:
            del _open_ws_by_ip[key]
