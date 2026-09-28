"""Tests for app.routers.weather — REST and WebSocket endpoints."""

from datetime import UTC, datetime

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.timeout(10)


async def test_get_sensors(async_client) -> None:
    """GET /api/weather/sensors returns sensor config from config.yaml."""
    resp = await async_client.get("/api/weather/sensors")
    assert resp.status_code == 200
    data = resp.json()
    assert "temperature" in data
    assert data["temperature"]["name"] == "Temperatura"
    assert data["temperature"]["unit"] == "°C"


async def test_get_current_empty_db(async_client) -> None:
    """GET /api/weather/current returns null values when DB is empty."""
    resp = await async_client.get("/api/weather/current")
    assert resp.status_code == 200
    data = resp.json()
    for value in data.values():
        assert value is None


async def test_get_current_with_data(async_client, seed_data) -> None:
    """GET /api/weather/current returns the latest reading per sensor."""
    resp = await async_client.get("/api/weather/current")
    assert resp.status_code == 200
    data = resp.json()

    assert data["temperature"] is not None
    assert data["temperature"]["parameter"] == "temperature"
    assert data["temperature"]["value"] == 24.0

    assert data["humidity"] is not None
    assert data["humidity"]["value"] == 55.0

    assert data["condition"] is not None
    assert data["condition"]["value_str"] == "sunny"


async def test_get_current_runs_a_single_query(
    async_client, db_engine, seed_data
) -> None:
    """/current fetches the latest row of every sensor with one SELECT, not N."""
    from sqlalchemy import event

    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", record)
    try:
        resp = await async_client.get("/api/weather/current")
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", record)

    assert resp.status_code == 200
    assert len(statements) == 1
    data = resp.json()
    assert data["temperature"]["value"] == 24.0
    assert data["condition"]["value_str"] == "sunny"
    assert data["pressure"] is None  # configured sensor without readings


async def test_get_current_prefers_newest_row_on_equal_timestamps(
    async_client, db_session
) -> None:
    """Two readings with the same timestamp: the later insert (higher id) wins."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    ts = datetime.now(UTC)
    db_session.add_all(
        [
            WeatherReading(parameter="humidity", value=50.0, unit="%", timestamp=ts),
            WeatherReading(parameter="humidity", value=51.0, unit="%", timestamp=ts),
        ]
    )
    await db_session.commit()

    resp = await async_client.get("/api/weather/current")
    assert resp.json()["humidity"]["value"] == 51.0


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_history(async_client, db_session) -> None:
    """GET /api/weather/history/{param} filters by hours and returns ordered results."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    import datetime as dt

    old = WeatherReading(
        parameter="temperature",
        value=10.0,
        unit="°C",
        timestamp=now - dt.timedelta(hours=24),
    )
    recent = WeatherReading(
        parameter="temperature",
        value=20.0,
        unit="°C",
        timestamp=now - dt.timedelta(hours=2),
    )
    db_session.add_all([old, recent])
    await db_session.commit()

    resp = await async_client.get("/api/weather/history/temperature?hours=12")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["value"] == 20.0

    resp = await async_client.get("/api/weather/history/temperature")
    assert resp.status_code == 200
    assert len(resp.json()) == 2  # default window is DEFAULT_HISTORY_HOURS (24 h)

    resp = await async_client.get("/api/weather/history/temperature?hours=48")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.parametrize(
    ("hours", "status"),
    [(0, 422), (-1, 422), (721, 422), (10**11, 422), (1, 200), (720, 200)],
)
async def test_get_history_hours_bounds(async_client, hours, status) -> None:
    """GET /history/{param} validates 1 <= hours <= 720 instead of erroring."""
    resp = await async_client.get(f"/api/weather/history/temperature?hours={hours}")
    assert resp.status_code == status


def _websocket_scope(origin: str | None = None) -> dict:
    headers = [] if origin is None else [(b"origin", origin.encode())]
    return {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "scheme": "ws",
        "path": "/api/weather/ws",
        "raw_path": b"/api/weather/ws",
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
        "subprotocols": [],
    }


async def test_websocket_endpoint_tracks_connection_lifecycle() -> None:
    """The WS endpoint registers the client on accept and removes it on close.

    Drives the ASGI app directly with a scripted websocket scope, so no
    TestClient/portal is needed and the assertions are deterministic.
    """
    from app.main import app  # ty: ignore[unresolved-import]
    from app.mqtt_client import manager  # ty: ignore[unresolved-import]

    incoming = [
        {"type": "websocket.connect"},
        {"type": "websocket.receive", "text": "ping"},
        {"type": "websocket.disconnect", "code": 1000},
    ]
    sent: list[dict] = []
    connections_at_receive: list[int] = []

    async def receive() -> dict:
        connections_at_receive.append(len(manager.active_connections))
        return incoming.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    await app(_websocket_scope(), receive, send)

    assert sent[0]["type"] == "websocket.accept"
    # connect handshake (0), then keep-alive text and disconnect while registered (1, 1)
    assert connections_at_receive == [0, 1, 1]
    assert manager.active_connections == set()


