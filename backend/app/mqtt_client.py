"""MQTT client — subscribe to weather topics, save to DB and broadcast via WebSocket."""

import asyncio
import json

import aiomqtt
from fastapi import WebSocket

from datetime import datetime, timezone

from .config import settings
from .database import SessionLocal
from .models import WeatherReading

TOPIC_PARAMETER_MAP: dict[str, str] = {
    f"{settings.topic_prefix}/{sensor}": sensor for sensor in settings.sensors
}


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
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
            except Exception:
                self.active_connections.remove(connection)


manager = WebSocketManager()


async def mqtt_listener() -> None:
    """Main MQTT client loop.

    Runs as an asyncio task in the FastAPI lifespan.
    Reconnects every 5 seconds on connection failure.
    """
    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_broker,
                port=settings.mqtt_port,
                username=settings.mqtt_user,
                password=settings.mqtt_password,
            ) as client:
                await client.subscribe(f"{settings.topic_prefix}/#")
                print(f"[MQTT] Connected to {settings.mqtt_broker}:{settings.mqtt_port}")

                async for message in client.messages:
                    topic = str(message.topic)
                    parameter = TOPIC_PARAMETER_MAP.get(topic)
                    if parameter is None:
                        continue  # unknown topic — ignore

                    try:
                        payload = json.loads(message.payload)
                    except json.JSONDecodeError as e:
                        print(f"[MQTT] Payload parse error on topic {topic}: {e}")
                        continue

                    sensor_config = settings.sensors.get(parameter)
                    is_condition = sensor_config and sensor_config.type == "condition"

                    try:
                        if is_condition:
                            value_str = str(payload["value"])
                            icon = str(payload.get("icon", ""))
                        else:
                            value = float(payload["value"])
                            unit = str(payload["unit"])
                    except (KeyError, ValueError) as e:
                        print(f"[MQTT] Payload parse error on topic {topic}: {e}")
                        continue

                    # Save to database
                    async with SessionLocal() as db:
                        if is_condition:
                            reading = WeatherReading(
                                parameter=parameter,
                                value=None,
                                unit="",
                                value_str=value_str,
                                icon=icon,
                                timestamp=datetime.now(timezone.utc),
                            )
                        else:
                            reading = WeatherReading(
                                parameter=parameter,
                                value=value,
                                unit=unit,
                                timestamp=datetime.now(timezone.utc),
                            )
                        db.add(reading)
                        await db.commit()
                        await db.refresh(reading)

                        # SQLite strips timezone info on read — re-attach UTC
                        if reading.timestamp.tzinfo is None:
                            reading.timestamp = reading.timestamp.replace(tzinfo=timezone.utc)

                    # Broadcast to frontend via WebSocket
                    if is_condition:
                        await manager.broadcast({
                            "parameter": parameter,
                            "value": value_str,
                            "icon": icon,
                            "timestamp": reading.timestamp.isoformat(),
                        })
                    else:
                        await manager.broadcast({
                            "parameter": parameter,
                            "value": value,
                            "unit": unit,
                            "timestamp": reading.timestamp.isoformat(),
                        })

        except aiomqtt.MqttError as e:
            print(f"[MQTT] Connection error: {e}. Retrying in 5s...")
            await asyncio.sleep(5)
