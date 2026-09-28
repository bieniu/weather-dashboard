"""Tests for app.mqtt_client — MQTT listener, WebSocket manager."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
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

    async def test_disconnect_is_idempotent(self) -> None:
        """Disconnecting a client already dropped by broadcast must not raise."""
        from app.mqtt_client import WebSocketManager  # ty: ignore[unresolved-import]

        manager = WebSocketManager()
        dead_ws = AsyncMock()
        dead_ws.send_text.side_effect = Exception("gone")
        await manager.connect(dead_ws)
        await manager.broadcast({"parameter": "temperature", "value": 22.5})

        manager.disconnect(dead_ws)
        manager.disconnect(dead_ws)
        assert manager.active_connections == set()


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
async def test_process_alert_message(monkeypatch, db_engine) -> None:
    """An alert MQTT message is persisted with value_str, level, valid_to."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/alerts")
    message.payload = json.dumps(
        {
            "value": "burze",
            "valid_to": "2026-06-23 18:00:00+00:00",
            "level": "yellow",
        }
    ).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT parameter, value, unit, value_str, level, valid_to "
                "FROM weather_readings"
            )
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "alerts"
    assert row[1] is None
    assert row[2] == ""
    assert row[3] == "burze"
    assert row[4] == "yellow"
    assert row[5] is not None


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_alert_null_level(monkeypatch, db_engine) -> None:
    """An alert with null level is persisted with level=None."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/alerts")
    message.payload = json.dumps(
        {
            "value": "brak zagrożeń",
            "valid_to": "2026-06-23 18:00:00+00:00",
            "level": None,
        }
    ).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT parameter, value, unit, value_str, level, valid_to "
                "FROM weather_readings"
            )
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "alerts"
    assert row[1] is None
    assert row[2] == ""
    assert row[3] == "brak zagrożeń"
    assert row[4] is None
    assert row[5] is not None


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_alert_invalid_level(monkeypatch, caplog, db_engine) -> None:
    """An alert with invalid level is rejected and not persisted."""
    import logging

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/alerts")
    message.payload = json.dumps(
        {
            "value": "test",
            "valid_to": "2026-06-23 18:00:00+00:00",
            "level": "invalid_level",
        }
    ).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Payload parse error" in caplog.text
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM weather_readings"))
        count = result.scalar()
    assert count == 0


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_alert_expired_valid_to(monkeypatch, caplog, db_engine) -> None:
    """An alert with valid_to in the past is rejected."""
    import logging

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/alerts")
    message.payload = json.dumps(
        {
            "value": "test",
            "valid_to": "2026-06-22 12:00:00+00:00",
            "level": "red",
        }
    ).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Payload parse error" in caplog.text
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM weather_readings"))
        count = result.scalar()
    assert count == 0


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_alert_broadcasts(monkeypatch, db_engine) -> None:
    """An alert MQTT message broadcasts with level, valid_to, value."""
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
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/alerts")
    message.payload = json.dumps(
        {
            "value": "burze",
            "valid_to": "2026-06-23 18:00:00+00:00",
            "level": "yellow",
        }
    ).encode()

    await mqtt_mod._process_mqtt_message(message)

    expected = json.dumps(
        {
            "parameter": "alerts",
            "value": "burze",
            "valid_to": "2026-06-23T18:00:00+00:00",
            "level": "yellow",
            "timestamp": "2026-06-23T12:00:00+00:00",
        }
    )
    ws.send_text.assert_awaited_once_with(expected)

    monkeypatch.setattr(mqtt_mod, "manager", original_manager)


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


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_sun_message_broadcasts(monkeypatch, db_engine) -> None:
    """A sun MQTT message broadcasts the sun position via WebSocket."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    from app.mqtt_client import (  # ty: ignore[unresolved-import]
        WebSocketManager,
        sun_state,
    )

    ws = AsyncMock()

    import app.mqtt_client as mqtt_mod  # ty: ignore[unresolved-import]

    original_manager = mqtt_mod.manager
    test_manager = WebSocketManager()
    await test_manager.connect(ws)
    monkeypatch.setattr(mqtt_mod, "manager", test_manager)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/sun")
    message.payload = json.dumps({"value": "above_horizon"}).encode()

    await mqtt_mod._process_mqtt_message(message)

    assert sun_state["value"] == "above_horizon"
    expected = json.dumps(
        {
            "parameter": "sun",
            "value": "above_horizon",
            "timestamp": "2026-06-23T12:00:00+00:00",
        }
    )
    ws.send_text.assert_awaited_once_with(expected)

    monkeypatch.setattr(mqtt_mod, "manager", original_manager)


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_sun_message_below_horizon(monkeypatch, db_engine) -> None:
    """A sun MQTT message with below_horizon broadcasts correctly."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    from app.mqtt_client import (  # ty: ignore[unresolved-import]
        WebSocketManager,
        sun_state,
    )

    ws = AsyncMock()

    import app.mqtt_client as mqtt_mod  # ty: ignore[unresolved-import]

    original_manager = mqtt_mod.manager
    test_manager = WebSocketManager()
    await test_manager.connect(ws)
    monkeypatch.setattr(mqtt_mod, "manager", test_manager)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/sun")
    message.payload = json.dumps({"value": "below_horizon"}).encode()

    await mqtt_mod._process_mqtt_message(message)

    assert sun_state["value"] == "below_horizon"
    expected = json.dumps(
        {
            "parameter": "sun",
            "value": "below_horizon",
            "timestamp": "2026-06-23T12:00:00+00:00",
        }
    )
    ws.send_text.assert_awaited_once_with(expected)

    monkeypatch.setattr(mqtt_mod, "manager", original_manager)


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_sun_message_persisted(monkeypatch, db_engine) -> None:
    """A sun MQTT message is persisted to the database."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/sun")
    message.payload = json.dumps({"value": "above_horizon"}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT parameter, value_str FROM weather_readings")
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "sun"
    assert row[1] == "above_horizon"


async def test_load_sun_state_from_db(monkeypatch, db_engine) -> None:
    """_load_sun_state reads the latest sun state from the database."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    from app.mqtt_client import (  # ty: ignore[unresolved-import]
        _load_sun_state,
        sun_state,
    )

    now = datetime.now(UTC)
    async with db_engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO weather_readings (parameter, value_str, unit, timestamp) "
                "VALUES (:param, :val, :unit, :ts)"
            ),
            {
                "param": "sun",
                "val": "below_horizon",
                "unit": "",
                "ts": now - timedelta(hours=1),
            },
        )
        await conn.execute(
            text(
                "INSERT INTO weather_readings (parameter, value_str, unit, timestamp) "
                "VALUES (:param, :val, :unit, :ts)"
            ),
            {"param": "sun", "val": "above_horizon", "unit": "", "ts": now},
        )
        await conn.commit()

    assert sun_state["value"] is None
    await _load_sun_state()
    assert sun_state["value"] == "above_horizon"


async def test_load_sun_state_no_data(monkeypatch, db_engine) -> None:
    """_load_sun_state does not overwrite in-memory value when DB is empty."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    from app.mqtt_client import (  # ty: ignore[unresolved-import]
        _load_sun_state,
        sun_state,
    )

    sun_state["value"] = "above_horizon"
    await _load_sun_state()
    assert sun_state["value"] == "above_horizon"


