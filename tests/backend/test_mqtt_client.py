"""Tests for app.mqtt_client — MQTT listener, WebSocket manager."""

import json
from unittest.mock import AsyncMock, MagicMock

from freezegun import freeze_time
from sqlalchemy import text


def test_topic_parameter_map_contains_known_sensors() -> None:
    from app.mqtt_client import TOPIC_PARAMETER_MAP

    assert "weather-dashboard/temperature" in TOPIC_PARAMETER_MAP
    assert TOPIC_PARAMETER_MAP["weather-dashboard/temperature"] == "temperature"
    assert "weather-dashboard/humidity" in TOPIC_PARAMETER_MAP


def test_topic_parameter_map_unknown_topic() -> None:
    from app.mqtt_client import TOPIC_PARAMETER_MAP

    assert "weather-dashboard/unknown" not in TOPIC_PARAMETER_MAP


class TestWebSocketManager:
    async def test_connect_adds_connection(self) -> None:
        from app.mqtt_client import WebSocketManager

        manager = WebSocketManager()
        ws = AsyncMock()
        await manager.connect(ws)
        assert ws in manager.active_connections
        ws.accept.assert_awaited_once()

    async def test_disconnect_removes_connection(self) -> None:
        from app.mqtt_client import WebSocketManager

        manager = WebSocketManager()
        ws = AsyncMock()
        await manager.connect(ws)
        manager.disconnect(ws)
        assert ws not in manager.active_connections

    async def test_broadcast_sends_to_all(self) -> None:
        from app.mqtt_client import WebSocketManager

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
        from app.mqtt_client import WebSocketManager

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
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/temperature")
    message.payload = json.dumps({"value": 22.5, "unit": "°C"}).encode()

    from app.mqtt_client import _process_mqtt_message

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

    from app.mqtt_client import _process_mqtt_message

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


async def test_process_unknown_topic_logs_warning(
    monkeypatch, caplog, db_engine
) -> None:
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

    from app.mqtt_client import _process_mqtt_message

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    # No DB writes for unknown topics
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM weather_readings"))
        count = result.scalar()
    assert count == 0


async def test_process_invalid_json_logs_warning(
    monkeypatch, caplog, db_engine
) -> None:
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

    from app.mqtt_client import _process_mqtt_message

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

    from app.mqtt_client import _process_mqtt_message

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Payload parse error" in caplog.text
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM weather_readings"))
        count = result.scalar()
    assert count == 0


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_numeric_broadcasts(monkeypatch, db_engine) -> None:
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    from app.mqtt_client import WebSocketManager

    ws = AsyncMock()

    # Patch the module-level manager
    import app.mqtt_client as mqtt_mod

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

    # Restore original manager
    monkeypatch.setattr(mqtt_mod, "manager", original_manager)
