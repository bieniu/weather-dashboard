const API_BASE = "/api/weather";
const WS_PROTOCOL = location.protocol === "https:" ? "wss:" : "ws:";
const WS_URL = `${WS_PROTOCOL}//${location.host}/api/weather/ws`;
const HISTORY_HOURS = 12;
const MAX_CHART_POINTS = 144;

const MDI_TO_KEY = {
  "weather-sunny": "sunny",
  "weather-cloudy": "cloudy",
  "weather-foggy": "fog",
  "weather-hail": "hail",
  "weather-partly-cloudy": "partlycloudy",
  "weather-pouring": "pouring",
  "weather-rainy": "rainy",
  "weather-snowy": "snowy",
  "weather-snowy-rainy": "snowy-rainy",
  "weather-windy": "windy",
  "weather-windy-variant": "windy-variant",
  "weather-lightning": "lightning",
  "weather-lightning-rainy": "lightning-rainy",
  "weather-clear-night": "clear-night",
  "clear-night": "clear-night",
  "weather-night": "clear-night",
  "weather-exceptional": "exceptional",
};

const SVG_FILE = {
  "clear-night": "clear-night.svg",
  cloudy: "cloudy.svg",
  exceptional: "exceptional.svg",
  fog: "fog.svg",
  hail: "hail.svg",
  lightning: "lightning.svg",
  "lightning-rainy": "lightning-rainy.svg",
  pouring: "pouring.svg",
  rainy: "rainy.svg",
  snowy: "snowy.svg",
  "snowy-rainy": "snowy-rainy.svg",
  sunny: "sunny.svg",
  windy: "windy.svg",
  "windy-variant": "windy-variant.svg",
};

function getConditionSvgPath(iconField) {
  const raw = iconField.startsWith("mdi:") ? iconField.slice(4) : iconField;
  const key = MDI_TO_KEY[raw] || raw;

  if (key === "partlycloudy") {
    const hour = new Date().getHours();
    return hour >= 6 && hour < 20
      ? "weather_icons/partly-cloudy-day.svg"
      : "weather_icons/partly-cloudy-night.svg";
  }
  const file = SVG_FILE[key];
  return file ? `weather_icons/${file}` : null;
}

const ALERT_ICONS = {
  yellow: "weather_icons/alert-yellow.svg",
  orange: "weather_icons/alert-orange.svg",
  red: "weather_icons/alert-red.svg",
};

const charts = {};
let sensorsConfig = {};

const alerts = [];
let alertTimerId = null;

function showAlertCard(alert) {
  const card = document.getElementById("card-alert");
  if (!card) return;

  const img = document.getElementById("alert-icon-img");
  if (img) {
    img.src = ALERT_ICONS[alert.level] || ALERT_ICONS.yellow;
    img.alt = alert.level;
  }
  const valueEl = document.getElementById("alert-value");
  if (valueEl) valueEl.textContent = alert.value;
  const updatedEl = document.getElementById("alert-updated");
  if (updatedEl) updatedEl.textContent = alert.updatedText || "";

  card.style.display = "";
}

function hideAlertCard() {
  const card = document.getElementById("card-alert");
  if (card) card.style.display = "none";
}

function updateAlertVisibility() {
  const now = new Date();
  for (let i = alerts.length - 1; i >= 0; i--) {
    if (new Date(alerts[i].valid_to) <= now) {
      alerts.splice(i, 1);
    }
  }
  const valid = alerts.find((a) => new Date(a.valid_to) > now);
  if (valid) showAlertCard(valid);
  else hideAlertCard();
}

function scheduleAlertCheck() {
  if (alertTimerId) return;
  alertTimerId = setInterval(updateAlertVisibility, 30000);
  window.addEventListener("beforeunload", () => {
    if (alertTimerId) clearInterval(alertTimerId);
  });
}

function handleAlertUpdate(alertData) {
  const existing = alerts.find((a) => a.timestamp === alertData.timestamp);
  if (!existing) {
    alerts.unshift(alertData);
  } else {
    Object.assign(existing, alertData);
  }
  updateAlertVisibility();
}

