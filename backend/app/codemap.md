# backend/app/

## Responsibility

Application Core — asynchronous FastAPI server acting as the ingestion, persistence, and distribution layer for real-time environmental sensor data. Receives sensor readings via MQTT, stores them in SQLite, serves historical data via REST, and pushes live updates to browser clients via WebSocket.

## Design

- **FastAPI async server** with `asynccontextmanager`-based lifespan for startup/shutdown orchestration (DB init, MQTT connection, background tasks).
- **Pydantic Settings (BaseSettings)** loads configuration from `.env` file at module level; `SensorConfig` objects are derived from `config.yaml` and merged into the settings singleton.
- **SQLAlchemy 2.0 async** with `aiosqlite` — declarative `Base` ORM model, `async_sessionmaker` factory, and `get_db` generator as a FastAPI dependency.
- **Schema-driven serialization** — `WeatherReadingOut` Pydantic model with `from_attributes` and custom `field_serializer` for UTC-aware ISO 8601 output.
- **MQTT ingestion via aiomqtt** — persistent `async for` message loop with automatic reconnection on `MqttError`; message dispatch dispatched to handler functions keyed by sensor type (`numeric`, `condition`, `text`, `alerts`, `forecast`).
- **Middleware stack** (Starlette `BaseHTTPMiddleware`):
  1. `CORSMiddleware` — permissive CORS from configured origins.
  2. `CloudflareIPMiddleware` — reads `Cf-Connecting-IP` header to set `request.state.real_ip`.
  3. `RateLimitMiddleware` — sliding-window rate limiter at 100 requests/60s per IP, bypassed for WebSocket upgrade.
  4. `CSPMiddleware` — applies Content-Security-Policy header to all responses.
- **WebSocket broadcast** — `WebSocketManager` singleton maintains an ephemeral list of connections; broadcast iterates a shallow copy, removing disconnected clients on send failure.
- **Background task** — `cleanup_old_readings()` runs every hour as an asyncio task, deleting `WeatherReading` rows older than 30 days.
- **Schema migration** — `init_db()` calls `Base.metadata.create_all` then applies additive column migrations from a `_MIGRATIONS` list via `ALTER TABLE ADD COLUMN` (idempotent, built-in, no Alembic).

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
