# backend/app/

## Responsibility

Application Core — asynchronous FastAPI server acting as the ingestion, persistence, and distribution layer for real-time environmental sensor data. Receives sensor readings via MQTT, stores them in SQLite, serves historical data via REST, and pushes live updates to browser clients via WebSocket.

## Design

- **FastAPI async server** with `asynccontextmanager`-based lifespan for startup/shutdown orchestration (DB init, MQTT connection, background tasks).
- **Pydantic Settings (BaseSettings)** loads configuration from `.env` file at module level; `SensorConfig` objects are derived from `config.yaml` and merged into the settings singleton. `SensorConfig.type` is a `SensorType` `StrEnum` (`numeric`, `condition`, `text`, `alerts`, `forecast`), so a typo in `config.yaml` fails at startup; `Settings.key_for_type(SensorType)` returns the first sensor key of a type (used for alerts and forecast).
- **SQLAlchemy 2.0 async** with `aiosqlite` — typed declarative model (`Mapped[...]`/`mapped_column`), `async_sessionmaker` factory, and `get_db` generator as a FastAPI dependency. Datetime columns use `UTCDateTime` (`models.py`), a `TypeDecorator` over `DATETIME` that converts aware values to UTC on write and attaches UTC to the naive values SQLite returns, so every loaded datetime is aware UTC.
- **Schema-driven serialization** (`schemas.py`) — `WeatherReadingOut` (`ConfigDict(from_attributes=True)`, `field_serializer` emitting `isoformat()` so UTC reads `+00:00`, not Pydantic's `Z`); `SunOut`, `ForecastOut`, `AnalyticsOut` `TypedDict`s type the hand-built `/sun`, `/forecast`, `/analytics` responses.
- **MQTT ingestion via aiomqtt** — persistent `async for` message loop; any failure (not only `MqttError`) is logged and the client reconnects with capped exponential backoff (5 s doubling to 60 s, ±20 % jitter, reset after a successful connect); `_process_mqtt_message` looks up one parser per topic — `PARSERS[SensorType]` (`_parse_numeric`, `_parse_condition`, `_parse_text`, `_parse_alerts`, `_parse_forecast`) or `_parse_sun` for `{topic_prefix}/sun` — which returns `(WeatherReading, broadcast payload)`; `_persist_and_broadcast` then commits the row and broadcasts the payload.
- **Middleware stack** (pure ASGI classes, listed outer to inner; `main.py` adds them in reverse because the last `add_middleware` call becomes the outermost layer; non-HTTP scopes pass both custom classes untouched):
  1. `SecurityHeadersMiddleware` (`main.py`) — wraps `send` and adds Content-Security-Policy, `X-Content-Type-Options`, `Referrer-Policy` and the `Cache-Control` policy to `http.response.start`: `no-cache` for `/`, `/index.html`, `/service-worker.js` and every other static path without `?v=` (icons, ES modules), `no-store` for `/api/*`, `immutable` for `?v=` assets only on 200/304 (nothing on a versioned 404); a `Cache-Control` already set by the app is kept.
  2. `RateLimitMiddleware` (`ratelimit.py`) — resolves the client IP with `client_ip()` (`Cf-Connecting-IP`, else the socket peer; also used for the WebSocket caps), stores it as `scope["state"]["real_ip"]`, and applies a sliding-window limit of 100 requests/60s per IP to `/api/*` only (429 + `Retry-After`); per-IP windows live in an `OrderedDict` capped at `MAX_TRACKED_IPS` (least recently seen key evicted).
  3. `CORSMiddleware` — CORS for `settings.allowed_origins` (public origin without port + loopback dev origins).
- **WebSocket broadcast** — `WebSocketManager` singleton maintains an ephemeral set of connections; `broadcast()` sends to all clients concurrently (`asyncio.gather`) with a per-client `WS_SEND_TIMEOUT_SECONDS`, so a stalled client is closed (1011) and dropped instead of blocking the MQTT ingest loop; `disconnect()` is idempotent.
- **MQTT payload limits** — `_process_mqtt_message` drops payloads over `MAX_PAYLOAD_BYTES` before decoding, rejects the `NaN`/`Infinity` JSON literals (`parse_constant`) and non-finite floats (`_finite_float`, `json.dumps(allow_nan=False)` for forecasts), requires a JSON object (`_parse_json_object`), truncates strings to their column width and forecasts to `MAX_FORECAST_ITEMS`; every parser error type (`PAYLOAD_ERRORS`, incl. `RecursionError`/`OverflowError`) is logged as one warning line, never a traceback.
- **Background tasks** — `cleanup_old_readings()` runs at startup and then every hour as an asyncio task, deleting `WeatherReading` rows older than `RETENTION_DAYS` (30); a failing cycle is logged and retried next cycle. Both tasks are registered in `background_tasks` with a done-callback that logs unexpected exits, and `GET /health` returns 503 naming any task that has stopped, so the Docker healthcheck restarts the container.
- **Logging** — `lifespan` calls `logging.basicConfig` with `settings.log_level` (env `LOG_LEVEL`, default `INFO`) so `app.*` INFO logs are visible alongside uvicorn's.
- **Schema migration** — `init_db()` calls `Base.metadata.create_all`, applies additive column migrations from a `_MIGRATIONS` list via `ALTER TABLE ADD COLUMN`, then creates any model-declared index missing from an existing table (`Index.create(checkfirst=True)`); idempotent, built-in, no Alembic.
- **SQLite pragmas** — `create_engine_with_pragmas()` registers a `connect` listener on `engine.sync_engine` that sets `journal_mode=WAL`, `synchronous=NORMAL` and `busy_timeout=5000` on every new connection.

## Flow

### MQTT → DB + WebSocket
```
MQTT broker ──`{topic_prefix}/#`──→ aiomqtt.Client (mqtt_listener)
                                        │
                                        ▼
                                 _process_mqtt_message(message)
                                        │  topic → parser (PARSERS[SensorType] or _parse_sun)
                                        ▼
                     parser(payload, parameter, now) → (WeatherReading, broadcast dict)
                                        │  PAYLOAD_ERRORS → one warning line, dropped
                                        ▼
                     _persist_and_broadcast: db.add + db.commit
                                        │
                                        ▼
                    WebSocketManager.broadcast(json) → all connected clients
```

### REST API
```
HTTP GET /api/weather/sensors        → settings.sensors (dict[str, SensorConfig], no DB)
HTTP GET /api/weather/current        → latest WeatherReading per sensor
HTTP GET /api/weather/history/{p}?hours=N → readings in time range
HTTP GET /api/weather/alerts         → readings with valid_to > now
HTTP GET /api/weather/sun            → latest sun position reading (SunOut)
HTTP GET /api/weather/forecast       → latest forecast, JSON string parsed (ForecastOut)
HTTP GET /api/weather/analytics      → umami_host/umami_id if configured (AnalyticsOut)
WS   /api/weather/ws                 → WebSocketManager.connect/disconnect
```

### Startup sequence
1. `lifespan` context manager enters → `_configure_logging()` → `init_db()` (table creation + migrations) → `asyncio.create_task(mqtt_listener())` → `asyncio.create_task(cleanup_old_readings())`.
2. Shutdown cancels both tasks with `suppress(CancelledError)`.

## Integration

| External System   | Interface                          | Direction     | Configuration                  |
|-------------------|------------------------------------|---------------|--------------------------------|
| MQTT broker       | `aiomqtt.Client` (TCP)            | ← inbound     | `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD` |
| SQLite database   | `aiosqlite` via SQLAlchemy async   | ↔ read/write  | `DATABASE_URL` (default: `sqlite+aiosqlite:///./weather.db`) |
| Umami analytics   | REST (optional, config-driven)     | → referenced  | `umami_host`, `umami_id` in `.env` |
| Frontend          | Static files mount at `/`          | → served      | `../frontend/` directory         |
| Browser clients   | WebSocket + HTTP (REST)            | ↔ bidirectional | `ws:`, `wss:` in CSP            |
| Docker            | `/health` endpoint                 | → health check | —                            |
