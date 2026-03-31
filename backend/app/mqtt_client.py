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
    "weather-dashboard/temperature": "temperature",
    "weather-dashboard/humidity": "humidity",
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
                await client.subscribe("weather-dashboard/#")
                print(f"[MQTT] Connected to {settings.mqtt_broker}:{settings.mqtt_port}")

                async for message in client.messages:
                    topic = str(message.topic)
                    parameter = TOPIC_PARAMETER_MAP.get(topic)
                    if parameter is None:
                        continue  # unknown topic — ignore

                    try:
                        payload = json.loads(message.payload)
                        value = float(payload["value"])
                        unit = str(payload["unit"])
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        print(f"[MQTT] Payload parse error on topic {topic}: {e}")
                        continue

                    # Save to database
                    async with SessionLocal() as db:
                        reading = WeatherReading(
                            parameter=parameter,
                            value=value,
                            unit=unit,
                            timestamp=datetime.now(timezone.utc),
                        )
                        db.add(reading)
                        await db.commit()
                        await db.refresh(reading)

                    # Broadcast to frontend via WebSocket
                    await manager.broadcast({
                        "parameter": parameter,
                        "value": value,
                        "unit": unit,
                        "timestamp": reading.timestamp.isoformat(),
                    })

        except aiomqtt.MqttError as e:
            print(f"[MQTT] Connection error: {e}. Retrying in 5s...")
            await asyncio.sleep(5)
