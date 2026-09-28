// Live readings over the WebSocket, with backoff reconnects and a REST
// backfill of whatever was missed while disconnected.
import { handleAlertUpdate, loadAlerts, toAlert } from "./alerts.js";
import { applySunState, loadCurrent, loadForecast, updateCard } from "./cards.js";
import { appendChartPoint, loadAllHistory } from "./charts.js";

const WS_PATH = "/api/weather/ws";
const WS_RECONNECT_BASE_MS = 5000;
const WS_RECONNECT_MAX_MS = 60000;
const WS_RECONNECT_JITTER = 0.2;
const WS_STATE_CONNECTING = 0;
const WS_STATE_OPEN = 1;

export const wsState = {
  socket: null,
  reconnectTimer: null,
  reconnectAttempt: 0,
  attempted: false,
};

function wsUrl() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${WS_PATH}`;
}

function setConnectionStatus(connected) {
  const statusEl = document.getElementById("connection-status");
  if (!statusEl) return;
  statusEl.className = `status ${connected ? "status--connected" : "status--disconnected"}`;
  const label = statusEl.querySelector(".status__label");
  if (label) label.textContent = connected ? "Połączono" : "Rozłączono";
}

// 5 s, 10 s, 20 s, 40 s, 60 s, 60 s ... with ±20 % jitter so clients do not
// reconnect in lockstep after an outage.
function reconnectDelay(attempt) {
  const base = Math.min(WS_RECONNECT_BASE_MS * 2 ** attempt, WS_RECONNECT_MAX_MS);
  return base * (1 + (Math.random() * 2 - 1) * WS_RECONNECT_JITTER);
}

function scheduleReconnect() {
  if (wsState.reconnectTimer) return;
  const delay = reconnectDelay(wsState.reconnectAttempt);
  wsState.reconnectAttempt += 1;
  wsState.reconnectTimer = setTimeout(() => {
    wsState.reconnectTimer = null;
    connectWebSocket();
  }, delay);
}

// Tab became visible / browser back online: do not wait out the backoff.
export function reconnectNow() {
  const state = wsState.socket?.readyState;
  if (state === WS_STATE_OPEN || state === WS_STATE_CONNECTING) return;
  clearTimeout(wsState.reconnectTimer);
  wsState.reconnectTimer = null;
  wsState.reconnectAttempt = 0;
  connectWebSocket();
}

// Whatever was pushed while disconnected is gone: reload cards, charts,
// alerts and the forecast so the dashboard shows no silent gap.
function backfillAfterReconnect() {
  return Promise.all([loadCurrent(), loadAllHistory(), loadAlerts(), loadForecast()]);
}

function handleMessage(data) {
  if (data.parameter === "alerts") {
    handleAlertUpdate(toAlert(data));
  } else if (data.parameter === "sun") {
    applySunState(data.value);
  } else {
    updateCard(data.parameter, data.value, data.unit, data.timestamp, data.icon);
    appendChartPoint(data.parameter, data.value, data.timestamp);
  }
}

export function connectWebSocket() {
  // Only the very first attempt (page load, initial requests in flight) skips
  // the backfill; if that attempt fails, the first successful open reloads
  // everything the failed initial requests could not.
  const isFirstAttempt = !wsState.attempted;
  wsState.attempted = true;
  const socket = new WebSocket(wsUrl());
  wsState.socket = socket;

  socket.onopen = () => {
    setConnectionStatus(true);
    wsState.reconnectAttempt = 0;
    if (!isFirstAttempt) backfillAfterReconnect();
  };

  socket.onmessage = (event) => {
    try {
      handleMessage(JSON.parse(event.data));
    } catch (e) {
      console.warn("[WS] Message parse error:", e);
    }
  };

  socket.onclose = () => {
    if (socket !== wsState.socket) return; // superseded by reconnectNow(); ignore
    setConnectionStatus(false);
    scheduleReconnect();
  };

  socket.onerror = (err) => {
    console.error("[WS] Error:", err);
    socket.close();
  };
}

export function resetWebSocket() {
  clearTimeout(wsState.reconnectTimer);
  Object.assign(wsState, {
    socket: null,
    reconnectTimer: null,
    reconnectAttempt: 0,
    attempted: false,
  });
}
