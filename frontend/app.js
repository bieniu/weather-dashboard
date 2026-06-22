const API_BASE = "/api/weather";
const WS_PROTOCOL = location.protocol === "https:" ? "wss:" : "ws:";
const WS_URL = `${WS_PROTOCOL}//${location.host}/api/weather/ws`;
const HISTORY_HOURS = 12;
const MAX_CHART_POINTS = 144;

const WEATHER_ICON_MAP = {
  "clear-night": "clear_night",
  "cloudy": "cloud",
  "exceptional": "warning",
  "fog": "foggy",
  "hail": "weather_hail",
  "lightning": "thunderstorm",
  "lightning-rainy": "thunderstorm_and_rain",
  "partlycloudy": "partly_cloudy_day",
  "pouring": "rainy_heavy",
  "rainy": "rainy",
  "snowy": "snowy",
  "snowy-rainy": "weather_snowy_rainy",
  "sunny": "sunny",
  "windy": "air",
  "windy-variant": "airwave",
};

const charts = {};
let sensorsConfig = {};

function formatTimestamp(isoString) {
  const d = new Date(isoString);
  return d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
}

function formatUpdated(isoString) {
  const d = new Date(isoString);
  return `Zaktualizowano: ${d.toLocaleTimeString("pl-PL")}`;
}

function resolveIcon(iconStr) {
  return iconStr.replace(/^mdi:/, "");
}

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function flashValue(element, color) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  element.animate([
    { backgroundColor: "transparent" },
    { backgroundColor: color + "22", offset: 0.3 },
    { backgroundColor: "transparent" }
  ], { duration: 600, easing: "ease-out" });
}

function createCard(sensorKey, sensor, index) {
  const card = document.createElement("article");
  card.className = "weather-card";
  card.id = `card-${sensorKey}`;
  card.style.setProperty("--card-index", index);
  card.style.setProperty("--sensor-color", sensor.color);

  if (sensor.type === "condition") {
    card.innerHTML = `
      <div class="weather-card__header">
        <span class="weather-card__icon weather-card__icon--condition material-symbols-rounded" id="${sensorKey}-icon">${resolveIcon(sensor.icon)}</span>
        <span class="weather-card__label">${sensor.name}</span>
      </div>
      <div class="weather-card__value-wrap">
        <span class="weather-card__value weather-card__value--condition" id="${sensorKey}-value">--</span>
      </div>
      <p class="weather-card__updated" id="${sensorKey}-updated">Oczekiwanie na dane...</p>
    `;
  } else {
    card.innerHTML = `
      <div class="weather-card__header">
        <span class="weather-card__icon material-symbols-rounded">${resolveIcon(sensor.icon)}</span>
        <span class="weather-card__label">${sensor.name}</span>
      </div>
      <div class="weather-card__value-wrap">
        <span class="weather-card__value" id="${sensorKey}-value">--</span>
        <span class="weather-card__unit" id="${sensorKey}-unit"></span>
      </div>
      <p class="weather-card__updated" id="${sensorKey}-updated">Oczekiwanie na dane...</p>
      <div class="weather-card__chart">
        <canvas id="chart-${sensorKey}" aria-label="${sensor.name} — wykres z ostatnich ${HISTORY_HOURS} godzin" role="img"></canvas>
      </div>
    `;
  }

  return card;
}

function createChart(canvasId, parameter, color, decimals, unit) {
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
            label: (ctx) => ` ${ctx.parsed.y.toFixed(decimals)} ${unit}`,
            title: (items) => formatTimestamp(items[0].raw.x),
          }
        }
      },
      scales: {
        x: {
          type: "time",
          time: { unit: "hour", tooltipFormat: "HH:mm", displayFormats: { hour: "HH:mm" } },
          grid: { color: getCssVar("--color-border") },
          ticks: {
            font: { family: "JetBrains Mono", size: 11 },
            color: getCssVar("--color-text-secondary"),
            maxTicksLimit: 6,
          }
        },
        y: {
          grid: { color: getCssVar("--color-border") },
          ticks: {
            font: { family: "JetBrains Mono", size: 11 },
            color: getCssVar("--color-text-secondary"),
            callback: function(value) {
              return Number(value).toFixed(decimals);
            },
          },
          afterFit(scale) {
            scale.width = 52;
          },
        }
      }
    }
  });
}

function updateChartTheme() {
  const border = getCssVar("--color-border");
  const tick = getCssVar("--color-text-secondary");
  Object.values(charts).forEach(c => {
    c.options.scales.x.grid.color = border;
    c.options.scales.y.grid.color = border;
    c.options.scales.x.ticks.color = tick;
    c.options.scales.y.ticks.color = tick;
    c.update();
  });
}

