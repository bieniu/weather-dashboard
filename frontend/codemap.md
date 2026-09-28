# frontend/

## Responsibility
Client-side SPA — Weather Dashboard UI. Displays real-time sensor readings (temperature, humidity, pressure, PM), weather condition icons, 5-day forecast, meteorological alerts, and interactive charts — all served as static files with no build step.

## Design
- **Vanilla JS (ES modules)** — no framework. Single `app.js` (~700 lines) handles all logic: card rendering, WebSocket lifecycle, Chart.js integration, theme toggling, alert management, and forecast display.
- **Chart.js 4.5.x** (vendored in `vendor/`, version pinned by `package.json`) with `chartjs-adapter-date-fns` for time-axis charts. Each numeric sensor gets a line chart (140px tall; points are `{x: epoch ms, y}` with `parsing: false`; above 400 points LTTB decimation draws ~200 samples, and because the plugin then swaps `dataset.data` for a decimated view, the source arrays live in `chartPoints` and are re-assigned on every update; the window is the sensor's `history_hours`, 24 h by default, trimmed relative to the newest point). Charts are responsive, themed via CSS custom properties, and animate on new data.
- **CSS custom properties** for theming — light/dark mode toggled via `data-theme` attribute on `<html>`. Design tokens control background, surface, text, border, accent, and status colors. Transitions are 0.3s ease.
- **BEM-like class naming** (`weather-card__value`, `forecast-col__day`, `status--connected`). Layout uses CSS Grid (`auto-fill, minmax(380px, 1fr)`) with a single-column breakpoint at 640px.
- **Responsive forecast layout** — pure CSS: `.grid` is an inline-size container and `@container (width < 776px)` (the width at which two 380px cards no longer fit, i.e. a single-column grid) switches `.forecast-grid` from 5 to 4 columns and hides the 5th period. No resize listener.
- **Fonts**: Sora (display), Inter (body), JetBrains Mono (chart ticks) via Google Fonts. Material Symbols Rounded for icons.
- **PWA**: `manifest.json` enables "standalone" display with 192/512 icons. `service-worker.js` (registered from `app.js` at the end of `init()`, not inline, because CSP is `script-src 'self'`) precaches the versioned app shell (`?v=N` URLs, `vendor/` bundles, all weather icons) into a cache named after the release (`VERSION`, rewritten by `scripts/set_version.sh`). Navigations and `/api/weather/sensors` are network-first with the cached copy as offline fallback (so the offline shell can still draw the cards); other same-origin GETs are cache-first and stored on first fetch; all other `/api/*` (live data) and cross-origin requests bypass the worker. Offline, cards render with placeholders because history and live data are never cached.
- **Weather icons**: 22 SVG weather icons (Meteocons fill style) in `weather_icons/`. Condition mapping resolves `mdi:` prefixed codes to SVG files, with day/night variants for partly cloudy.

## Flow
1. **DOMContentLoaded** → `init()` fires:
   - Theme toggle initialized (respects `prefers-color-scheme`).
   - `GET /api/weather/sensors` fetches sensor config (name, type, unit, color, icon, history window).
    - Cards are created dynamically from sensor config and appended to `#weather-grid`. Numeric sensors get a `<canvas>` for Chart.js; condition/text/forecast/alerts get specialized layouts.
    - `GET /api/weather/history/{parameter}?hours=N` loads historical data for each sensor (populates charts and last-value cards).
   - `GET /api/weather/forecast` loads 5-period forecast data — response is `{forecast: [...], timestamp: "..."}`, extracts `data.forecast` array and uses server-provided `data.timestamp` for the card update.
   - `GET /api/weather/alerts` loads active meteorological alerts.
   - `GET /api/weather/sun` loads sun state (above/below horizon) for day/night icon selection.
   - WebSocket connects to `ws://<host>/api/weather/ws`.
   - Analytics script injected from `/api/weather/analytics` response (non-critical).
2. **WebSocket lifecycle**:
   - `onopen` — status indicator turns green with pulsing dot ("Połączono").
   - `onmessage` — parses JSON; dispatches to `updateCard()` (value + unit + timestamp for numeric, forecast grid rendering for forecast type, condition value + icon for condition type), `appendChartPoint()` (rolling chart data), alert handling, or sun state updates.
   - `onclose` — status turns red ("Rozłączono"), auto-reconnects after 5s.
3. **Forecast rendering**: `updateCard()` for `forecast` type fills the 5-column grid. Each forecast period renders day name (Polish), day/night period, weather icon (condition SVG with day/night variant), temperature, precipitation, cloud coverage, and wind speed. Fields use null-safe access — missing values display `--`. Unused columns (when fewer than 5 periods are returned) are reset to `--` placeholders.
4. **Alert system**: Alerts arrive via WebSocket or initial fetch. A 30s interval checks `valid_to` expiry. Expired alerts are removed. Active alerts show a full-width card with color-coded icon (yellow/orange/red/green). Browser notifications are sent on new alerts (permission requested on first click).
5. **Theme toggle**: Click cycles light↔dark. Chart grid/tick colors update via `updateChartTheme()`. Preference is not persisted (resets to system preference on reload).

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
- **No build step** — Chart.js and the date adapter are served same-origin from `vendor/` (copies refreshed with `npm run vendor`, verified by `npm run vendor:check`); An explicit toggle is stored in `localStorage` (`theme`) and from then on wins over the OS preference (product choice: there is no \"follow the OS again\" control). Google Fonts and a Material Symbols subset (`icon_names=`, ~3 kB instead of the ~460 kB full icon font) still come from Google. Cache-bust via `?v=N` query param on CSS/JS/vendor/manifest, rewritten by `scripts/set_version.sh`.
- **Backend** (FastAPI) mounts frontend as static files at `/` and serves API at `/api/weather/*`.