async def _handshake(scope: dict) -> list[dict]:
    """Drive the WS endpoint through connect + immediate disconnect; return sends."""
    from app.main import app  # ty: ignore[unresolved-import]

    incoming = [
        {"type": "websocket.connect"},
        {"type": "websocket.disconnect", "code": 1000},
    ]
    sent: list[dict] = []

    async def receive() -> dict:
        return incoming.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:8332", "http://127.0.0.1:8332", "http://localhost"],
)
async def test_websocket_accepts_allowed_origin(origin) -> None:
    """Origins from settings.allowed_origins complete the handshake."""
    sent = await _handshake(_websocket_scope(origin=origin))
    assert sent[0]["type"] == "websocket.accept"


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "http://localhost:9999", "null"],
)
async def test_websocket_rejects_foreign_origin(origin) -> None:
    """A cross-site Origin is refused with 1008 before the socket is accepted."""
    from app.mqtt_client import manager  # ty: ignore[unresolved-import]

    sent = await _handshake(_websocket_scope(origin=origin))
    assert sent == [{"type": "websocket.close", "code": 1008, "reason": ""}]
    assert manager.active_connections == set()


async def test_websocket_rejects_when_global_cap_reached(monkeypatch) -> None:
    """Beyond MAX_WS_CONNECTIONS the handshake is refused (ASGI close 1013)."""
    from app.routers import weather  # ty: ignore[unresolved-import]

    monkeypatch.setattr(weather, "MAX_WS_CONNECTIONS", 2)
    weather._open_ws_by_ip.update({"10.0.0.1": 1, "10.0.0.2": 1})

    sent = await _handshake(_websocket_scope())
    assert sent == [{"type": "websocket.close", "code": 1013, "reason": ""}]
    assert weather._open_ws_by_ip.total() == 2  # refused handshake not counted


async def test_websocket_rejects_when_per_ip_cap_reached(monkeypatch) -> None:
    """One IP cannot use more than MAX_WS_CONNECTIONS_PER_IP slots."""
    from app.routers import weather  # ty: ignore[unresolved-import]

    monkeypatch.setattr(weather, "MAX_WS_CONNECTIONS_PER_IP", 1)
    weather._open_ws_by_ip["127.0.0.1"] = 1  # the scope's client address

    refused = await _handshake(_websocket_scope())
    assert refused == [{"type": "websocket.close", "code": 1013, "reason": ""}]

    other = _websocket_scope()
    other["headers"] = [(b"cf-connecting-ip", b"203.0.113.9")]
    accepted = await _handshake(other)
    assert accepted[0]["type"] == "websocket.accept"
    assert weather._open_ws_by_ip == {"127.0.0.1": 1}  # released on disconnect


async def test_websocket_endpoint_unregisters_on_unexpected_error() -> None:
    """A failure other than WebSocketDisconnect still removes the connection."""
    from app.main import app  # ty: ignore[unresolved-import]
    from app.mqtt_client import manager  # ty: ignore[unresolved-import]

    incoming: list[dict] = [{"type": "websocket.connect"}]

    async def receive() -> dict:
        if incoming:
            return incoming.pop(0)
        msg = "transport failure"
        raise RuntimeError(msg)

    async def send(_message: dict) -> None:
        pass

    with pytest.raises(RuntimeError, match="transport failure"):
        await app(_websocket_scope(), receive, send)

    assert manager.active_connections == set()


async def test_get_history_invalid_parameter(async_client) -> None:
    """GET /api/weather/history/{param} with unknown sensor returns 400."""
    resp = await async_client.get("/api/weather/history/nonexistent")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid parameter"


