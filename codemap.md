# Repository Atlas: weather-dashboard

## Project Responsibility

Real-time environmental sensor dashboard. Ingests sensor readings (temperature, humidity, pressure, PM, water level) from an MQTT broker, persists them to an async SQLite database, and serves a real-time SPA dashboard with live charts, weather conditions, alerts, and 5-day forecast — all inside a single Docker container with no external runtime dependencies beyond the MQTT broker.

## System Entry Points

- `backend/app/main.py` — FastAPI application factory, middleware stack, lifespan hooks. Run via `uvicorn app.main:app`.
- `frontend/index.html` — SPA entry point, loaded as static file from FastAPI at `/`.
- `docker-compose.yml` — Single-service deployment (build + env config + persistent volume).
- `Dockerfile` — Multi-stage build: Python deps → copy source → run with uvicorn.
- `config.yaml` — Sensor definitions (name, type, unit, icon, color) + MQTT topic prefix.
- `pyproject.toml` — Python deps, dev deps (ruff, ty, pytest), linter/type-checker config.

## Directory Map (Aggregated)

| Directory | Responsibility Summary | Detailed Map |
|-----------|------------------------|--------------|
| `backend/` | Backend service layer — MQTT ingestion, SQLite persistence, REST + WebSocket serving via FastAPI. | [View Map](backend/codemap.md) |
| `backend/app/` | Application core — async FastAPI server, SQLAlchemy models, Pydantic schemas, MQTT client, rate limiter, middleware stack. | [View Map](backend/app/codemap.md) |
| `backend/app/routers/` | API Router Layer — HTTP endpoint handlers and WebSocket endpoint for `/api/weather/*`. | [View Map](backend/app/routers/codemap.md) |
| `frontend/` | Client-side SPA — vanilla JS with Chart.js, CSS custom properties theming, PWA support, no build step. | [View Map](frontend/codemap.md) |
| `utils/` | Icon generation tooling — produces PWA icons (PNG), maskable icons, and SVG favicon from source SVGs via cairosvg + Pillow. | [View Map](utils/codemap.md) |
| `scripts/` | Build and release helpers — single `set_version.sh` script for version propagation across all config files. | [View Map](scripts/codemap.md) |

## Key Data Flow

```
MQTT Broker ──→ backend/app/ (mqtt_listener)
                    │
                    ▼
              SQLite (WeatherReading)
                    │
              ┌─────┴─────┐
              ▼           ▼
         WebSocket    REST (/api/weather/*)
              │           │
              └─────┬─────┘
                    ▼
              frontend/ (SPA Dashboard)
```

## Design Principles

- **Single-process architecture** — FastAPI serves both API and frontend static files. No separate frontend server, no reverse proxy required in dev.
- **Async everywhere** — `asyncio` for MQTT ingestion, DB access (`aiosqlite`), WebSocket push, and background cleanup tasks.
- **Config-driven sensors** — All sensor definitions live in `config.yaml`; no code changes needed to add/remove sensor types.
- **No framework on frontend** — Vanilla JS avoids build tooling. Chart.js via CDN for charts, native WebSocket for real-time updates.
- **Minimal external deps** — MQTT broker is the only required external service. SQLite for persistence, Umami for optional analytics.
