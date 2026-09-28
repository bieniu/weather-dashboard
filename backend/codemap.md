# backend/

## Responsibility

Backend Service Layer — ingests sensor data from an MQTT broker, persists readings to an async SQLite database, and serves them to the frontend via REST endpoints and a real-time WebSocket. Also handles alert parsing, rate limiting, and periodic cleanup of old records.

## Design

- **Framework:** FastAPI (0.139) with async lifespan management.
- **Async patterns:** `asyncio` background tasks for MQTT listening and DB cleanup; `aiosqlite` + SQLAlchemy 2.0 async session API for all database access.
- **Project layout:**
  - `app/main.py` — application factory, middleware stack, lifespan hooks.
  - `app/config.py` — `Settings` (pydantic-settings from `.env`, `key_for_type()`) + `SensorConfig` (from `config.yaml`, `type: SensorType`).
  - `app/database.py` — async engine with SQLite pragmas (WAL, `synchronous=NORMAL`, `busy_timeout`), session factory, schema migrations (`_MIGRATIONS` columns + missing-index creation).
  - `app/models.py` — `WeatherReading` ORM model (`Mapped[...]`) with compound indexes plus a timestamp-only index for retention cleanup; `UTCDateTime` column type that always loads aware UTC datetimes.
  - `app/schemas.py` — `WeatherReadingOut` Pydantic output schema (ISO 8601 with `+00:00`) and the `SunOut` / `ForecastOut` / `AnalyticsOut` response `TypedDict`s.
  - `app/mqtt_client.py` — `aiomqtt` subscriber, `WebSocketManager` broadcast hub, parser registry `PARSERS[SensorType]` (plus `_parse_sun`) feeding `_persist_and_broadcast`.
  - `app/ratelimit.py` — pure ASGI `RateLimitMiddleware`: client IP from `Cf-Connecting-IP` (`client_ip()`), sliding-window limit (100 req/min per IP, `/api/*` paths only, at most `MAX_TRACKED_IPS` keys kept with LRU eviction).
  - `app/routers/weather.py` — REST + WebSocket route handlers.
- **Middleware stack (outer to inner, pure ASGI):** SecurityHeaders (CSP, nosniff, referrer policy, cache policy) → RateLimit (real IP from `Cf-Connecting-IP`, limit on `/api/*` only) → CORS. Starlette treats the middleware added *last* as the outermost layer, so `main.py` adds them in reverse.
- **DB cleanup:** Background task deletes readings older than 30 days at startup and then every hour; `/health` returns 503 if it or the MQTT listener has died.

## Flow

1. `uvicorn app.main:app` boots the FastAPI application.
2. The `lifespan` context manager runs on startup:
   - `init_db()` creates tables and applies any missing column migrations.
   - Two `asyncio.create_task` background workers start: `mqtt_listener()` and `cleanup_old_readings()`.
3. `mqtt_listener()` connects to the MQTT broker, subscribes to `{topic_prefix}/#`, and loops over incoming messages. `_process_mqtt_message` picks the parser for the topic's sensor type, which validates the payload and builds the `WeatherReading` row plus the broadcast message; `_persist_and_broadcast` writes the row and pushes the message to all connected WebSocket clients.
4. REST requests hit `/api/weather/sensors`, `/api/weather/current`, or `/api/weather/history/{parameter}?hours=N`. The rate limiter checks each request (except WebSocket upgrades) against a per-IP sliding window.
5. WebSocket clients connect at `/api/weather/ws` and receive live JSON updates pushed by `WebSocketManager.broadcast`.
6. On shutdown, both background tasks are cancelled gracefully.

## Integration

- **Frontend:** The FastAPI app mounts `../frontend/` as static files at `/`, serving the single-page JS dashboard at the root URL.
- **API:** All data endpoints live under `/api/weather/*` (mounted via `weather_router`).
- **MQTT:** Connects to an external broker using credentials from `.env`. Topic pattern: `{topic_prefix}/{sensor_key}`. Supports sensor types: `numeric`, `condition`, `text`, `alerts`, `forecast`, plus a special `sun` topic.
- **WebSocket:** Real-time push at `/api/weather/ws` — used by the frontend for live dashboard updates without polling.
- **External config:** Sensor definitions come from `config.yaml`; broker/auth settings from `.env`.