async function loadAlerts() {
  try {
    const res = await fetch(`${API_BASE}/alerts`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    alerts.length = 0;
    for (const r of data) {
      alerts.push({
        value: r.value_str,
        valid_to: r.valid_to,
        level: r.level,
        timestamp: r.timestamp,
        updatedText: formatUpdated(r.timestamp),
      });
    }
    updateAlertVisibility();
  } catch (err) {
    console.error("[Alerts] Error fetching alerts:", err);
  }
}

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

function createCard(sensorKey, sensor, index) {
  const card = document.createElement("article");
  card.className = "weather-card";
  card.id = `card-${sensorKey.replace(/_/g, "-")}`;
  card.style.setProperty("--card-index", index);
  if (sensor.color) {
    card.style.setProperty("--sensor-color", sensor.color);
  }

  if (sensor.type === "alert") {
    card.style.display = "none";
    card.innerHTML = `
      <div class="weather-card__header weather-card__header--condition">
        <span class="weather-card__label">${sensor.name}</span>
      </div>
      <div class="weather-card__value-wrap weather-card__value-wrap--condition">
        <img class="weather-card__icon weather-card__icon--condition weather-card__icon--img" id="${sensorKey}-icon-img" src="" alt="">
        <span class="weather-card__value weather-card__value--condition" id="${sensorKey}-value">--</span>
      </div>
      <p class="weather-card__updated" id="${sensorKey}-updated"></p>
    `;
  } else if (sensor.type === "condition" || sensor.type === "text") {
    const iconFile = sensorKey.replace(/_/g, "-");
    card.innerHTML = `
      <div class="weather-card__header weather-card__header--condition">
        <span class="weather-card__label">${sensor.name}</span>
      </div>
      <div class="weather-card__value-wrap weather-card__value-wrap--condition">
        ${
          sensor.type === "condition"
            ? `
        <img class="weather-card__icon weather-card__icon--condition weather-card__icon--img weather-card__icon--hidden" id="${sensorKey}-icon-img" src="" alt="">
        <img class="weather-card__icon weather-card__icon--condition weather-card__icon--img" id="${sensorKey}-icon-fallback" src="weather_icons/not-available.svg" alt="">
        `
            : `
        <img class="weather-card__icon weather-card__icon--condition weather-card__icon--img" id="${sensorKey}-icon-img" src="weather_icons/${iconFile}.svg" alt="">
        `
        }
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
        <canvas id="chart-${sensorKey}" aria-label="${sensor.name} — wykres z ostatnich ${sensor.history_hours ?? HISTORY_HOURS} godzin" role="img"></canvas>
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
      datasets: [
        {
          data: [],
          borderColor: color,
          backgroundColor: color + "22",
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.3,
          fill: true,
        },
      ],
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
          },
        },
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
          },
        },
        y: {
          grid: { color: getCssVar("--color-border") },
          ticks: {
            font: { family: "JetBrains Mono", size: 11 },
            color: getCssVar("--color-text-secondary"),
            callback: function (value) {
              return Number(value).toFixed(decimals);
            },
          },
          afterFit(scale) {
            scale.width = 52;
          },
        },
      },
    },
  });
}

function updateChartTheme() {
  const border = getCssVar("--color-border");
  const tick = getCssVar("--color-text-secondary");
  Object.values(charts).forEach((c) => {
    c.options.scales.x.grid.color = border;
    c.options.scales.y.grid.color = border;
    c.options.scales.x.ticks.color = tick;
    c.options.scales.y.ticks.color = tick;
    c.update();
  });
}

function updateCard(parameter, value, unit, timestamp, icon) {
  const sensor = sensorsConfig[parameter];
  if (!sensor || sensor.type === "alert") return;

  const valueEl = document.getElementById(`${parameter}-value`);
  const updatedEl = document.getElementById(`${parameter}-updated`);
  if (updatedEl) updatedEl.textContent = formatUpdated(timestamp);

  if (sensor.type === "condition" || sensor.type === "text") {
    if (valueEl) valueEl.textContent = value ?? "—";
  } else {
    if (valueEl) valueEl.textContent = Number(value).toFixed(sensor.round ?? 1);
    const unitEl = document.getElementById(`${parameter}-unit`);
    if (unitEl) unitEl.textContent = unit;
  }

  if (sensor.type === "condition") {
    const img = document.getElementById(`${parameter}-icon-img`);
    const fallback = document.getElementById(`${parameter}-icon-fallback`);
    if (value) {
      if (img) {
        img.src = getConditionSvgPath(icon || value);
        img.alt = value;
        img.classList.remove("weather-card__icon--hidden");
      }
      if (fallback) fallback.classList.add("weather-card__icon--hidden");
    } else {
      if (img) img.classList.add("weather-card__icon--hidden");
      if (fallback) fallback.classList.remove("weather-card__icon--hidden");
    }
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
    const sensor = sensorsConfig[parameter];
    const hours = sensor?.history_hours ?? HISTORY_HOURS;
    const res = await fetch(`${API_BASE}/history/${parameter}?hours=${hours}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const history = await res.json();

    if (sensor?.type === "alert") return;

    if (sensor?.type === "condition" || sensor?.type === "text") {
      if (history.length > 0) {
        const last = history[history.length - 1];
        updateCard(parameter, last.value_str, null, last.timestamp, last.icon);
      }
      return;
    }

    const chart = charts[parameter];
    if (!chart) return;
    chart.data.datasets[0].data = history.map((r) => ({
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
      if (data.parameter === "alert") {
        handleAlertUpdate({
          value: data.value,
          valid_to: data.valid_to,
          level: data.level,
          timestamp: data.timestamp,
          updatedText: formatUpdated(data.timestamp),
        });
      } else {
        updateCard(data.parameter, data.value, data.unit, data.timestamp, data.icon);
        appendChartPoint(data.parameter, data.value, data.timestamp);
      }
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
    btn.setAttribute("aria-label", theme === "dark" ? "Włącz jasny motyw" : "Włącz ciemny motyw");
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

async function initAnalytics() {
  try {
    const res = await fetch(`${API_BASE}/analytics`);
    if (!res.ok) return;
    const { host, id } = await res.json();
    if (host && id) {
      const s = document.createElement("script");
      s.src = `${host.replace(/\/+$/, "")}/script.js`;
      s.dataset.websiteId = id;
      s.defer = true;
      document.head.appendChild(s);
    }
  } catch {
    /* analytics non-critical */
  }
}

async function init() {
  initThemeToggle();
  sensorsConfig = await loadSensors();
  const grid = document.getElementById("weather-grid");

  let idx = 0;
  for (const [key, sensor] of Object.entries(sensorsConfig)) {
    grid.appendChild(createCard(key, sensor, idx));
    if (sensor.type !== "condition" && sensor.type !== "text" && sensor.type !== "alert") {
      charts[key] = createChart(`chart-${key}`, key, sensor.color, sensor.round ?? 1, sensor.unit);
    }
    idx++;
  }

  await Promise.all(Object.keys(sensorsConfig).map((key) => loadHistory(key)));

  await loadAlerts();
  scheduleAlertCheck();

  connectWebSocket();
  initAnalytics();
}

document.addEventListener("DOMContentLoaded", init);

export {
  getConditionSvgPath,
  formatTimestamp,
  formatUpdated,
  resolveIcon,
  getCssVar,
  createCard,
  createChart,
  updateChartTheme,
  updateCard,
  appendChartPoint,
  loadHistory,
  connectWebSocket,
  initThemeToggle,
  loadSensors,
  initAnalytics,
  init,
  charts,
  sensorsConfig,
  alerts,
  alertTimerId,
  ALERT_ICONS,
  showAlertCard,
  hideAlertCard,
  updateAlertVisibility,
  scheduleAlertCheck,
  handleAlertUpdate,
  loadAlerts,
  API_BASE,
  HISTORY_HOURS,
  MAX_CHART_POINTS,
};
