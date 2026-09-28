# backend/app/

## Responsibility

Application Core — asynchronous FastAPI server acting as the ingestion, persistence, and distribution layer for real-time environmental sensor data. Receives sensor readings via MQTT, stores them in SQLite, serves historical data via REST, and pushes live updates to browser clients via WebSocket.

## Design

- **FastAPI async server** with `asynccontextmanager`-based lifespan for startup/shutdown orchestration (DB init, MQTT connection, background tasks).
- **Pydantic Settings (BaseSettings)** loads configuration from `.env` file at module level; `SensorConfig` objects are derived from `config.yaml` and merged into the settings singleton.
- **SQLAlchemy 2.0 async** with `aiosqlite` — declarative `Base` ORM model, `async_sessionmaker` factory, and `get_db` generator as a FastAPI dependency.
- **Schema-driven serialization** — `WeatherReadingOut` Pydantic model with `from_attributes` and custom `field_serializer` for UTC-aware ISO 8601 output.
- **MQTT ingestion via aiomqtt** — persistent `async for` message loop; any failure (not only `MqttError`) is logged and the client reconnects with capped exponential backoff (5 s doubling to 60 s, ±20 % jitter, reset after a successful connect); message dispatch dispatched to handler functions keyed by sensor type (`numeric`, `condition`, `text`, `alerts`, `forecast`).
- **Middleware stack** (Starlette `BaseHTTPMiddleware`, listed outer to inner; `main.py` adds them in reverse because the last `add_middleware` call becomes the outermost layer):
  1. `SecurityHeadersMiddleware` — Content-Security-Policy, `X-Content-Type-Options`, `Referrer-Policy` and the `Cache-Control` policy (`no-cache` HTML/worker, `no-store` API, `immutable` cache-busted assets) on all responses.
  2. `CloudflareIPMiddleware` — reads `Cf-Connecting-IP` header to set `request.state.real_ip`.
  3. `RateLimitMiddleware` — sliding-window rate limiter at 100 requests/60s per IP, applied to `/api/*` paths only; per-IP windows live in an `OrderedDict` capped at `MAX_TRACKED_IPS` (least recently seen key evicted); WebSocket scopes never reach `BaseHTTPMiddleware.dispatch`.
  4. `CORSMiddleware` — CORS for `settings.allowed_origins` (public origin without port + loopback dev origins).
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
                                        │
                          ┌─────────────┼─────────────┐
                          ▼             ▼             ▼
                    numeric/      condition/      alerts
                    text          text
                          │             │             │
                          ▼             ▼             ▼
                    WeatherReading ORM object → db.add + db.commit
                          │
                          ▼
                    WebSocketManager.broadcast(json) → all connected clients
```

### REST API
```
HTTP GET /api/weather/sensors        → settings.sensors model_dump (no DB)
HTTP GET /api/weather/current        → latest WeatherReading per sensor
HTTP GET /api/weather/history/{p}?hours=N → readings in time range
HTTP GET /api/weather/alerts         → readings with valid_to > now
HTTP GET /api/weather/sun            → latest sun position reading
HTTP GET /api/weather/forecast       → latest forecast (JSON string parsed)
HTTP GET /api/weather/analytics      → umami_host/umami_id if configured
WS   /api/weather/ws                 → WebSocketManager.connect/disconnect
```

### Startup sequence
1. `lifespan` context manager enters → `init_db()` (table creation + migrations) → `_load_sun_state()` (restore latest sun value from DB) → `asyncio.create_task(mqtt_listener())` → `asyncio.create_task(cleanup_old_readings())`.
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
