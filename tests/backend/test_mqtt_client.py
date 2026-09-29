"""Tests for app.mqtt_client — MQTT listener, WebSocket manager."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

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

    async def test_broadcast_drops_stalled_client_and_keeps_others(
        self, monkeypatch
    ) -> None:
        """A client that never finishes send_text is closed and dropped."""
        import asyncio

        from app import mqtt_client as mqtt_mod  # ty: ignore[unresolved-import]

        monkeypatch.setattr(mqtt_mod, "WS_SEND_TIMEOUT_SECONDS", 0.05)
        manager = mqtt_mod.WebSocketManager()
        fast_ws = AsyncMock()
        slow_ws = AsyncMock()

        async def hang(_message: str) -> None:
            await asyncio.sleep(10)

        slow_ws.send_text = hang
        await manager.connect(fast_ws)
        await manager.connect(slow_ws)

        await manager.broadcast({"parameter": "temperature", "value": 1.0})

        fast_ws.send_text.assert_awaited_once()
        assert fast_ws in manager.active_connections
        assert slow_ws not in manager.active_connections
        slow_ws.close.assert_awaited_once_with(code=1011)

    async def test_broadcast_sends_concurrently(self) -> None:
        """Sends run in parallel: each client waits for the other to start."""
        import asyncio

        from app.mqtt_client import WebSocketManager  # ty: ignore[unresolved-import]

        manager = WebSocketManager()
        both_started = asyncio.Event()
        started = 0

        async def send_text(_message: str) -> None:
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            # Sequential sends would time out here and drop the first client.
            await asyncio.wait_for(both_started.wait(), 1)

        ws1, ws2 = AsyncMock(), AsyncMock()
        ws1.send_text = send_text
        ws2.send_text = send_text
        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.broadcast({"parameter": "temperature", "value": 1.0})

        assert manager.active_connections == {ws1, ws2}

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


def make_message(topic: str, payload: object) -> SimpleNamespace:
    """Stand-in for aiomqtt.Message: only ``topic`` and ``payload`` are read."""
    return SimpleNamespace(topic=topic, payload=payload)


@pytest.fixture
def ingest(patched_session, db_engine) -> SimpleNamespace:
    """Bind ingest to the test DB; return a registered WebSocket and a row reader.

    ``rows()`` returns every stored reading as a raw DB tuple of
    ``(parameter, value, unit, value_str, icon, level, valid_to)``.
    """
    from app.mqtt_client import manager  # ty: ignore[unresolved-import]

    ws = AsyncMock()
    manager.active_connections.add(ws)

    async def rows() -> list[tuple]:
        async with db_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT parameter, value, unit, value_str, icon, level, valid_to "
                    "FROM weather_readings"
                )
            )
            return [tuple(row) for row in result.fetchall()]

    return SimpleNamespace(ws=ws, rows=rows)


NOW_ISO = "2026-06-23T12:00:00+00:00"
ALERT_VALID_TO = "2026-06-23 18:00:00+00:00"
ALERT_VALID_TO_DB = "2026-06-23 18:00:00.000000"


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
@pytest.mark.parametrize(
    ("topic", "payload", "expected_row", "expected_broadcast"),
    [
        (
            "weather-dashboard/temperature",
            {"value": 22.5, "unit": "°C"},
            ("temperature", 22.5, "°C", None, None, None, None),
            {
                "parameter": "temperature",
                "value": 22.5,
                "unit": "°C",
                "timestamp": NOW_ISO,
            },
        ),
        (
            "weather-dashboard/condition",
            {"value": "sunny", "icon": "mdi:weather-sunny"},
            ("condition", None, "", "sunny", "mdi:weather-sunny", None, None),
            {
                "parameter": "condition",
                "value": "sunny",
                "timestamp": NOW_ISO,
                "icon": "mdi:weather-sunny",
            },
        ),
        (
            "weather-dashboard/air_quality",
            {"value": "bardzo dobra"},
            ("air_quality", None, "", "bardzo dobra", "", None, None),
            {"parameter": "air_quality", "value": "bardzo dobra", "timestamp": NOW_ISO},
        ),
        (
            "weather-dashboard/alerts",
            {"value": "burze", "valid_to": ALERT_VALID_TO, "level": "yellow"},
            ("alerts", None, "", "burze", None, "yellow", ALERT_VALID_TO_DB),
            {
                "parameter": "alerts",
                "value": "burze",
                "valid_to": "2026-06-23T18:00:00+00:00",
                "level": "yellow",
                "timestamp": NOW_ISO,
            },
        ),
        (
            "weather-dashboard/alerts",
            {"value": "brak zagrożeń", "valid_to": ALERT_VALID_TO, "level": None},
            ("alerts", None, "", "brak zagrożeń", None, None, ALERT_VALID_TO_DB),
            {
                "parameter": "alerts",
                "value": "brak zagrożeń",
                "valid_to": "2026-06-23T18:00:00+00:00",
                "level": None,
                "timestamp": NOW_ISO,
            },
        ),
        (
            "weather-dashboard/alerts",
            {"value": "wiatr", "valid_to": "2026-06-23 18:00:00"},
            ("alerts", None, "", "wiatr", None, None, ALERT_VALID_TO_DB),
            {
                "parameter": "alerts",
                "value": "wiatr",
                "valid_to": "2026-06-23T18:00:00+00:00",
                "level": None,
                "timestamp": NOW_ISO,
            },
        ),
        (
            "weather-dashboard/alerts",
            {
                "value": "susza hydrologiczna",
                "valid_to": "9999-12-31T23:59:59+00:00",
                "level": None,
            },
            (
                "alerts",
                None,
                "",
                "susza hydrologiczna",
                None,
                None,
                "2026-06-25 11:59:00.000000",
            ),
            {
                "parameter": "alerts",
                "value": "susza hydrologiczna",
                "valid_to": "2026-06-25T11:59:00+00:00",
                "level": None,
                "timestamp": NOW_ISO,
            },
        ),
        (
            "weather-dashboard/sun",
            {"value": "above_horizon"},
            ("sun", None, "", "above_horizon", None, None, None),
            {"parameter": "sun", "value": "above_horizon", "timestamp": NOW_ISO},
        ),
        (
            "weather-dashboard/sun",
            {"value": "below_horizon"},
            ("sun", None, "", "below_horizon", None, None, None),
            {"parameter": "sun", "value": "below_horizon", "timestamp": NOW_ISO},
        ),
    ],
)
async def test_process_persists_and_broadcasts(
    ingest, topic, payload, expected_row, expected_broadcast
) -> None:
    """Each sensor type stores its columns and broadcasts its own message shape."""
    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(make_message(topic, json.dumps(payload).encode()))

    assert await ingest.rows() == [expected_row]
    ingest.ws.send_text.assert_awaited_once_with(json.dumps(expected_broadcast))


async def test_process_unknown_topic_is_silently_ignored(ingest, caplog) -> None:
    """A message on a topic without a configured sensor is dropped without a log."""
    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    message = make_message("weather-dashboard/unknown_sensor", b'{"value": 22.5}')
    with caplog.at_level("DEBUG"):
        await _process_mqtt_message(message)

    assert await ingest.rows() == []
    ingest.ws.send_text.assert_not_awaited()
    assert caplog.records == []


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
async def test_process_forecast_message(ingest) -> None:
    """A forecast is stored as a JSON array and broadcast as a parsed list."""
    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    await _process_mqtt_message(
        make_message(
            "weather-dashboard/forecast", json.dumps(FORECAST_PAYLOAD).encode()
        )
    )

    [row] = await ingest.rows()
    assert row[0] == "forecast"
    assert json.loads(row[3]) == FORECAST_PAYLOAD
    expected = {
        "parameter": "forecast",
        "value": FORECAST_PAYLOAD,
        "timestamp": NOW_ISO,
    }
    ingest.ws.send_text.assert_awaited_once_with(json.dumps(expected))


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


@freeze_time("2026-06-23 12:00:00", tz_offset=0)
@pytest.mark.parametrize(
    ("topic", "payload", "expected_log"),
    [
        ("weather-dashboard/temperature", b"not-json", "Payload parse error"),
        ("weather-dashboard/temperature", b'{"unit": "C"}', "Payload parse error"),
        ("weather-dashboard/temperature", b"5", "not a JSON object"),
        ("weather-dashboard/temperature", b"[]", "not a JSON object"),
        ("weather-dashboard/temperature", b"null", "not a JSON object"),
        (
            "weather-dashboard/temperature",
            b'{"value": "nan", "unit": "C"}',
            "Non-finite",
        ),
        (
            "weather-dashboard/temperature",
            b'{"value": "inf", "unit": "C"}',
            "Non-finite",
        ),
        ("weather-dashboard/temperature", b'{"value": NaN, "unit": "C"}', "Non-finite"),
        (
            "weather-dashboard/temperature",
            b'{"value": 1e400, "unit": "C"}',
            "Non-finite",
        ),
        ("weather-dashboard/temperature", b'{"value": [1], "unit": "C"}', "float()"),
        ("weather-dashboard/temperature", b"[" * 60_000, "Payload parse error"),
        ("weather-dashboard/condition", b'"sunny"', "not a JSON object"),
        ("weather-dashboard/alerts", b"[]", "not a JSON object"),
        (
            "weather-dashboard/alerts",
            b'{"value": "x", "valid_to": "2026-06-23 18:00:00+00:00", "level": "no"}',
            "Invalid alert level",
        ),
        (
            "weather-dashboard/alerts",
            b'{"value": "x", "valid_to": "2026-06-22 12:00:00+00:00", "level": "red"}',
            "valid_to out of range",
        ),
        (
            "weather-dashboard/alerts",
            b'{"value": "x", "valid_to": "9999-12-31T23:59:59-14:00"}',
            "Payload parse error",
        ),
        ("weather-dashboard/forecast", b"not-json", "Payload parse error"),
        ("weather-dashboard/forecast", b"5", "not a list"),
        ("weather-dashboard/forecast", b'{"value": "x"}', "not a list"),
        ("weather-dashboard/forecast", b'[{"t": NaN}]', "Non-finite"),
        ("weather-dashboard/forecast", b'[{"t": Infinity}]', "Non-finite"),
        ("weather-dashboard/forecast", b'[{"t": 1e400}]', "Out of range float"),
        ("weather-dashboard/sun", b"[]", "not a JSON object"),
        ("weather-dashboard/sun", b'{"value": null}', "Invalid sun value"),
        ("weather-dashboard/sun", b'{"value": "invalid"}', "Invalid sun value"),
        ("weather-dashboard/sun", b'{"foo": "bar"}', "Payload parse error"),
        ("weather-dashboard/temperature", None, "Unsupported payload type"),
    ],
)
async def test_process_rejects_malformed_payloads(
    ingest, caplog, topic, payload, expected_log
) -> None:
    """Malformed, non-finite, deeply nested or wrongly typed payloads are dropped."""
    from app.mqtt_client import _process_mqtt_message  # ty: ignore[unresolved-import]

    with caplog.at_level("WARNING"):
        await _process_mqtt_message(make_message(topic, payload))

    assert await ingest.rows() == []
    ingest.ws.send_text.assert_not_awaited()
    assert expected_log in caplog.text
    assert f"Payload parse error on topic {topic}" in caplog.text  # one line
    assert len(caplog.records) == 1
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize(
    "topic",
    [
        "weather-dashboard/temperature",
        "weather-dashboard/forecast",
        "weather-dashboard/sun",
    ],
)
async def test_process_rejects_oversized_payload(ingest, caplog, topic) -> None:
    """Payloads above MAX_PAYLOAD_BYTES are dropped before JSON decoding."""
    from app.mqtt_client import (  # ty: ignore[unresolved-import]
        MAX_PAYLOAD_BYTES,
        _process_mqtt_message,
    )

    padding = "x" * (MAX_PAYLOAD_BYTES + 1)
    payload = json.dumps({"value": 1, "unit": "C", "pad": padding}).encode()

    with caplog.at_level("WARNING"):
        await _process_mqtt_message(make_message(topic, payload))

    assert await ingest.rows() == []
    ingest.ws.send_text.assert_not_awaited()
    assert "Payload too large" in caplog.text


async def test_process_truncates_text_and_unit_to_column_width(ingest) -> None:
    """Over-long strings are cut to the column width instead of stored verbatim."""
    from app.mqtt_client import (  # ty: ignore[unresolved-import]
        MAX_UNIT_LEN,
        MAX_VALUE_STR_LEN,
        _process_mqtt_message,
    )

    await _process_mqtt_message(
        make_message(
            "weather-dashboard/air_quality",
            json.dumps({"value": "a" * 500}).encode(),
        )
    )
    await _process_mqtt_message(
        make_message(
            "weather-dashboard/temperature",
            json.dumps({"value": 1.5, "unit": "u" * 50}).encode(),
        )
    )

    sent = [json.loads(call.args[0]) for call in ingest.ws.send_text.await_args_list]
    assert len(sent[0]["value"]) == MAX_VALUE_STR_LEN
    assert len(sent[1]["unit"]) == MAX_UNIT_LEN


async def test_process_forecast_keeps_only_first_items(ingest, caplog) -> None:
    """A forecast longer than MAX_FORECAST_ITEMS is truncated, not rejected."""
    from app.mqtt_client import (  # ty: ignore[unresolved-import]
        MAX_FORECAST_ITEMS,
        _process_mqtt_message,
    )

    items = [{"datetime": f"2026-06-{i % 28 + 1:02d}"} for i in range(50)]

    with caplog.at_level("INFO"):
        await _process_mqtt_message(
            make_message("weather-dashboard/forecast", json.dumps(items).encode())
        )

    assert (
        f"Forecast forecast has 50 items; keeping the first {MAX_FORECAST_ITEMS}"
        in caplog.text
    )
    broadcast = json.loads(ingest.ws.send_text.await_args.args[0])
    assert len(broadcast["value"]) == MAX_FORECAST_ITEMS
    [row] = await ingest.rows()
    assert len(json.loads(row[3])) == MAX_FORECAST_ITEMS


def test_every_sensor_type_has_a_parser() -> None:
    """Adding a SensorType member without a parser would raise KeyError at runtime."""
    from app.config import SensorType  # ty: ignore[unresolved-import]
    from app.mqtt_client import PARSERS  # ty: ignore[unresolved-import]

    assert set(PARSERS) == set(SensorType)
