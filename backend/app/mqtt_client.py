"""MQTT client — subscribe to weather topics, save to DB and broadcast via WebSocket."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import aiomqtt

if TYPE_CHECKING:
    from fastapi import WebSocket

from .config import settings
from .database import SessionLocal
from .models import WeatherReading

logger = logging.getLogger(__name__)

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
    is_string = sensor_type in {"condition", "text"}
    now = datetime.now(UTC)

    try:
        payload = json.loads(message.payload)
        if is_string:
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

    if is_string:
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
