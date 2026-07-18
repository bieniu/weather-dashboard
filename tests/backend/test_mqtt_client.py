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

    from app.mqtt_client import WebSocketManager, sun_state  # ty: ignore[unresolved-import]

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
    expected = json.dumps({
        "parameter": "sun",
        "value": "above_horizon",
        "timestamp": "2026-06-23T12:00:00+00:00",
    })
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

    from app.mqtt_client import WebSocketManager, sun_state  # ty: ignore[unresolved-import]

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
    expected = json.dumps({
        "parameter": "sun",
        "value": "below_horizon",
        "timestamp": "2026-06-23T12:00:00+00:00",
    })
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

    from app.mqtt_client import _load_sun_state, sun_state  # ty: ignore[unresolved-import]

    now = datetime.now(UTC)
    async with db_engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO weather_readings (parameter, value_str, unit, timestamp) "
                "VALUES (:param, :val, :unit, :ts)"
            ),
            {"param": "sun", "val": "below_horizon", "unit": "", "ts": now - timedelta(hours=1)},
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
    """_load_sun_state leaves sun_state as None when no data exists."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_session_factory = async_sessionmaker(
        db_engine, expire_on_commit=False, class_=AsyncSession
    )
    monkeypatch.setattr("app.mqtt_client.SessionLocal", test_session_factory)

    from app.mqtt_client import _load_sun_state, sun_state  # ty: ignore[unresolved-import]

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
