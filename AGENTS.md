<!-- CLAUDE.md is a symlink to this file — edit only AGENTS.md -->
# Instructions for AI Agents (Copilot, Claude, Codex)

## Structure

```
backend/         FastAPI async app (Python 3.12, SQLAlchemy + aiosqlite, aiomqtt)
  app/main.py    Entrypoint — `uvicorn app.main:app`
  app/config.py  Reads config.yaml + .env
frontend/        Vanilla JS + Chart.js (CDN), no build step
config.yaml      Sensor definitions (temperature, humidity, pressure, pm1/10/25)
```

## Setup & run

```bash
pip install -r backend/requirements.txt
# Requires .env in project root with MQTT_BROKER, MQTT_USER, MQTT_PASSWORD
uvicorn app.main:app --host 0.0.0.0 --port 8000   # run from backend/
# Or from root:
docker compose up
```

## Key points

- Backend mounts `/api/weather/*` router, then serves `../frontend/` as static files at `/`
- MQTT topic pattern: `{topic_prefix}/{sensor_key}` (prefix defaults to `weather-dashboard` in config.yaml)
- WebSocket at `/api/weather/ws` pushes live readings; REST at `/api/weather/sensors` and `/api/weather/history/{parameter}?hours=N`
- DB cleanup: deletes readings older than 30d, runs every hour in a background asyncio task
- No tests, no linter/formatter/typechecker config — none present in repo
- `.env` is gitignored; example vars in docker-compose.yml: `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`
