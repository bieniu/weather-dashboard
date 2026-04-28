// ===== CONFIGURATION =====
const API_BASE = "/api/weather";
const WS_PROTOCOL = location.protocol === "https:" ? "wss:" : "ws:";
const WS_URL = `${WS_PROTOCOL}//${location.host}/api/weather/ws`;
const HISTORY_HOURS = 12;
const MAX_CHART_POINTS = 144; // every 5 min for 12h = 144 points

// ===== STATE =====
const charts = {};
let sensorsConfig = {};

// ===== HELPERS =====
function formatTimestamp(isoString) {
  const d = new Date(isoString);
  return d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
}

function formatUpdated(isoString) {
  const d = new Date(isoString);
  return `Zaktualizowano: ${d.toLocaleTimeString("pl-PL")}`;
}

/** Strip the "mdi:" prefix and return a Material Symbols icon name. */
function resolveIcon(iconStr) {
  return iconStr.replace(/^mdi:/, "");
}

// ===== CARD GENERATION =====
function createCard(sensorKey, sensor) {
  const card = document.createElement("article");
  card.className = "weather-card";
  card.id = `card-${sensorKey}`;
  card.style.setProperty("--sensor-accent", sensor.color);

  card.innerHTML = `
    <div class="weather-card__header">
      <span class="material-symbols-rounded weather-card__icon" style="color: ${sensor.color}">${resolveIcon(sensor.icon)}</span>
      <span class="weather-card__label">${sensor.name}</span>
    </div>
    <div class="weather-card__current">
      <span class="weather-card__value" id="${sensorKey}-value">--</span>
      <span class="weather-card__unit" id="${sensorKey}-unit"></span>
    </div>
    <p class="weather-card__updated" id="${sensorKey}-updated">Oczekiwanie na dane...</p>
    <div class="weather-card__chart-wrapper">
      <canvas id="chart-${sensorKey}" aria-label="${sensor.name} chart for the last ${HISTORY_HOURS} hours" role="img"></canvas>
    </div>
  `;

  return card;
}

// ===== CHART INITIALIZATION =====
function createChart(canvasId, parameter, color) {
  const ctx = document.getElementById(canvasId).getContext("2d");

  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [{
        data: [],
        borderColor: color,
        backgroundColor: color + "22",
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.3,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.parsed.y.toFixed(1)}`,
            title: (items) => formatTimestamp(items[0].raw.x),
          }
        }
      },
      scales: {
        x: {
          type: "time",
          time: { unit: "hour", tooltipFormat: "HH:mm", displayFormats: { hour: "HH:mm" } },
          grid: { color: getComputedStyle(document.documentElement)
                           .getPropertyValue("--md-sys-color-outline-variant").trim() },
          ticks: {
            font: { family: "Roboto", size: 11 },
            color: getComputedStyle(document.documentElement)
                     .getPropertyValue("--md-sys-color-on-surface-variant").trim(),
            maxTicksLimit: 6,
          }
        },
        y: {
          grid: { color: getComputedStyle(document.documentElement)
                           .getPropertyValue("--md-sys-color-outline-variant").trim() },
          ticks: {
            font: { family: "Roboto Mono", size: 11 },
            color: getComputedStyle(document.documentElement)
                     .getPropertyValue("--md-sys-color-on-surface-variant").trim(),
            callback: function(value) {
              return Number(value).toFixed(1);
            },
          }
        }
      }
    }
  });
}

// ===== UPDATE CARD =====
function updateCard(parameter, value, unit, timestamp) {
  const valueEl = document.getElementById(`${parameter}-value`);
  const unitEl = document.getElementById(`${parameter}-unit`);
  const updatedEl = document.getElementById(`${parameter}-updated`);

  if (valueEl) valueEl.textContent = Number(value).toFixed(1);
  if (unitEl) unitEl.textContent = unit;
  if (updatedEl) updatedEl.textContent = formatUpdated(timestamp);
}

// ===== APPEND CHART POINT =====
function appendChartPoint(parameter, value, timestamp) {
  const chart = charts[parameter];
  if (!chart) return;

  chart.data.datasets[0].data.push({ x: new Date(timestamp), y: value });

  // Limit number of points
  if (chart.data.datasets[0].data.length > MAX_CHART_POINTS) {
    chart.data.datasets[0].data.shift();
  }

  chart.update("none"); // no animation for live data
}

// ===== LOAD HISTORY (REST) =====
async function loadHistory(parameter) {
  try {
    const res = await fetch(`${API_BASE}/history/${parameter}?hours=${HISTORY_HOURS}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const history = await res.json();

    const chart = charts[parameter];
    if (!chart) return;

    chart.data.datasets[0].data = history.map(r => ({
      x: new Date(r.timestamp),
      y: r.value,
    }));
    chart.update();

    // Set current value from the last record
    if (history.length > 0) {
      const last = history[history.length - 1];
      updateCard(parameter, last.value, last.unit, last.timestamp);
    }
  } catch (err) {
    console.error(`[History] Error fetching ${parameter}:`, err);
  }
}

// ===== WEBSOCKET — LIVE UPDATES =====
function connectWebSocket() {
  const statusEl = document.getElementById("connection-status");
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("[WS] Connected");
    statusEl.className = "status-chip status-chip--connected";
    statusEl.innerHTML = `<span class="material-symbols-rounded">wifi</span><span>Połączono</span>`;
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateCard(data.parameter, data.value, data.unit, data.timestamp);
      appendChartPoint(data.parameter, data.value, data.timestamp);
    } catch (e) {
      console.warn("[WS] Message parse error:", e);
    }
  };

  ws.onclose = () => {
    console.warn("[WS] Disconnected. Retrying in 5s...");
    statusEl.className = "status-chip status-chip--disconnected";
    statusEl.innerHTML = `<span class="material-symbols-rounded">wifi_off</span><span>Rozłączono</span>`;
    setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = (err) => {
    console.error("[WS] Error:", err);
    ws.close();
  };
}

// ===== THEME TOGGLE =====
function initThemeToggle() {
  const btn = document.querySelector("[data-theme-toggle]");
  const html = document.documentElement;
  let theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  html.setAttribute("data-theme", theme);

  const updateIcon = () => {
    btn.querySelector(".material-symbols-rounded").textContent =
      theme === "dark" ? "light_mode" : "dark_mode";
    btn.setAttribute("aria-label",
      theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
  };
  updateIcon();

  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", theme);
    updateIcon();
    // Refresh chart axis colors after theme change
    Object.values(charts).forEach(c => c.update());
  });
}

// ===== LOAD SENSOR CONFIG =====
async function loadSensors() {
  const res = await fetch(`${API_BASE}/sensors`);
  if (!res.ok) throw new Error(`Failed to load sensors: HTTP ${res.status}`);
  return res.json();
}

// ===== APP INITIALIZATION =====
async function init() {
  initThemeToggle();

  // Load sensor configuration from backend
  sensorsConfig = await loadSensors();
  const grid = document.getElementById("weather-grid");

  for (const [key, sensor] of Object.entries(sensorsConfig)) {
    // Generate card DOM
    grid.appendChild(createCard(key, sensor));

    // Create chart with sensor accent color
    charts[key] = createChart(`chart-${key}`, key, sensor.color);
  }

  // Load historical data for all sensors
  await Promise.all(
    Object.keys(sensorsConfig).map(key => loadHistory(key))
  );

  // Connect WebSocket
  connectWebSocket();
}

document.addEventListener("DOMContentLoaded", init);
