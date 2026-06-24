"""Tests for app.mqtt_client — MQTT listener, WebSocket manager."""

import json
from unittest.mock import AsyncMock, MagicMock

from freezegun import freeze_time
from sqlalchemy import text


def test_topic_parameter_map_contains_known_sensors() -> None:
    """TOPIC_PARAMETER_MAP includes all configured sensor topics."""
    from app.mqtt_client import TOPIC_PARAMETER_MAP  # ty: ignore[unresolved-import]

    assert "weather-dashboard/temperature" in TOPIC_PARAMETER_MAP
    assert TOPIC_PARAMETER_MAP["weather-dashboard/temperature"] == "temperature"
    assert "weather-dashboard/humidity" in TOPIC_PARAMETER_MAP


def test_topic_parameter_map_unknown_topic() -> None:
    """TOPIC_PARAMETER_MAP does not contain topics not in config."""
    from app.mqtt_client import TOPIC_PARAMETER_MAP  # ty: ignore[unresolved-import]

    assert "weather-dashboard/unknown" not in TOPIC_PARAMETER_MAP


class TestWebSocketManager:
    """Unit tests for WebSocketManager — connect, disconnect, broadcast."""

    async def test_connect_adds_connection(self) -> None:
        """Connect should accept the websocket and add it to active_connections."""
        from app.mqtt_client import WebSocketManager  # ty: ignore[unresolved-import]

        manager = WebSocketManager()
        ws = AsyncMock()
        await manager.connect(ws)
        assert ws in manager.active_connections
        ws.accept.assert_awaited_once()

    async def test_disconnect_removes_connection(self) -> None:
        """Disconnect should remove the websocket from active_connections."""
        from app.mqtt_client import WebSocketManager  # ty: ignore[unresolved-import]

        manager = WebSocketManager()
        ws = AsyncMock()
        await manager.connect(ws)
        manager.disconnect(ws)
        assert ws not in manager.active_connections

    async def test_broadcast_sends_to_all(self) -> None:
        """Broadcast should send the JSON message to every connected client."""
        from app.mqtt_client import WebSocketManager  # ty: ignore[unresolved-import]

        manager = WebSocketManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.broadcast({"parameter": "temperature", "value": 22.5})

        expected = json.dumps({"parameter": "temperature", "value": 22.5})
        ws1.send_text.assert_awaited_once_with(expected)
        ws2.send_text.assert_awaited_once_with(expected)

    async def test_broadcast_removes_dead_connections(self) -> None:
        """Broadcast should remove clients whose send_text raises an exception."""
        from app.mqtt_client import WebSocketManager  # ty: ignore[unresolved-import]

        manager = WebSocketManager()
        good_ws = AsyncMock()
        dead_ws = AsyncMock()
        dead_ws.send_text.side_effect = Exception("gone")
        await manager.connect(good_ws)
        await manager.connect(dead_ws)

        await manager.broadcast({"parameter": "temperature", "value": 22.5})

        assert good_ws in manager.active_connections
        assert dead_ws not in manager.active_connections


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_numeric_message(monkeypatch, db_engine) -> None:
    """A numeric MQTT message is persisted in the database."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/temperature")
    message.payload = json.dumps({"value": 22.5, "unit": "°C"}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT parameter, value, unit FROM weather_readings")
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "temperature"
    assert row[1] == 22.5
    assert row[2] == "°C"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_condition_message(monkeypatch, db_engine) -> None:
    """A condition MQTT message is persisted with value_str and icon."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/condition")
    message.payload = json.dumps(
        {"value": "sunny", "icon": "mdi:weather-sunny"}
    ).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT parameter, value, unit, value_str, icon FROM weather_readings")
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "condition"
    assert row[1] is None
    assert row[2] == ""
    assert row[3] == "sunny"
    assert row[4] == "mdi:weather-sunny"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_text_message(monkeypatch, db_engine) -> None:
    """A text-type MQTT message is persisted with value_str and no icon."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/air_quality")
    message.payload = json.dumps({"value": "bardzo dobra"}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT parameter, value, unit, value_str, icon FROM weather_readings")
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "air_quality"
    assert row[1] is None
    assert row[2] == ""
    assert row[3] == "bardzo dobra"
    assert row[4] == ""


async def test_process_unknown_topic_logs_warning(
    monkeypatch, caplog, db_engine
) -> None:
    """An MQTT message for an unknown topic is silently ignored."""
    import logging

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/unknown_sensor")
    message.payload = json.dumps({"value": 22.5}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM weather_readings"))
        count = result.scalar()
    assert count == 0


async def test_process_invalid_json_logs_warning(
    monkeypatch, caplog, db_engine
) -> None:
    """A malformed JSON payload logs a warning and does not persist."""
    import logging

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/temperature")
    message.payload = b"not-json"

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Payload parse error" in caplog.text
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM weather_readings"))
        count = result.scalar()
    assert count == 0


async def test_process_missing_value_logs_warning(
    monkeypatch, caplog, db_engine
) -> None:
    """An MQTT payload without a 'value' key logs a warning and skips persistence."""
    import logging

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/temperature")
    message.payload = json.dumps({"unit": "°C"}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Payload parse error" in caplog.text
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM weather_readings"))
        count = result.scalar()
    assert count == 0


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_numeric_broadcasts(monkeypatch, db_engine) -> None:
    """A numeric MQTT message broadcasts the reading via WebSocketManager."""
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    from app.mqtt_client import WebSocketManager  # ty: ignore[unresolved-import]

    ws = AsyncMock()

    import app.mqtt_client as mqtt_mod  # ty: ignore[unresolved-import]

    original_manager = mqtt_mod.manager
    test_manager = WebSocketManager()
    await test_manager.connect(ws)
    monkeypatch.setattr(mqtt_mod, "manager", test_manager)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/temperature")
    message.payload = json.dumps({"value": 22.5, "unit": "°C"}).encode()

    await mqtt_mod._process_mqtt_message(message)

    expected = json.dumps(
        {
            "parameter": "temperature",
            "value": 22.5,
            "unit": "°C",
            "timestamp": "2026-06-23T12:00:00+00:00",
        }
    )
    ws.send_text.assert_awaited_once_with(expected)

    monkeypatch.setattr(mqtt_mod, "manager", original_manager)
