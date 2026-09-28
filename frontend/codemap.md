# frontend/

## Responsibility
Client-side SPA — Weather Dashboard UI. Displays real-time sensor readings (temperature, humidity, pressure, PM), weather condition icons, 5-day forecast, meteorological alerts, and interactive charts — all served as static files with no build step.

## Design
- **Vanilla JS (ES modules, no build step)** — no framework. `index.html` loads `app.js?v=N` as the entry module; it imports the rest with plain relative specifiers (no `?v=`, so a module graph needs no rewriting). Dependency order, no cycles:

  | Module | Owns |
  |---|---|
  | `api.js` | `API_BASE`, `getJson()` (throws on non-2xx), `sensorsConfig` (filled by `loadSensors()`), `HISTORY_HOURS` / `historyHours(sensor)` |
  | `format.js` | module-level `Intl.DateTimeFormat` (`TIME_FORMAT`, HH:mm), `formatTimestamp`, `formatUpdated`, `getPolishDayAbbr`, `esc()` for HTML templates |
  | `icons.js` | condition code → SVG maps, `sunState`, `getConditionSvgPath()` (partly cloudy: explicit `isDaytime` → sun state → `DAY_START_HOUR`..`DAY_END_HOUR`), `resolveIcon()` |
  | `charts.js` | `charts`, `chartPoints`, `buildChartOptions(decimals, unit)` (pure; tooltip/tick callbacks), `createChart(canvasId, color, decimals, unit)`, `withAlpha()` (fill colour from #rgb/#rrggbb, else transparent), theme recolouring, `appendChartPoint`, `loadHistory`, `loadAllHistory` |
  | `cards.js` | `CARD_TYPES` map (markup + updater per sensor type; unknown types render as numeric), `isChartSensor()`, `createCard`, `updateCard`, `fillForecastCol`, condition icon re-render / `applySunState`, loaders `loadCurrent`, `loadForecast`, `loadSunState` |
  | `alerts.js` | `alerts` list, `toAlert()` (REST and WebSocket shapes), alert card, expiry check every `ALERT_CHECK_MS`, notifications, `loadAlerts` |
  | `ws.js` | `wsState`, `connectWebSocket` (URL built from `location` at connect time), backoff reconnect, `reconnectNow`, REST backfill after a reconnect |
  | `theme.js` | theme toggle, `THEME_STORAGE_KEY`, `THEME_ICONS` |
  | `app.js` | `init()`, `registerServiceWorker`, `initAnalytics`, `resetState()` (calls every module's `reset*()`; used by tests), the `DOMContentLoaded` hook |

- **Chart.js 4.5.x** (vendored in `vendor/`, version pinned by `package.json`, used through the `Chart` global) with `chartjs-adapter-date-fns` for time-axis charts. Each numeric sensor gets a line chart (140px tall; points are `{x: epoch ms, y}` with `parsing: false`; above 400 points LTTB decimation draws ~200 samples, and because the plugin then swaps `dataset.data` for a decimated view, the source arrays live in `chartPoints` and are re-assigned on every update; the window is the sensor's `history_hours`, 24 h by default, trimmed relative to the newest point). Axis colours come from the CSS tokens, read once per chart creation / theme change. The y axis has a fixed width (`Y_AXIS_WIDTH`) so the plots line up.
- **Config strings are never raw HTML** — `sensor.name`, `sensor.icon` and the sensor key go through `esc()` before they reach a card template; live values are written with `textContent`.
- **CSS custom properties** for theming — light/dark mode toggled via `data-theme` attribute on `<html>`. Design tokens control background, surface, text, border, accent and status colours, plus `--content-max` (page width) and `--transition` (theme colour transitions).
- **BEM-like class naming** (`weather-card__value`, `forecast-col__day`, `status--connected`). Every card also gets `weather-card--<type>` (`numeric`, `condition`, `text`, `alerts`, `forecast`); layout rules use these classes, never the `#card-<key>` ids (those stay as anchors / test hooks), so renaming a sensor key cannot break the layout. Layout uses CSS Grid (`auto-fill, minmax(min(380px, 100%), 1fr)`).
- **Responsive forecast layout** — pure CSS: `.grid` is an inline-size container and `@container (width < 776px)` (the width at which two 380px cards no longer fit, i.e. a single-column grid) switches `.forecast-grid` from 5 to 4 columns and hides the 5th period. No resize listener.
- **Fonts**: Sora (display), Inter (body), JetBrains Mono (chart ticks) via Google Fonts. Material Symbols Rounded for icons (subset: every ligature in `index.html`, `frontend/*.js` and `config.yaml` must be in `icon_names=`, checked by `tests/frontend/icons.test.js`).
- **PWA**: `manifest.json` enables "standalone" display with 192/512 icons. `service-worker.js` (registered from `app.js` at the start of `init()`, not inline, because CSP is `script-src 'self'`) precaches the versioned app shell (`?v=N` URLs, `vendor/` bundles), every ES module under its plain path (`APP_MODULES`; `tests/frontend/service-worker.test.js` fails if a module is missing) and all weather icons into a cache named after the release (`VERSION`, rewritten by `scripts/set_version.sh`). Navigations, the ES modules imported by `app.js` (`APP_MODULES`) and `/api/weather/sensors` are network-first with the cached copy as offline fallback (so the offline shell can still draw the cards); other same-origin GETs are cache-first and stored on first fetch; all other `/api/*` (live data) and cross-origin requests bypass the worker. Offline, cards render with placeholders because history and live data are never cached.
- **Weather icons**: 22 SVG weather icons (Meteocons fill style) in `weather_icons/`. Condition mapping resolves `mdi:` prefixed codes to SVG files, with day/night variants for partly cloudy.

## Flow
1. **DOMContentLoaded** → `init()` (`app.js`) fires:
   - Service worker registered, theme toggle initialized (respects `prefers-color-scheme`).
   - `GET /api/weather/sensors` fetches sensor config (name, type, unit, color, icon, history window). If it fails, `#weather-grid` shows an error message (`.grid__error`, `role="alert"`) and init stops.
   - Cards are created from the sensor config and appended to `#weather-grid`. Numeric sensors (`isChartSensor`) get a `<canvas>` and a Chart.js instance; condition/text/forecast/alerts get specialized layouts.
   - `GET /api/weather/current` fills every card value in one request; `GET /api/weather/history/{parameter}?hours=N` fills each chart.
   - `GET /api/weather/forecast` loads 5-period forecast data — response is `{forecast: [...], timestamp: "..."}`, extracts `data.forecast` array and uses server-provided `data.timestamp` for the card update.
   - `GET /api/weather/alerts` loads active meteorological alerts.
   - `GET /api/weather/sun` loads sun state (above/below horizon) for day/night icon selection.
   - WebSocket connects to `ws://<host>/api/weather/ws`.
   - Analytics script injected from `/api/weather/analytics` response (non-critical).
2. **WebSocket lifecycle**:
   - `onopen` — status indicator turns green with pulsing dot ("Połączono").
   - `onmessage` — parses JSON; dispatches to `updateCard()` (the type's updater from `CARD_TYPES`), `appendChartPoint()` (rolling chart data), `handleAlertUpdate(toAlert(...))`, or `applySunState()`.
   - `onclose` — status turns red ("Rozłączono"), reconnects with exponential backoff (5 s doubling to 60 s, ±20 % jitter); a visible tab or `online` event reconnects at once, and every reconnect backfills current values, histories, alerts and the forecast over REST.
3. **Forecast rendering**: the forecast updater fills the `FORECAST_COLUMNS` (5) columns via `fillForecastCol(col, item | null)`. Each period renders day name (Polish), day/night period, weather icon (condition SVG with day/night variant), temperature, precipitation, cloud coverage and wind speed (`fmt(value, suffix)`: missing values display `--`). Columns without a period (fewer than 5 returned) are reset to `--` placeholders.
4. **Alert system**: Alerts arrive via WebSocket or initial fetch, both normalised by `toAlert()`. Every `ALERT_CHECK_MS` (30 s) expired (or undated) alerts are dropped and the first remaining one is shown in a full-width card with a colour-coded icon (yellow/orange/red; green for a null level). Browser notifications are sent on new alerts (permission requested on first click).
5. **Theme toggle**: Click cycles light↔dark and stores the choice in `localStorage` (`theme`); chart grid/tick colours update via `updateChartTheme()`.

## Integration
- **REST endpoints** (all under `/api/weather`):
  - `GET /sensors` — sensor definitions
  - `GET /current` — latest readings
  - `GET /history/{parameter}?hours=N` — time-series data
  - `GET /forecast` — 5-period forecast
  - `GET /alerts` — active alerts
  - `GET /sun` — sun state
  - `GET /analytics` — analytics host/ID config
- **WebSocket** at `/api/weather/ws` — pushes real-time readings as JSON `{ parameter, value, unit, timestamp, icon }`, plus alert and sun state messages.
- **No build step** — Chart.js and the date adapter are served same-origin from `vendor/` (copies refreshed with `npm run vendor`, verified by `npm run vendor:check`). An explicit theme toggle is stored in `localStorage` (`theme`) and from then on wins over the OS preference (product choice: there is no "follow the OS again" control). Google Fonts and a Material Symbols subset (`icon_names=`, ~3 kB instead of the ~460 kB full icon font) still come from Google. Cache-bust via `?v=N` query param on CSS, the entry `app.js`, vendor bundles and the manifest, rewritten by `scripts/set_version.sh`; the imported modules are unversioned (served with `no-cache`, revalidated by ETag) and refreshed by the service worker's per-release precache.
- **Tests** (`tests/frontend/`, vitest + happy-dom): `setup.js` loads the `<body>` of `index.html`, stubs `Chart`, `Notification`, `matchMedia` and a failing `fetch` per test with `vi.stubGlobal` (undone by `vi.unstubAllGlobals()`); `app.test.js` imports each module directly and calls `resetState()` before every test.
- **Backend** (FastAPI) mounts frontend as static files at `/` and serves API at `/api/weather/*`.
