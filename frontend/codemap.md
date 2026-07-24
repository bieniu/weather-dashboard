# frontend/

## Responsibility
Client-side SPA — Weather Dashboard UI. Displays real-time sensor readings (temperature, humidity, pressure, PM), weather condition icons, 5-day forecast, meteorological alerts, and interactive charts — all served as static files with no build step.

## Design
- **Vanilla JS (ES modules)** — no framework. Single `app.js` (~700 lines) handles all logic: card rendering, WebSocket lifecycle, Chart.js integration, theme toggling, alert management, and forecast display.
- **Chart.js 4.4.3** (CDN) with `chartjs-adapter-date-fns` for time-axis charts. Each numeric sensor gets a line chart (140px tall, 144-point rolling window, 12-hour history by default). Charts are responsive, themed via CSS custom properties, and animate on new data.
- **CSS custom properties** for theming — light/dark mode toggled via `data-theme` attribute on `<html>`. Design tokens control background, surface, text, border, accent, and status colors. Transitions are 0.3s ease.
- **BEM-like class naming** (`weather-card__value`, `forecast-col__day`, `status--connected`). Layout uses CSS Grid (`auto-fill, minmax(380px, 1fr)`) with a single-column breakpoint at 640px.
- **Fonts**: Sora (display), Inter (body), JetBrains Mono (chart ticks) via Google Fonts. Material Symbols Rounded for icons.
- **PWA**: `manifest.json` enables "standalone" display with 192/512 icons. `service-worker.js` precaches app shell and serves cached-on-fallback for GET requests.
- **Weather icons**: 16 SVG weather icons (Meteocons fill style) in `weather_icons/`. Condition mapping resolves `mdi:` prefixed codes to SVG files, with day/night variants for partly cloudy.

## Flow
1. **DOMContentLoaded** → `init()` fires:
   - Theme toggle initialized (respects `prefers-color-scheme`).
   - `GET /api/weather/sensors` fetches sensor config (name, type, unit, color, icon, history window).
   - Cards are created dynamically from sensor config and appended to `#weather-grid`. Numeric sensors get a `<canvas>` for Chart.js; condition/text/forecast/alerts get specialized layouts.
   - `GET /api/weather/history/{parameter}?hours=N` loads historical data for each sensor (populates charts and last-value cards).
   - `GET /api/weather/forecast` loads 5-period forecast data.
   - `GET /api/weather/alerts` loads active meteorological alerts.
   - `GET /api/weather/sun` loads sun state (above/below horizon) for day/night icon selection.
   - WebSocket connects to `ws://<host>/api/weather/ws`.
   - Analytics script injected from `/api/weather/analytics` response (non-critical).
2. **WebSocket lifecycle**:
   - `onopen` — status indicator turns green with pulsing dot ("Połączono").
   - `onmessage` — parses JSON; dispatches to `updateCard()` (value + unit + timestamp), `appendChartPoint()` (rolling chart data), alert handling, or sun state updates.
   - `onclose` — status turns red ("Rozłączono"), auto-reconnects after 5s.
3. **Alert system**: Alerts arrive via WebSocket or initial fetch. A 30s interval checks `valid_to` expiry. Expired alerts are removed. Active alerts show a full-width card with color-coded icon (yellow/orange/red/green). Browser notifications are sent on new alerts (permission requested on first click).
4. **Theme toggle**: Click cycles light↔dark. Chart grid/tick colors update via `updateChartTheme()`. Preference is not persisted (resets to system preference on reload).

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
- **No build step** — all dependencies loaded from CDN (Chart.js, date adapter, Google Fonts, Material Symbols). Cache-bust via `?v=160` query param on CSS/JS/manifest.
- **Backend** (FastAPI) mounts frontend as static files at `/` and serves API at `/api/weather/*`.
