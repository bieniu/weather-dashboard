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

function getConditionSvgPath(iconField, timestamp, isDaytime) {
  const raw = iconField.startsWith("mdi:") ? iconField.slice(4) : iconField;
  const key = MDI_TO_KEY[raw] || raw;

  if (key === "partlycloudy") {
    if (isDaytime !== undefined) {
      return isDaytime
        ? "weather_icons/partly-cloudy-day.svg"
        : "weather_icons/partly-cloudy-night.svg";
    }
    if (sunState.value === "above_horizon") {
      return "weather_icons/partly-cloudy-day.svg";
    }
    if (sunState.value === "below_horizon") {
      return "weather_icons/partly-cloudy-night.svg";
    }
    const date = timestamp ? new Date(timestamp) : new Date();
    const hour = date.getHours();
    return hour >= 6 && hour < 20
      ? "weather_icons/partly-cloudy-day.svg"
      : "weather_icons/partly-cloudy-night.svg";
  }
  const file = SVG_FILE[key];
  return file ? `weather_icons/${file}` : null;
}

function getPolishDayAbbr(date) {
  const days = ["niedziela", "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota"];
  return days[date.getDay()];
}

const ALERT_ICONS = {
  yellow: "weather_icons/alert-yellow.svg",
  orange: "weather_icons/alert-orange.svg",
  red: "weather_icons/alert-red.svg",
};
const ALERT_GREEN_ICON = "weather_icons/alert-green.svg";

const charts = {};
let sensorsConfig = {};
const sunState = { value: null };
const conditionIconMap = {};

const alerts = [];
let alertTimerId = null;

function showAlertCard(alert) {
  const card = document.getElementById("card-alerts");
  if (!card) return;

  const img = document.getElementById("alerts-icon-img");
  if (img) {
    img.src =
      alert.level == null ? ALERT_GREEN_ICON : ALERT_ICONS[alert.level] || ALERT_ICONS.yellow;
    img.alt = alert.level ?? "green";
  }
  const valueEl = document.getElementById("alerts-value");
  if (valueEl) valueEl.textContent = alert.value;
  const updatedEl = document.getElementById("alerts-updated");
  if (updatedEl) updatedEl.textContent = alert.updatedText || "";

  card.style.display = "";
}

function hideAlertCard() {
  const card = document.getElementById("card-alerts");
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
    sendAlertNotification(alertData);
  } else {
    Object.assign(existing, alertData);
  }
  updateAlertVisibility();
}

function sendAlertNotification(alertData) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const levelLabel =
    { yellow: "Żółty", orange: "Pomarańczowy", red: "Czerwony", null: "Zielony" }[
      alertData.level
    ] || alertData.level;
  const validTo = new Date(alertData.valid_to);
  const now = new Date();
  const validToText =
    validTo.getFullYear() === now.getFullYear() &&
    validTo.getMonth() === now.getMonth() &&
    validTo.getDate() === now.getDate()
      ? validTo.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })
      : `${validTo.toLocaleDateString("pl-PL", { day: "numeric", month: "long" })}, ${validTo.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })}`;
  new Notification("Alert meteorologiczny", {
    body: `${levelLabel} alert: ${alertData.value}\nWażny do: ${validToText}`,
    tag: alertData.timestamp,
  });
}

function requestNotificationPermission() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    Notification.requestPermission();
  }
}

function rerenderConditionIcons() {
  for (const [param, sensor] of Object.entries(sensorsConfig)) {
    if (sensor.type === "condition" && conditionIconMap[param]) {
      const img = document.getElementById(`${param}-icon-img`);
      if (img) img.src = getConditionSvgPath(conditionIconMap[param]);
    }
  }
}

async function loadSunState() {
  try {
    const res = await fetch(`${API_BASE}/sun`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.value === "above_horizon" || data.value === "below_horizon") {
      sunState.value = data.value;
      rerenderConditionIcons();
    }
  } catch (err) {
    console.warn("[Sun] Error loading sun state:", err);
  }
}

