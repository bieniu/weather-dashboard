// Entry module (index.html loads it as app.js?v=N). The other modules are
// imported without a query string and precached by service-worker.js.
import { getJson, loadSensors, resetSensors } from "./api.js";
import {
  loadAlerts,
  requestNotificationPermission,
  resetAlerts,
  scheduleAlertCheck,
} from "./alerts.js";
import {
  createCard,
  isChartSensor,
  loadCurrent,
  loadForecast,
  loadSunState,
  resetCards,
} from "./cards.js";
import { chartPoints, charts, createChart, loadAllHistory, resetCharts } from "./charts.js";
import { resetIcons } from "./icons.js";
import { initThemeToggle } from "./theme.js";
import { connectWebSocket, reconnectNow, resetWebSocket } from "./ws.js";

const SENSORS_ERROR =
  "Nie udało się wczytać konfiguracji czujników. Odśwież stronę, aby spróbować ponownie.";

export async function initAnalytics() {
  try {
    const { host, id } = await getJson("/analytics");
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

export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch((err) => {
    console.warn("[SW] Registration failed:", err);
  });
}

function showGridError(grid, message) {
  const error = document.createElement("p");
  error.className = "grid__error";
  error.setAttribute("role", "alert");
  error.textContent = message;
  grid.replaceChildren(error);
}

export async function init() {
  // Independent of the API being reachable: an offline visit must still get
  // the worker so the next one can use the precached shell.
  registerServiceWorker();
  initThemeToggle();
  const grid = document.getElementById("weather-grid");

  let sensors;
  try {
    sensors = await loadSensors();
  } catch (err) {
    console.error("[Sensors] Error loading sensor configuration:", err);
    showGridError(grid, SENSORS_ERROR);
    return;
  }

  Object.entries(sensors).forEach(([key, sensor], index) => {
    grid.appendChild(createCard(key, sensor, index));
    if (isChartSensor(sensor)) {
      charts[key] = createChart(`chart-${key}`, sensor.color, sensor.round ?? 1, sensor.unit);
      chartPoints[key] = [];
    }
  });

  // Live updates first, so nothing pushed while the initial requests are in
  // flight is lost (loadHistory merges points that arrived in the meantime).
  connectWebSocket();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") reconnectNow();
  });
  window.addEventListener("online", reconnectNow);

  await Promise.all([
    loadCurrent(),
    loadAllHistory(),
    loadForecast(),
    loadAlerts(),
    loadSunState(),
  ]);
  scheduleAlertCheck();
  initAnalytics();

  document.addEventListener("click", requestNotificationPermission, { once: true });
}

/** Clears every module's state (tests call this before each case). */
export function resetState() {
  resetSensors();
  resetIcons();
  resetCards();
  resetCharts();
  resetAlerts();
  resetWebSocket();
}

document.addEventListener("DOMContentLoaded", init);
