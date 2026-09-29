"""MQTT client — subscribe to weather topics, save to DB and broadcast via WebSocket."""

import asyncio
import json
import logging
import math
import random
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, NoReturn

import aiomqtt

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import WebSocket

from .config import SensorType, settings
from .database import SessionLocal
from .models import WeatherReading

VALID_ALERT_LEVELS = {"yellow", "orange", "red"}
MAX_ALERT_VALID_HOURS = 48
RECONNECT_BASE_SECONDS = 5
RECONNECT_MAX_SECONDS = 60
RECONNECT_JITTER = 0.2

# Payload hardening: anyone who can publish under the topic prefix could
# otherwise push multi-megabyte payloads that get stored for 30 days and
# fanned out to every WebSocket client.
MAX_PAYLOAD_BYTES = 64_000
MAX_VALUE_STR_LEN = 100  # WeatherReading.value_str is String(100)
MAX_ICON_LEN = 50  # WeatherReading.icon is String(50)
MAX_LEVEL_LEN = 20  # WeatherReading.level is String(20)
MAX_UNIT_LEN = 10  # WeatherReading.unit is String(10)
MAX_FORECAST_ITEMS = 20  # the frontend renders 5

# A client that stops reading (full TCP buffer) must not stall the MQTT ingest
# loop, which awaits every broadcast.
WS_SEND_TIMEOUT_SECONDS = 2.0
WS_CLOSE_TIMEOUT_SECONDS = 1.0

logger = logging.getLogger(__name__)


def _reject_json_constant(name: str) -> NoReturn:
    """``json.loads`` accepts NaN/Infinity by default; browsers' JSON.parse does not."""
    msg = f"Non-finite JSON constant: {name}"
    raise ValueError(msg)


def _load_json(raw: object) -> object:
    """Decode an MQTT payload, refusing non-text and oversized payloads early."""
    if not isinstance(raw, (bytes, bytearray, str)):
        msg = f"Unsupported payload type: {type(raw).__name__}"
        raise TypeError(msg)
    if len(raw) > MAX_PAYLOAD_BYTES:
        msg = f"Payload too large: {len(raw)} bytes"
        raise ValueError(msg)
    return json.loads(raw, parse_constant=_reject_json_constant)


# Everything a hostile payload can make the parsers raise. RecursionError comes
# from deeply nested JSON, OverflowError from datetime arithmetic on year 9999.
PAYLOAD_ERRORS = (
    json.JSONDecodeError,
    KeyError,
    ValueError,
    TypeError,
    RecursionError,
    OverflowError,
)


def _parse_json_object(raw: object) -> dict:
    """Decode a JSON object payload; anything else is a TypeError."""
    payload = _load_json(raw)
    if not isinstance(payload, dict):
        msg = f"Payload is not a JSON object: {type(payload).__name__}"
        raise TypeError(msg)
    return payload


def _finite_float(value: str | float) -> float:
    """Convert to float, rejecting NaN/inf (they are not valid JSON on broadcast)."""
    number = float(value)
    if not math.isfinite(number):
        msg = f"Non-finite value: {value!r}"
        raise ValueError(msg)
    return number


TOPIC_PARAMETER_MAP: dict[str, str] = {
    f"{settings.topic_prefix}/{sensor}": sensor for sensor in settings.sensors
}

