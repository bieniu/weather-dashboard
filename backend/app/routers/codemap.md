# backend/app/routers/

## Responsibility

API Router Layer — HTTP endpoint handlers and WebSocket endpoint for weather data. Translates incoming HTTP/WS requests into database queries or configuration lookups, returning serialised responses. Owns the `/api/weather/*` route namespace.

## Design

- **Single `APIRouter` instance** (`prefix="/api/weather"`) registered in `main.py` via `app.include_router()`.
- **Stateless handlers** — all per-request state (DB session) injected via `Depends(get_db)`.
- **Read-only REST** — no POST/PUT/DELETE endpoints; data enters the system exclusively through MQTT ingestion (`mqtt_client.py`). The `/forecast` and `/sun` endpoints use manual dict serialisation (including UTC timezone handling) instead of Pydantic `response_model`.
- **Response serialisation** — numeric sensor endpoints use Pydantic `response_model` (`WeatherReadingOut`) with `from_attributes=True` for ORM-to-schema coercion; `/forecast` and `/sun` return hand-constructed dicts with ISO 8601 timestamps.
- **WebSocket** delegates lifecycle to `WebSocketManager` (connection tracking, broadcast) from `mqtt_client.py`; the endpoint only handles accept/disconnect and a blocking receive loop for keep-alive.
- **Config-driven sensor enumeration** — `/sensors` and `/current` iterate `settings.sensors`; `/history` and `/alerts` validate parameters against it.
- **No middleware or auth** — rate limiting is applied at the app level (`RateLimitMiddleware`), not per-route.

## Flow

```
HTTP Request
  → FastAPI routing (prefix /api/weather)
  → RateLimitMiddleware (app-level, pre-route)
  → Route handler
      → Depends(get_db) → yields AsyncSession
      → SQLAlchemy async query (select/where/order_by)
      → Pydantic serialisation via response_model
  → JSON response
```

```
WebSocket Upgrade
  → /api/weather/ws
  → manager.connect() → accept + register
  → Loop: receive_text() (blocking, keep-alive)
  → On disconnect: manager.disconnect() → unregister
  → Broadcasts arrive from MQTT listener via manager.broadcast()
```

Specific endpoint data flows:

| Endpoint | Source | Query pattern |
|---|---|---|
| `GET /sensors` | `settings.sensors` (config.yaml) | None — pure config dump |
| `GET /current` | `WeatherReading` table | One `LIMIT 1` query per sensor key, ordered by `timestamp DESC` |
| `GET /history/{param}` | `WeatherReading` table | Time-range filter (`>= now - N hours`), ordered by `timestamp ASC` |
| `GET /alerts` | `WeatherReading` table | Filtered by `alerts_key` parameter + `valid_to > now`, ordered by `timestamp DESC` |
| `GET /sun` | `WeatherReading` table | Single `LIMIT 1` where `parameter == "sun"` |
| `GET /forecast` | `WeatherReading` table | Single `LIMIT 1` where sensor `type == "forecast"`, returns `{forecast: json.loads(value_str), timestamp: iso_string}` |
| `GET /analytics` | `settings.umami_host` / `settings.umami_id` | None — pure config lookup |
| `WS /ws` | `WebSocketManager` (MQTT push) | No DB query — passive receive loop |

## Integration

**Dependencies (imported by this layer):**
- `app.config.settings` — sensor definitions, alerts key, Umami config
- `app.database.get_db` — async session factory dependency
- `app.models.WeatherReading` — SQLAlchemy ORM model for queries
- `app.mqtt_client.manager` — singleton `WebSocketManager` for WS lifecycle
- `app.schemas.WeatherReadingOut` — Pydantic response schema

**Consumers (import this layer):**
- `app.main` — imports `weather_router` and calls `app.include_router()`

**External consumers:**
- Frontend (vanilla JS) — calls all REST endpoints and opens the WebSocket
- No other internal module depends on routers