async def test_get_sensors_structure(async_client) -> None:
    """GET /api/weather/sensors returns all expected keys with required fields."""
    resp = await async_client.get("/api/weather/sensors")
    data = resp.json()
    expected_sensors = {
        "alerts",
        "condition",
        "forecast",
        "air_quality",
        "temperature",
        "apparent_temperature",
        "humidity",
        "pressure",
        "pm1",
        "pm10",
        "pm25",
        "precipitation_probability",
        "water_level",
    }
    assert set(data.keys()) == expected_sensors
    for sensor in data.values():
        assert "name" in sensor
        assert "icon" in sensor
        assert "color" in sensor
        assert "type" in sensor
        assert "history_hours" in sensor
    assert data["water_level"]["history_hours"] == 24
    assert data["temperature"]["history_hours"] == 24


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_alerts_empty_db(async_client) -> None:
    """GET /api/weather/alerts returns empty list when no alerts exist."""
    resp = await async_client.get("/api/weather/alerts")
    assert resp.status_code == 200
    assert resp.json() == []


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_alerts_filters_expired(async_client, db_session) -> None:
    """GET /api/weather/alerts returns only valid alerts (valid_to > now)."""
    from datetime import timedelta

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    valid = WeatherReading(
        parameter="alerts",
        value_str="burze",
        level="yellow",
        valid_to=now + timedelta(hours=24),
        timestamp=now,
    )
    expired = WeatherReading(
        parameter="alerts",
        value_str="stare",
        level="red",
        valid_to=now - timedelta(hours=1),
        timestamp=now - timedelta(hours=2),
    )
    db_session.add_all([valid, expired])
    await db_session.commit()

    resp = await async_client.get("/api/weather/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["value_str"] == "burze"
    assert data[0]["level"] == "yellow"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_alerts_ordered_newest_first(async_client, db_session) -> None:
    """GET /api/weather/alerts returns valid alerts ordered by timestamp DESC."""
    from datetime import timedelta

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    older = WeatherReading(
        parameter="alerts",
        value_str="older",
        level="yellow",
        valid_to=now + timedelta(hours=24),
        timestamp=now - timedelta(hours=2),
    )
    newer = WeatherReading(
        parameter="alerts",
        value_str="newer",
        level="orange",
        valid_to=now + timedelta(hours=24),
        timestamp=now,
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    resp = await async_client.get("/api/weather/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["value_str"] == "newer"
    assert data[1]["value_str"] == "older"


async def test_get_sun_no_data(async_client) -> None:
    """GET /api/weather/sun returns null when no sun data exists."""
    resp = await async_client.get("/api/weather/sun")
    assert resp.status_code == 200
    data = resp.json()
    assert data["parameter"] is None
    assert data["value"] is None
    assert data["timestamp"] is None


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_sun_with_data(async_client, db_session) -> None:
    """GET /api/weather/sun returns the latest sun reading."""
    from datetime import UTC, datetime

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    older = WeatherReading(parameter="sun", value_str="below_horizon", timestamp=now)
    newer = WeatherReading(
        parameter="sun",
        value_str="above_horizon",
        timestamp=now,
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    resp = await async_client.get("/api/weather/sun")
    assert resp.status_code == 200
    data = resp.json()
    assert data["value"] == "above_horizon"
    assert data["timestamp"] == "2026-06-23T12:00:00+00:00"
    assert data["parameter"] == "sun"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_forecast_empty(async_client) -> None:
    """GET /api/weather/forecast returns empty forecast when no data exists."""
    resp = await async_client.get("/api/weather/forecast")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"forecast": [], "timestamp": None}


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_forecast_with_data(async_client, db_session) -> None:
    """GET /api/weather/forecast returns parsed forecast array."""
    import json

    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    forecast_data = [
        {
            "datetime": "2026-07-23T00:00:00+00:00",
            "condition": "cloudy",
            "temperature": 22.0,
            "precipitation": 0.0,
            "is_daytime": True,
        },
    ]
    now = datetime.now(UTC)
    reading = WeatherReading(
        parameter="forecast",
        value_str=json.dumps(forecast_data),
        timestamp=now,
    )
    db_session.add(reading)
    await db_session.commit()

    resp = await async_client.get("/api/weather/forecast")
    assert resp.status_code == 200
    data = resp.json()
    assert data["forecast"] == forecast_data
    assert data["timestamp"] == "2026-06-23T12:00:00+00:00"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_get_forecast_null_value_str(async_client, db_session) -> None:
    """GET /api/weather/forecast returns empty when value_str is null."""
    from app.models import WeatherReading  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    reading = WeatherReading(
        parameter="forecast",
        value_str=None,
        timestamp=now,
    )
    db_session.add(reading)
    await db_session.commit()

    resp = await async_client.get("/api/weather/forecast")
    assert resp.status_code == 200
    assert resp.json() == {"forecast": [], "timestamp": None}


async def test_get_forecast_no_forecast_sensor(async_client) -> None:
    """GET /api/weather/forecast returns empty when no forecast sensor configured."""
    from app.config import settings  # ty: ignore[unresolved-import]

    forecast_key = next(k for k, s in settings.sensors.items() if s.type == "forecast")
    sensor = settings.sensors.pop(forecast_key)
    try:
        resp = await async_client.get("/api/weather/forecast")
        assert resp.status_code == 200
        assert resp.json() == {"forecast": [], "timestamp": None}
    finally:
        settings.sensors[forecast_key] = sensor


async def test_get_alerts_no_alerts_sensor(async_client) -> None:
    """GET /api/weather/alerts returns [] when no alerts sensor configured."""
    from app.config import settings  # ty: ignore[unresolved-import]

    alerts_key = next(k for k, s in settings.sensors.items() if s.type == "alerts")
    sensor = settings.sensors.pop(alerts_key)
    try:
        resp = await async_client.get("/api/weather/alerts")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        settings.sensors[alerts_key] = sensor


async def test_get_analytics_disabled(async_client) -> None:
    """GET /api/weather/analytics returns {} when Umami is not configured."""
    resp = await async_client.get("/api/weather/analytics")
    assert resp.status_code == 200
    assert resp.json() == {}


async def test_get_analytics_enabled(async_client) -> None:
    """GET /api/weather/analytics returns host and id when configured."""
    from app.config import settings  # ty: ignore[unresolved-import]

    host = "https://umami.example.com"
    uid = "1234-4567-5678"
    settings.umami_host = host
    settings.umami_id = uid
    try:
        resp = await async_client.get("/api/weather/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"host": host, "id": uid}
    finally:
        settings.umami_host = None
        settings.umami_id = None
