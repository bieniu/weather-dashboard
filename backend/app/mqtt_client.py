"""MQTT client — subscribe to weather topics, save to DB and broadcast via WebSocket."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import aiomqtt

if TYPE_CHECKING:
    from fastapi import WebSocket

from .config import settings
from .database import SessionLocal
from .models import WeatherReading

VALID_ALERT_LEVELS = {"yellow", "orange", "red"}
MAX_ALERT_VALID_HOURS = 48

logger = logging.getLogger(__name__)


def _parse_alert_payload(payload: dict, now: datetime) -> tuple[str, str, datetime]:
    """Validate and extract alert fields from an MQTT payload."""
    value = str(payload["value"])[:100]
    level = str(payload["level"])[:20]
    if level not in VALID_ALERT_LEVELS:
        msg = f"Invalid alert level: {level}"
        raise ValueError(msg)
    valid_to = datetime.fromisoformat(payload["valid_to"])
    if valid_to.tzinfo is None:
        valid_to = valid_to.replace(tzinfo=UTC)
    max_valid = now + timedelta(hours=MAX_ALERT_VALID_HOURS)
    if valid_to <= now or valid_to > max_valid:
        msg = f"valid_to out of range: {valid_to}"
        raise ValueError(msg)
    return value, level, valid_to


TOPIC_PARAMETER_MAP: dict[str, str] = {
    f"{settings.topic_prefix}/{sensor}": sensor for sensor in settings.sensors
}


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        """Initialize empty connection list."""
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active list."""
        self.active_connections.remove(websocket)

    async def broadcast(self, data: dict[str, object]) -> None:
        """Broadcast JSON data to all connected clients."""
        message = json.dumps(data)
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except Exception:  # noqa: BLE001
                self.active_connections.remove(connection)


manager = WebSocketManager()


async def _process_mqtt_message(message: aiomqtt.Message) -> None:
    """Parse, persist and broadcast a single MQTT message."""
    topic = str(message.topic)
    parameter = TOPIC_PARAMETER_MAP.get(topic)
    if parameter is None:
        return  # unknown topic — ignore

    sensor_type = settings.sensors[parameter].type
    now = datetime.now(UTC)

    try:
        payload = json.loads(message.payload)
        if sensor_type == "alert":
            value_str, level, valid_to = _parse_alert_payload(payload, now)
            reading = WeatherReading(
                parameter=parameter,
                value_str=value_str,
                level=level,
                valid_to=valid_to,
                timestamp=now,
            )
        elif sensor_type in {"condition", "text"}:
            value_str = str(payload["value"])
            icon = str(payload.get("icon", "")) if sensor_type == "condition" else ""
            reading = WeatherReading(
                parameter=parameter, value_str=value_str, icon=icon, timestamp=now
            )
        else:
            value = float(payload["value"])
            unit = str(payload["unit"])
            reading = WeatherReading(
                parameter=parameter, value=value, unit=unit, timestamp=now
            )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Payload parse error on topic %s: %s", topic, e)
        return

    async with SessionLocal() as db:
        db.add(reading)
        await db.commit()

    if sensor_type == "alert":
        await manager.broadcast(
            {
                "parameter": parameter,
                "value": value_str,
                "valid_to": valid_to.isoformat(),
                "level": level,
                "timestamp": now.isoformat(),
            }
        )
    elif sensor_type in {"condition", "text"}:
        data: dict[str, object] = {
            "parameter": parameter,
            "value": value_str,
            "timestamp": now.isoformat(),
        }
        if sensor_type == "condition":
            data["icon"] = icon
        await manager.broadcast(data)
    else:
        await manager.broadcast(
            {
                "parameter": parameter,
                "value": value,
                "unit": unit,
                "timestamp": now.isoformat(),
            }
        )


async def mqtt_listener() -> None:
    """Listen for MQTT messages and process incoming readings."""
    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_broker,
                port=settings.mqtt_port,
                username=settings.mqtt_user,
                password=settings.mqtt_password,
            ) as client:
                await client.subscribe(f"{settings.topic_prefix}/#")
                logger.info(
                    "Connected to %s:%s",
                    settings.mqtt_broker,
                    settings.mqtt_port,
                )

                async for message in client.messages:
                    await _process_mqtt_message(message)

        except aiomqtt.MqttError as e:
            logger.warning("Connection error: %s. Retrying in 5s...", e)
            await asyncio.sleep(5)
