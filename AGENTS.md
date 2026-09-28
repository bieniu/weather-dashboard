<!-- CLAUDE.md is a symlink to this file — edit only AGENTS.md -->
# Instructions for AI Agents (Copilot, Claude, Codex)

## Structure

```
backend/           FastAPI async app (Python 3.14, SQLAlchemy + aiosqlite, aiomqtt)
  app/main.py      Entrypoint — `uvicorn app.main:app`
  app/config.py    Reads config.yaml + .env
frontend/          Vanilla JS + Chart.js (vendored), no build step
  vendor/          Chart.js + date adapter copied from node_modules by `npm run vendor`
  weather_icons/   22 SVG weather icons (Meteocons fill style)
utils/             Icon generation scripts
  generate_icons.py  Generates weather icons from SVGs
  icon_with_bg.svg   Icon template with background
  icon.svg           Base icon SVG
tests/backend/     Tests (pytest)
.venv/             Python virtual environment (root dir)
config.yaml        Sensor definitions (temperature, humidity, pressure, pm1/10/25)
pyproject.toml     Project config, deps, ruff/ty settings (root dir)
README.md          Minimal docs — icon source reference only
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
- PWA: `frontend/service-worker.js` is registered from `app.js` (inline scripts are blocked by CSP). Its `VERSION` constant names the cache and is bumped by `scripts/set_version.sh`; the precache list must only contain files that exist (a single 404 aborts the install), which `tests/frontend/service-worker.test.js` checks.
- Chart.js and `chartjs-adapter-date-fns` are `dependencies` in `package.json` and their browser bundles live in `frontend/vendor/` (same-origin, CSP `script-src 'self'`). After a version bump run `npm run vendor`; `npm run vendor:check` (CI + pre-commit) fails while the copies are stale.
- MQTT topic pattern: `{topic_prefix}/{sensor_key}` (prefix defaults to `weather-dashboard` in config.yaml)
- WebSocket at `/api/weather/ws` pushes live readings (a browser `Origin` outside `settings.allowed_origins`, or more than `MAX_WS_CONNECTIONS` open handlers / `MAX_WS_CONNECTIONS_PER_IP` per client IP, is refused before `accept()`, which the browser sees as HTTP 403; slow clients are closed after `WS_SEND_TIMEOUT_SECONDS`); REST at `/api/weather/sensors`, `/api/weather/current`, and `/api/weather/history/{parameter}?hours=N`
- MQTT payload limits: `MAX_PAYLOAD_BYTES` (64 kB), non-object JSON and NaN/inf are rejected, strings are cut to their column width, forecasts keep the first `MAX_FORECAST_ITEMS`
- DB cleanup: deletes readings older than 30d, runs at startup and then every hour in a background asyncio task; `/health` returns 503 when a background task has died
- Logging: `LOG_LEVEL` env var (default `INFO`) configures the root logger in `lifespan`
- DB migrations: `init_db()` in `backend/app/database.py` applies schema migrations from the `_MIGRATIONS` list, then creates any index declared on the models that the existing table lacks (`create_all` never touches existing tables). When adding a new column to `WeatherReading`, add it to `_MIGRATIONS`; a new `Index` in `__table_args__` needs no migration entry. Extend `test_init_db_adds_missing_columns_and_indexes` either way.
- SQLite pragmas: every connection gets `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` via `create_engine_with_pragmas()` (tests use the same factory). WAL keeps `weather.db-wal`/`-shm` files next to the database, so back it up with `sqlite3 weather.db ".backup out.db"` (or `VACUUM INTO`), never by copying `weather.db` alone while the app runs.
- Linting: `ruff check backend` (run from root)
- Formatting: `ruff format backend` (run from root). Ruff selects `ALL` rules with minimal ignores (D203, D213).
- Type checking: `ty check backend` (run from root). configured in `pyproject.toml` (root).
- Both ruff and ty are dev dependencies — install via `uv sync --frozen` from root.
- Pre-commit wrapper: `prek` (reads `.pre-commit-config.yaml`). Run `prek run --all-files` to run all hooks.
- `.env` is gitignored; example vars in docker-compose.yml: `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`
- Deployment: the Cloudflare tunnel is the only public entry point. docker-compose binds 8332 to `127.0.0.1` only, uvicorn runs without `--proxy-headers`, and the client IP for rate limiting / WebSocket caps comes solely from `Cf-Connecting-IP` (falling back to the socket peer). HSTS and HTTPS redirects are configured in Cloudflare, not in the app.

## Testing

### Backend (pytest)

```bash
uv sync --group test       # install test deps (run from root)
pytest tests/backend -v    # run all backend tests (run from root)
pytest tests/backend -v --timeout=10 -k "test_mqtt"  # filter by name
```

- **Framework:** pytest + pytest-asyncio (auto mode), pytest-timeout (10s default)
- **DB:** each test gets a fresh in-memory SQLite via `db_engine` fixture
- **MQTT:** `_process_mqtt_message` tested directly with mock messages; `aiomqtt.Client` is never connected in tests
- **Time:** `freezegun` for freezing `datetime.now(UTC)`
- **WebSocket:** `WebSocketManager` unit tests plus endpoint lifecycle tests that drive the ASGI app directly with a scripted websocket scope (no TestClient, no lifespan, so no MQTT connection)
- **HTTP client:** `httpx.AsyncClient` with `ASGITransport` and `get_db` overridden to test engine

### Frontend (vitest)

```bash
npm test       # run all frontend tests with coverage (run from root)
```

- **Framework:** vitest (4.x) + happy-dom + @vitest/coverage-v8
- **Config:** `vitest.config.js` in root
- **Setup:** `tests/frontend/setup.js` — mocks Chart.js, canvas, matchMedia, DOM structure
- **Coverage:** always collected via `--coverage`; check uncovered lines for missing test coverage

### Linting & type checking

```bash
ruff check backend       # ruff lint (from root)
ruff format backend      # ruff format (from root)
ty check backend         # type checking (from root)
prek run --all-files     # pre-commit wrapper
```

### After every implementation

Always verify correctness by running **all** these before committing:

```bash
ruff check backend && ty check backend && pytest tests/backend -v --timeout=10 && npm test
```

Failing any of these must be fixed before the implementation is complete.

### Test files (`tests/backend/`)

| File | What it covers |
|---|---|
| `test_config.py` | `SensorConfig`, `Settings` (sensors, prefix, allowed origins, log level) |
| `test_database.py` | Table creation, column + index migrations, SQLite pragmas, cleanup query plan, `get_db` |
| `test_models.py` | ORM creation, default timestamp, declared indexes |
| `test_schemas.py` | `WeatherReadingOut` serialization, tz handling, nullables |
| `test_mqtt_client.py` | Topic map, `WebSocketManager` (concurrent broadcast, stalled-client drop), `_process_mqtt_message` (numeric, condition, error paths, payload limits), reconnect backoff |
| `test_ratelimit.py` | Rate limiter unit tests (pass, 429, non-API bypass, cleanup, per-IP isolation) |
| `test_routers.py` | REST endpoints (`/sensors`, `/current`, `/history`), sensor structure |
| `test_main.py` | Middleware through the real stack (per-IP rate limit via `Cf-Connecting-IP`, static bypass, CSP, CORS), DB cleanup task |

### Test structure conventions

- Tests use lazy imports inside each function (pytest fixtures trigger app module loading).
- `conftest.py` sets required env vars (`MQTT_BROKER`, `MQTT_USER`, `MQTT_PASSWORD`, `DATABASE_URL`) and `chdir`s to `backend/` before any app module is imported.
- Ruff and ty both run on test files; per-file-ignores in `pyproject.toml` suppress rules inappropriate for tests (ANN, D, S101, PLC0415, etc.).

## Repository Map

A full codemap is available at `codemap.md` in the project root.

Before working on any task, read `codemap.md` to understand:
- Project architecture and entry points
- Directory responsibilities and design patterns
- Data flow and integration points between modules

For deep work on a specific folder, also read that folder's `codemap.md`.