async def test_process_sun_invalid_value(monkeypatch, caplog) -> None:
    """A sun MQTT message with invalid value is rejected."""
    import logging

    from app.mqtt_client import sun_state  # ty: ignore[unresolved-import]

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/sun")
    message.payload = json.dumps({"value": "invalid"}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Invalid sun value" in caplog.text
    assert sun_state["value"] is None


async def test_process_sun_missing_value(monkeypatch, caplog) -> None:
    """A sun MQTT message without value key is rejected."""
    import logging

    from app.mqtt_client import sun_state  # ty: ignore[unresolved-import]

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/sun")
    message.payload = json.dumps({"foo": "bar"}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Payload parse error" in caplog.text
    assert sun_state["value"] is None


FORECAST_PAYLOAD = [
    {
        "datetime": "2026-07-22T00:00:00+00:00",
        "is_daytime": True,
        "condition": "cloudy",
        "temperature": 23.1,
        "precipitation": 0.0,
        "cloud_coverage": 75,
    },
    {
        "datetime": "2026-07-23T00:00:00+00:00",
        "is_daytime": False,
        "condition": "rainy",
        "temperature": 20.5,
        "precipitation": 0.1,
        "cloud_coverage": 90,
    },
    {
        "datetime": "2026-07-23T00:00:00+00:00",
        "is_daytime": True,
        "condition": "partlycloudy",
        "temperature": 20.2,
        "precipitation": 1.6,
        "cloud_coverage": 50,
    },
    {
        "datetime": "2026-07-24T00:00:00+00:00",
        "is_daytime": False,
        "condition": "rainy",
        "temperature": 17.9,
        "precipitation": 0.6,
        "cloud_coverage": 85,
    },
    {
        "datetime": "2026-07-24T00:00:00+00:00",
        "is_daytime": True,
        "condition": "rainy",
        "temperature": 21.7,
        "precipitation": 2.0,
        "cloud_coverage": 60,
    },
    {
        "datetime": "2026-07-25T00:00:00+00:00",
        "is_daytime": False,
        "condition": "partlycloudy",
        "temperature": 20.3,
        "precipitation": 0.0,
        "cloud_coverage": 30,
    },
]


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_forecast_message_persisted(monkeypatch, db_engine) -> None:
    """A forecast MQTT message is persisted with value_str containing the JSON array."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/forecast")
    message.payload = json.dumps(FORECAST_PAYLOAD).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(message)

    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT parameter, value_str FROM weather_readings")
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "forecast"
    assert json.loads(row[1]) == FORECAST_PAYLOAD


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
async def test_process_forecast_message_broadcasts(monkeypatch, db_engine) -> None:
    """A forecast MQTT message broadcasts the forecast array via WebSocketManager."""
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
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/forecast")
    message.payload = json.dumps(FORECAST_PAYLOAD).encode()

    await mqtt_mod._process_mqtt_message(message)

    expected = json.dumps(
        {
            "parameter": "forecast",
            "value": FORECAST_PAYLOAD,
            "timestamp": "2026-06-23T12:00:00+00:00",
        }
    )
    ws.send_text.assert_awaited_once_with(expected)

    monkeypatch.setattr(mqtt_mod, "manager", original_manager)


async def test_process_forecast_invalid_payload_not_a_list(monkeypatch, caplog) -> None:
    """A forecast payload that is not a list is rejected."""
    import logging

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/forecast")
    message.payload = json.dumps({"value": "not-a-list"}).encode()

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert (
        "Forecast payload on topic weather-dashboard/forecast is not a list"
        in caplog.text
    )


async def test_process_forecast_invalid_json(monkeypatch, caplog) -> None:
    """A forecast payload with invalid JSON is rejected."""
    import logging

    message = MagicMock()
    message.topic = MagicMock()
    message.topic.__str__ = MagicMock(return_value="weather-dashboard/forecast")
    message.payload = b"not-json"

    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level(logging.WARNING):
        await _process_mqtt_message(message)

    assert "Payload parse error" in caplog.text


@pytest.mark.parametrize(
    ("attempt", "expected_base"),
    [(0, 5), (1, 10), (2, 20), (3, 40), (4, 60), (10, 60)],
)
def test_reconnect_delay_backs_off_with_cap(attempt, expected_base) -> None:
    """Delay doubles from 5 s, caps at 60 s, and stays within ±20 % jitter."""
    from app.mqtt_client import _reconnect_delay  # ty: ignore[unresolved-import]

    delay = _reconnect_delay(attempt)
    assert expected_base * 0.8 <= delay <= expected_base * 1.2


@pytest.fixture
def listener_env(monkeypatch):
    """Stub aiomqtt.Client and asyncio.sleep; stop the loop after N sleeps."""
    import asyncio

    from app import mqtt_client as mqtt_mod  # ty: ignore[unresolved-import]

    sleeps: list[float] = []

    def install(client_factory, stop_after: int) -> None:
        monkeypatch.setattr(mqtt_mod.aiomqtt, "Client", client_factory)

        async def mock_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            if len(sleeps) >= stop_after:
                msg = "break loop"
                raise asyncio.CancelledError(msg)

        monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    return sleeps, install


@pytest.mark.parametrize(
    ("error", "expected_log"),
    [
        ("mqtt", "MQTT connection error"),
        ("runtime", "Unexpected error in MQTT listener"),
    ],
)
async def test_mqtt_listener_retries_with_growing_delay(
    listener_env, caplog, error, expected_log
) -> None:
    """Both MqttError and unexpected errors are logged and retried with backoff."""
    import asyncio
    from contextlib import suppress

    import aiomqtt
    from app.mqtt_client import mqtt_listener  # ty: ignore[unresolved-import]

    class FailingClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            if error == "mqtt":
                msg = "refused"
                raise aiomqtt.MqttError(msg)
            msg = "unexpected"
            raise RuntimeError(msg)

        async def __aexit__(self, *_exc):
            return False

    sleeps, install = listener_env
    install(FailingClient, stop_after=3)

    with caplog.at_level("WARNING"), suppress(asyncio.CancelledError):
        await mqtt_listener()

    assert len(sleeps) == 3
    assert sleeps[0] < sleeps[1] < sleeps[2]
    assert sleeps[2] <= 20 * 1.2
    assert expected_log in caplog.text
    assert "Reconnecting to MQTT in" in caplog.text


async def test_mqtt_listener_resets_backoff_after_connect(listener_env) -> None:
    """A successful connection resets the attempt counter to the base delay."""
    import asyncio
    from contextlib import suppress

    import aiomqtt
    from app.mqtt_client import mqtt_listener  # ty: ignore[unresolved-import]

    calls = {"n": 0}

    class EmptyMessages:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class FlakyClient:
        """Fails twice, connects once (no messages), then fails again."""

        def __init__(self, **_kwargs) -> None:
            self.messages = EmptyMessages()

        async def __aenter__(self):
            calls["n"] += 1
            if calls["n"] == 3:
                return self
            msg = "refused"
            raise aiomqtt.MqttError(msg)

        async def __aexit__(self, *_exc):
            return False

        async def subscribe(self, _topic: str) -> None:
            pass

    sleeps, install = listener_env
    install(FlakyClient, stop_after=4)

    with suppress(asyncio.CancelledError):
        await mqtt_listener()

    # attempts 0, 1 fail -> ~5 s, ~10 s; attempt resets on connect -> ~5 s, then ~10 s
    assert len(sleeps) == 4
    assert sleeps[2] < sleeps[1]
    assert 5 * 0.8 <= sleeps[2] <= 5 * 1.2