function updateCard(parameter, value, unit, timestamp, icon) {
  const sensor = sensorsConfig[parameter];
  if (!sensor) return;

  if (sensor.type === "condition") {
    const valueEl = document.getElementById(`${parameter}-value`);
    const updatedEl = document.getElementById(`${parameter}-updated`);
    const iconEl = document.getElementById(`${parameter}-icon`);
    if (valueEl) {
      valueEl.textContent = value ?? "—";
      flashValue(valueEl, sensor.color);
    }
    if (iconEl && icon) {
      iconEl.textContent = WEATHER_ICON_MAP[icon] || icon;
    }
    if (updatedEl) updatedEl.textContent = formatUpdated(timestamp);
  } else {
    const valueEl = document.getElementById(`${parameter}-value`);
    const unitEl = document.getElementById(`${parameter}-unit`);
    const updatedEl = document.getElementById(`${parameter}-updated`);

    const decimals = sensor.round ?? 1;
    if (valueEl) {
      valueEl.textContent = Number(value).toFixed(decimals);
      flashValue(valueEl, sensor.color);
    }
    if (unitEl) unitEl.textContent = unit;
    if (updatedEl) updatedEl.textContent = formatUpdated(timestamp);
  }
}

function appendChartPoint(parameter, value, timestamp) {
  const chart = charts[parameter];
  if (!chart) return;
  chart.data.datasets[0].data.push({ x: new Date(timestamp), y: value });
  if (chart.data.datasets[0].data.length > MAX_CHART_POINTS) {
    chart.data.datasets[0].data.shift();
  }
  chart.update("none");
}

async function loadHistory(parameter) {
  try {
    const res = await fetch(`${API_BASE}/history/${parameter}?hours=${HISTORY_HOURS}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const history = await res.json();

    const sensor = sensorsConfig[parameter];
    if (sensor?.type === "condition") {
      if (history.length > 0) {
        const last = history[history.length - 1];
        updateCard(parameter, last.value_str, null, last.timestamp, last.icon);
      }
      return;
    }

    const chart = charts[parameter];
    if (!chart) return;
    chart.data.datasets[0].data = history.map(r => ({
      x: new Date(r.timestamp),
      y: r.value,
    }));
    chart.update();
    if (history.length > 0) {
      const last = history[history.length - 1];
      updateCard(parameter, last.value, last.unit, last.timestamp);
    }
  } catch (err) {
    console.error(`[History] Error fetching ${parameter}:`, err);
  }
}

function connectWebSocket() {
  const statusEl = document.getElementById("connection-status");
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    statusEl.className = "status status--connected";
    statusEl.innerHTML = `<span class="status__dot"></span><span class="status__label">Połączono</span>`;
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateCard(data.parameter, data.value, data.unit, data.timestamp, data.icon);
      appendChartPoint(data.parameter, data.value, data.timestamp);
    } catch (e) {
      console.warn("[WS] Message parse error:", e);
    }
  };

  ws.onclose = () => {
    statusEl.className = "status status--disconnected";
    statusEl.innerHTML = `<span class="status__dot"></span><span class="status__label">Rozłączono</span>`;
    setTimeout(connectWebSocket, 5000);
  };

  ws.onerror = (err) => {
    console.error("[WS] Error:", err);
    ws.close();
  };
}

function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  const html = document.documentElement;
  let theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  html.setAttribute("data-theme", theme);

  const updateIcon = () => {
    btn.querySelector(".material-symbols-rounded").textContent =
      theme === "dark" ? "light_mode" : "dark_mode";
    btn.setAttribute("aria-label",
      theme === "dark" ? "Włącz jasny motyw" : "Włącz ciemny motyw");
  };
  updateIcon();

  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", theme);
    updateIcon();
    updateChartTheme();
  });
}

async function loadSensors() {
  const res = await fetch(`${API_BASE}/sensors`);
  if (!res.ok) throw new Error(`Failed to load sensors: HTTP ${res.status}`);
  return res.json();
}

async function init() {
  initThemeToggle();
  sensorsConfig = await loadSensors();
  const grid = document.getElementById("weather-grid");

  let idx = 0;
  for (const [key, sensor] of Object.entries(sensorsConfig)) {
    grid.appendChild(createCard(key, sensor, idx));
    if (sensor.type !== "condition") {
      charts[key] = createChart(`chart-${key}`, key, sensor.color, sensor.round ?? 1, sensor.unit);
    }
    idx++;
  }

  await Promise.all(
    Object.keys(sensorsConfig).map(key => loadHistory(key))
  );

  connectWebSocket();
}

document.addEventListener("DOMContentLoaded", init);