async function loadForecast() {
  try {
    const res = await fetch(`${API_BASE}/forecast`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) {
      const forecastKey = Object.entries(sensorsConfig).find(([, s]) => s.type === "forecast")?.[0];
      if (forecastKey) {
        updateCard(forecastKey, data, null, new Date().toISOString());
      }
    }
  } catch (err) {
    console.error("[Forecast] Error loading forecast:", err);
  }
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

  if (sensor.type === "alerts") {
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
  } else if (sensor.type === "forecast") {
    card.innerHTML = `
      <div class="weather-card__header">
        <span class="weather-card__label">${sensor.name}</span>
      </div>
      <div class="forecast-grid" id="${sensorKey}-forecast">
        <div class="forecast-col">
          <div class="forecast-col__day">--</div>
          <div class="forecast-col__period">--</div>
          <img class="forecast-col__icon" src="" alt="">
          <div class="forecast-col__temp"><span class="material-symbols-rounded forecast-col__val-icon">thermometer</span><span class="forecast-col__temp-value">--</span></div>
          <div class="forecast-col__precip"><span class="material-symbols-rounded forecast-col__val-icon">water_drop</span><span class="forecast-col__precip-value">--</span></div>
          <div class="forecast-col__cloud"><span class="material-symbols-rounded forecast-col__val-icon">cloud</span><span class="forecast-col__cloud-value">--</span></div>
        </div>
        <div class="forecast-col">
          <div class="forecast-col__day">--</div>
          <div class="forecast-col__period">--</div>
          <img class="forecast-col__icon" src="" alt="">
          <div class="forecast-col__temp"><span class="material-symbols-rounded forecast-col__val-icon">thermometer</span><span class="forecast-col__temp-value">--</span></div>
          <div class="forecast-col__precip"><span class="material-symbols-rounded forecast-col__val-icon">water_drop</span><span class="forecast-col__precip-value">--</span></div>
          <div class="forecast-col__cloud"><span class="material-symbols-rounded forecast-col__val-icon">cloud</span><span class="forecast-col__cloud-value">--</span></div>
        </div>
        <div class="forecast-col">
          <div class="forecast-col__day">--</div>
          <div class="forecast-col__period">--</div>
          <img class="forecast-col__icon" src="" alt="">
          <div class="forecast-col__temp"><span class="material-symbols-rounded forecast-col__val-icon">thermometer</span><span class="forecast-col__temp-value">--</span></div>
          <div class="forecast-col__precip"><span class="material-symbols-rounded forecast-col__val-icon">water_drop</span><span class="forecast-col__precip-value">--</span></div>
          <div class="forecast-col__cloud"><span class="material-symbols-rounded forecast-col__val-icon">cloud</span><span class="forecast-col__cloud-value">--</span></div>
        </div>
        <div class="forecast-col">
          <div class="forecast-col__day">--</div>
          <div class="forecast-col__period">--</div>
          <img class="forecast-col__icon" src="" alt="">
          <div class="forecast-col__temp"><span class="material-symbols-rounded forecast-col__val-icon">thermometer</span><span class="forecast-col__temp-value">--</span></div>
          <div class="forecast-col__precip"><span class="material-symbols-rounded forecast-col__val-icon">water_drop</span><span class="forecast-col__precip-value">--</span></div>
          <div class="forecast-col__cloud"><span class="material-symbols-rounded forecast-col__val-icon">cloud</span><span class="forecast-col__cloud-value">--</span></div>
        </div>
        <div class="forecast-col">
          <div class="forecast-col__day">--</div>
          <div class="forecast-col__period">--</div>
          <img class="forecast-col__icon" src="" alt="">
          <div class="forecast-col__temp"><span class="material-symbols-rounded forecast-col__val-icon">thermometer</span><span class="forecast-col__temp-value">--</span></div>
          <div class="forecast-col__precip"><span class="material-symbols-rounded forecast-col__val-icon">water_drop</span><span class="forecast-col__precip-value">--</span></div>
          <div class="forecast-col__cloud"><span class="material-symbols-rounded forecast-col__val-icon">cloud</span><span class="forecast-col__cloud-value">--</span></div>
        </div>
      </div>
      <p class="weather-card__updated" id="${sensorKey}-updated">Oczekiwanie na dane...</p>
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
  if (!sensor || sensor.type === "alerts") return;

  const valueEl = document.getElementById(`${parameter}-value`);
  const updatedEl = document.getElementById(`${parameter}-updated`);
  if (updatedEl) updatedEl.textContent = formatUpdated(timestamp);

  if (sensor.type === "forecast") {
    const container = document.getElementById(`${parameter}-forecast`);
    if (!container || !Array.isArray(value)) return;
    const items = value.slice(1, 6); // skip first (current), take next 5
    const cols = container.children;
    for (let i = 0; i < Math.min(items.length, cols.length); i++) {
      const item = items[i];
      const col = cols[i];
      const dt = new Date(item.datetime);
      col.querySelector(".forecast-col__day").textContent = getPolishDayAbbr(dt);
      col.querySelector(".forecast-col__period").textContent = item.is_daytime ? "dzień" : "noc";
      const img = col.querySelector(".forecast-col__icon");
      img.src = getConditionSvgPath(item.condition, item.datetime, item.is_daytime);
      img.alt = item.condition;
      col.querySelector(".forecast-col__temp-value").textContent =
        `${Math.round(item.temperature)}°C`;
      col.querySelector(".forecast-col__precip-value").textContent =
        `${Math.round(item.precipitation)} mm`;
      col.querySelector(".forecast-col__cloud-value").textContent =
        `${Math.round(item.cloud_coverage)}%`;
    }
  } else if (sensor.type === "condition" || sensor.type === "text") {
    if (valueEl) valueEl.textContent = value ?? "—";
  } else {
    if (valueEl) valueEl.textContent = Number(value).toFixed(sensor.round ?? 1);
    const unitEl = document.getElementById(`${parameter}-unit`);
    if (unitEl) unitEl.textContent = unit;
  }

  if (sensor.type === "condition") {
    const iconField = icon || value;
    conditionIconMap[parameter] = iconField;
    const img = document.getElementById(`${parameter}-icon-img`);
    const fallback = document.getElementById(`${parameter}-icon-fallback`);
    if (value) {
      if (img) {
        img.src = getConditionSvgPath(iconField, timestamp);
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
    if (sensor?.type === "alerts" || sensor?.type === "forecast") return;

    const hours = sensor?.history_hours ?? HISTORY_HOURS;
    const res = await fetch(`${API_BASE}/history/${parameter}?hours=${hours}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const history = await res.json();

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
      if (data.parameter === "alerts") {
        handleAlertUpdate({
          value: data.value,
          valid_to: data.valid_to,
          level: data.level,
          timestamp: data.timestamp,
          updatedText: formatUpdated(data.timestamp),
        });
      } else if (data.parameter === "sun") {
        if (data.value === "above_horizon" || data.value === "below_horizon") {
          sunState.value = data.value;
          rerenderConditionIcons();
        }
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
    if (
      sensor.type !== "condition" &&
      sensor.type !== "text" &&
      sensor.type !== "alerts" &&
      sensor.type !== "forecast"
    ) {
      charts[key] = createChart(`chart-${key}`, key, sensor.color, sensor.round ?? 1, sensor.unit);
    }
    idx++;
  }

  await Promise.all(Object.keys(sensorsConfig).map((key) => loadHistory(key)));

  loadForecast();
  loadAlerts();
  loadSunState();
  scheduleAlertCheck();
  connectWebSocket();
  initAnalytics();

  document.addEventListener("click", requestNotificationPermission, { once: true });
}

document.addEventListener("DOMContentLoaded", init);

export {
  getConditionSvgPath,
  getPolishDayAbbr,
  rerenderConditionIcons,
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
  loadForecast,
  connectWebSocket,
  initThemeToggle,
  loadSensors,
  initAnalytics,
  init,
  charts,
  sensorsConfig,
  alerts,
  sunState,
  alertTimerId,
  ALERT_ICONS,
  ALERT_GREEN_ICON,
  showAlertCard,
  hideAlertCard,
  updateAlertVisibility,
  scheduleAlertCheck,
  handleAlertUpdate,
  sendAlertNotification,
  requestNotificationPermission,
  loadAlerts,
  loadSunState,
  API_BASE,
  HISTORY_HOURS,
  MAX_CHART_POINTS,
};
