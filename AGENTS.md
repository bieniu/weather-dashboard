<!-- CLAUDE.md is a symlink to this file — edit only AGENTS.md -->
# Instructions for AI Agents (Copilot, Claude, Codex)

## Structure

```
backend/         FastAPI async app (Python 3.14, SQLAlchemy + aiosqlite, aiomqtt)
  app/main.py    Entrypoint — `uvicorn app.main:app`
  app/config.py  Reads config.yaml + .env
frontend/        Vanilla JS + Chart.js (CDN), no build step
.venv/           Python virtual environment (root dir)
config.yaml      Sensor definitions (temperature, humidity, pressure, pm1/10/25)
pyproject.toml   Project config, deps, ruff/ty settings (root dir)
```

## Setup & run

```bash
uv sync --frozen   # run from root (requires uv installed)
# Requires .env in project root with MQTT_BROKER, MQTT_USER, MQTT_PASSWORD
uvicorn app.main:app --host 0.0.0.0 --port 8332   # run from backend/
# Or from root:
docker compose up
```

## Key points

- Backend mounts `/api/weather/*` router, then serves `../frontend/` as static files at `/`
- MQTT topic pattern: `{topic_prefix}/{sensor_key}` (prefix defaults to `weather-dashboard` in config.yaml)
- WebSocket at `/api/weather/ws` pushes live readings; REST at `/api/weather/sensors` and `/api/weather/history/{parameter}?hours=N`
- DB cleanup: deletes readings older than 30d, runs every hour in a background asyncio task
- Linting: `ruff check backend` (run from root)
- Formatting: `ruff format backend` (run from root). Ruff selects `ALL` rules with minimal ignores (D203, D213).
- Type checking: `ty check backend` (run from root). configured in `pyproject.toml` (root).
- Both ruff and ty are dev dependencies — install via `uv sync --frozen` from root.
- Pre-commit equivalent: `prek` (config in `prek.toml`). Run `prek run` to run all hooks.
- `.env` is gitignored; example vars in docker-compose.yml: `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`