SUN_TOPIC = f"{settings.topic_prefix}/sun"


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        """Initialize empty connection set."""
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection; a no-op if it is already gone."""
        self.active_connections.discard(websocket)

    async def _send(self, websocket: WebSocket, message: str) -> None:
        try:
            await asyncio.wait_for(
                websocket.send_text(message), WS_SEND_TIMEOUT_SECONDS
            )
        except Exception as err:  # noqa: BLE001 - closed, stalled or broken: drop it
            self.active_connections.discard(websocket)
            logger.info("Dropping WebSocket client after send failure: %r", err)
            with suppress(Exception):
                await asyncio.wait_for(
                    websocket.close(code=1011), WS_CLOSE_TIMEOUT_SECONDS
                )

    async def broadcast(self, data: dict[str, object]) -> None:
        """Send JSON data to all clients concurrently; slow clients are dropped."""
        message = json.dumps(data)
        connections = list(self.active_connections)
        if connections:
            await asyncio.gather(*(self._send(ws, message) for ws in connections))


manager = WebSocketManager()

SUN_VALUES = frozenset({"above_horizon", "below_horizon"})

# A parser turns one raw MQTT payload into the row to store and the message to
# broadcast, or raises one of PAYLOAD_ERRORS.
type Broadcast = dict[str, object]
type Parser = Callable[[object, str, datetime], tuple[WeatherReading, Broadcast]]


def _parse_numeric(
    raw: object, parameter: str, now: datetime
) -> tuple[WeatherReading, Broadcast]:
    payload = _parse_json_object(raw)
    value = _finite_float(payload["value"])
    unit = str(payload["unit"])[:MAX_UNIT_LEN]
    reading = WeatherReading(parameter=parameter, value=value, unit=unit, timestamp=now)
    return reading, {
        "parameter": parameter,
        "value": value,
        "unit": unit,
        "timestamp": now.isoformat(),
    }


def _parse_text(
    raw: object, parameter: str, now: datetime
) -> tuple[WeatherReading, Broadcast]:
    payload = _parse_json_object(raw)
    value = str(payload["value"])[:MAX_VALUE_STR_LEN]
    reading = WeatherReading(
        parameter=parameter, value_str=value, icon="", timestamp=now
    )
    return reading, {
        "parameter": parameter,
        "value": value,
        "timestamp": now.isoformat(),
    }


def _parse_condition(
    raw: object, parameter: str, now: datetime
) -> tuple[WeatherReading, Broadcast]:
    payload = _parse_json_object(raw)
    value = str(payload["value"])[:MAX_VALUE_STR_LEN]
    icon = str(payload.get("icon", ""))[:MAX_ICON_LEN]
    reading = WeatherReading(
        parameter=parameter, value_str=value, icon=icon, timestamp=now
    )
    return reading, {
        "parameter": parameter,
        "value": value,
        "timestamp": now.isoformat(),
        "icon": icon,
    }


def _parse_alerts(
    raw: object, parameter: str, now: datetime
) -> tuple[WeatherReading, Broadcast]:
    payload = _parse_json_object(raw)
    value = str(payload["value"])[:MAX_VALUE_STR_LEN]
    level_raw = payload.get("level")
    if level_raw is not None:
        level = str(level_raw)[:MAX_LEVEL_LEN]
        if level not in VALID_ALERT_LEVELS:
            msg = f"Invalid alert level: {level}"
            raise ValueError(msg)
    else:
        level = None
    valid_to = datetime.fromisoformat(payload["valid_to"])
    if valid_to.tzinfo is None:
        valid_to = valid_to.replace(tzinfo=UTC)
    else:
        valid_to = valid_to.astimezone(UTC)
    max_valid = now + timedelta(hours=MAX_ALERT_VALID_HOURS)
    if valid_to <= now:
        msg = f"valid_to out of range: {valid_to}"
        raise ValueError(msg)
    # IMGW hydro warnings send 9999-12-31T23:59:59+00:00 as an open-ended
    # sentinel meaning "no end date"; treat any valid_to beyond the max as
    # that sentinel and clamp it to just inside the range.
    if valid_to > max_valid:
        original_valid_to = valid_to
        valid_to = max_valid - timedelta(minutes=1)
        logger.info(
            "Alert %s valid_to %s is open-ended; clamped to %s",
            parameter,
            original_valid_to,
            valid_to,
        )
    reading = WeatherReading(
        parameter=parameter,
        value_str=value,
        level=level,
        valid_to=valid_to,
        timestamp=now,
    )
    return reading, {
        "parameter": parameter,
        "value": value,
        "valid_to": valid_to.isoformat(),
        "level": level,
        "timestamp": now.isoformat(),
    }


def _parse_forecast(
    raw: object, parameter: str, now: datetime
) -> tuple[WeatherReading, Broadcast]:
    payload = _load_json(raw)
    if not isinstance(payload, list):
        msg = "Forecast payload is not a list"
        raise TypeError(msg)
    if len(payload) > MAX_FORECAST_ITEMS:
        logger.info(
            "Forecast %s has %d items; keeping the first %d",
            parameter,
            len(payload),
            MAX_FORECAST_ITEMS,
        )
        payload = payload[:MAX_FORECAST_ITEMS]
    # 1e400 parses to inf without hitting parse_constant; allow_nan=False
    # turns any non-finite float anywhere in the list into a ValueError.
    encoded = json.dumps(payload, allow_nan=False)
    reading = WeatherReading(parameter=parameter, value_str=encoded, timestamp=now)
    return reading, {
        "parameter": parameter,
        "value": payload,
        "timestamp": now.isoformat(),
    }


def _parse_sun(
    raw: object, parameter: str, now: datetime
) -> tuple[WeatherReading, Broadcast]:
    payload = _parse_json_object(raw)
    value = str(payload["value"])
    if value not in SUN_VALUES:
        msg = f"Invalid sun value: {value[:MAX_VALUE_STR_LEN]!r}"
        raise ValueError(msg)
    reading = WeatherReading(parameter=parameter, value_str=value, timestamp=now)
    return reading, {
        "parameter": parameter,
        "value": value,
        "timestamp": now.isoformat(),
    }


PARSERS: dict[SensorType, Parser] = {
    SensorType.NUMERIC: _parse_numeric,
    SensorType.CONDITION: _parse_condition,
    SensorType.TEXT: _parse_text,
    SensorType.ALERTS: _parse_alerts,
    SensorType.FORECAST: _parse_forecast,
}


async def _persist_and_broadcast(reading: WeatherReading, data: Broadcast) -> None:
    async with SessionLocal() as db:
        db.add(reading)
        await db.commit()
    await manager.broadcast(data)


async def _process_mqtt_message(message: aiomqtt.Message) -> None:
    """Parse, persist and broadcast a single MQTT message."""
    topic = str(message.topic)
    if topic == SUN_TOPIC:
        parameter, parser = "sun", _parse_sun
    else:
        parameter = TOPIC_PARAMETER_MAP.get(topic)
        if parameter is None:
            return  # unknown topic — ignore
        parser = PARSERS[settings.sensors[parameter].type]

    now = datetime.now(UTC)
    try:
        reading, data = parser(message.payload, parameter, now)
    except PAYLOAD_ERRORS as e:
        logger.warning("Payload parse error on topic %s: %s", topic, e)
        return

    await _persist_and_broadcast(reading, data)


def _reconnect_delay(attempt: int) -> float:
    """Exponential backoff (5, 10, 20, 40, 60, 60, ... s) with ±20 % jitter."""
    base = min(RECONNECT_BASE_SECONDS * 2**attempt, RECONNECT_MAX_SECONDS)
    # S311: jitter only spreads reconnects; it is not security-sensitive randomness.
    jitter = random.uniform(-RECONNECT_JITTER, RECONNECT_JITTER)  # noqa: S311
    return base * (1 + jitter)


async def mqtt_listener() -> None:
    """Listen for MQTT messages and process incoming readings.

    Reconnects with capped exponential backoff after any failure, so a broker
    outage or an unexpected error never stops ingestion for good.
    """
    attempt = 0
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
                attempt = 0

                async for message in client.messages:
                    try:
                        await _process_mqtt_message(message)
                    except Exception:
                        logger.exception(
                            "Error processing message on topic %s", message.topic
                        )

        except aiomqtt.MqttError as e:
            logger.warning("MQTT connection error: %s", e)
        except Exception:
            logger.exception("Unexpected error in MQTT listener")

        delay = _reconnect_delay(attempt)
        attempt += 1
        logger.warning("Reconnecting to MQTT in %.0f s (attempt %d)", delay, attempt)
        await asyncio.sleep(delay)
