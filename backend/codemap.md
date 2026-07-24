# backend/

## Responsibility

Backend Service Layer — ingests sensor data from an MQTT broker, persists readings to an async SQLite database, and serves them to the frontend via REST endpoints and a real-time WebSocket. Also handles alert parsing, rate limiting, and periodic cleanup of old records.

## Design

- **Framework:** FastAPI (0.139) with async lifespan management.
- **Async patterns:** `asyncio` background tasks for MQTT listening and DB cleanup; `aiosqlite` + SQLAlchemy 2.0 async session API for all database access.
- **Project layout:**
  - `app/main.py` — application factory, middleware stack, lifespan hooks.
  - `app/config.py` — `Settings` (pydantic-settings from `.env`) + `SensorConfig` (from `config.yaml`).
  - `app/database.py` — async engine, session factory, schema migrations via `_MIGRATIONS`.
  - `app/models.py` — `WeatherReading` ORM model with compound indexes.
  - `app/schemas.py` — `WeatherReadingOut` Pydantic output schema with UTC serialization.
  - `app/mqtt_client.py` — `aiomqtt` subscriber, `WebSocketManager` broadcast hub, per-sensor-type message dispatch (numeric, condition, text, alerts, forecast, sun).
  - `app/ratelimit.py` — sliding-window rate limiter middleware (100 req/min per IP).
  - `app/routers/weather.py` — REST + WebSocket route handlers.
- **Middleware stack (outer to inner):** CORS → CloudflareIP (real IP from `Cf-Connecting-IP`) → RateLimit → CSP (Content-Security-Policy header).
- **DB cleanup:** Background task deletes readings older than 30 days every hour.

## Flow

1. `uvicorn app.main:app` boots the FastAPI application.
2. The `lifespan` context manager runs on startup:
   - `init_db()` creates tables and applies any missing column migrations.
   - `_load_sun_state()` restores the last known sun position from the DB.
   - Two `asyncio.create_task` background workers start: `mqtt_listener()` and `cleanup_old_readings()`.
3. `mqtt_listener()` connects to the MQTT broker, subscribes to `{topic_prefix}/#`, and loops over incoming messages. Each message is dispatched by topic to `_process_mqtt_message`, which parses the JSON payload, writes a `WeatherReading` row, and broadcasts the data to all connected WebSocket clients.
4. REST requests hit `/api/weather/sensors`, `/api/weather/current`, or `/api/weather/history/{parameter}?hours=N`. The rate limiter checks each request (except WebSocket upgrades) against a per-IP sliding window.
5. WebSocket clients connect at `/api/weather/ws` and receive live JSON updates pushed by `WebSocketManager.broadcast`.
6. On shutdown, both background tasks are cancelled gracefully.

## Integration

- **Frontend:** The FastAPI app mounts `../frontend/` as static files at `/`, serving the single-page JS dashboard at the root URL.
- **API:** All data endpoints live under `/api/weather/*` (mounted via `weather_router`).
- **MQTT:** Connects to an external broker using credentials from `.env`. Topic pattern: `{topic_prefix}/{sensor_key}`. Supports sensor types: `numeric`, `condition`, `text`, `alerts`, `forecast`, plus a special `sun` topic.
- **WebSocket:** Real-time push at `/api/weather/ws` — used by the frontend for live dashboard updates without polling.
- **External config:** Sensor definitions come from `config.yaml`; broker/auth settings from `.env`.
