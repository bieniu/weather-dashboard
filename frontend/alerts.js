// Meteorological alerts: the full-width alert card, expiry and notifications.
import { getJson } from "./api.js";
import { TIME_FORMAT, formatUpdated } from "./format.js";

const ALERT_CHECK_MS = 30000;
const DATE_FORMAT = new Intl.DateTimeFormat("pl-PL", { day: "numeric", month: "long" });

// A null level means "no warnings" (green); unknown levels fall back to yellow.
export const ALERT_ICONS = {
  yellow: "weather_icons/alert-yellow.svg",
  orange: "weather_icons/alert-orange.svg",
  red: "weather_icons/alert-red.svg",
};
export const ALERT_GREEN_ICON = "weather_icons/alert-green.svg";
const ALERT_LABELS = { yellow: "Żółty", orange: "Pomarańczowy", red: "Czerwony" };
const ALERT_GREEN_LABEL = "Zielony";

// Active alerts, newest first.
export const alerts = [];
let alertTimerId = null;

/** The shape both the REST list and WebSocket messages are turned into. */
export function toAlert({ value, valid_to, level, timestamp }) {
  return { value, valid_to, level, timestamp, updatedText: formatUpdated(timestamp) };
}

export function showAlertCard(alert) {
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

export function hideAlertCard() {
  const card = document.getElementById("card-alerts");
  if (card) card.style.display = "none";
}

/** Drops expired (or undated) alerts, then shows the first one left or hides the card. */
export function updateAlertVisibility() {
  const now = new Date();
  for (let i = alerts.length - 1; i >= 0; i--) {
    if (!(new Date(alerts[i].valid_to) > now)) alerts.splice(i, 1);
  }
  if (alerts.length > 0) showAlertCard(alerts[0]);
  else hideAlertCard();
}

export function scheduleAlertCheck() {
  alertTimerId ??= setInterval(updateAlertVisibility, ALERT_CHECK_MS);
}

export function handleAlertUpdate(alert) {
  const existing = alerts.find((a) => a.timestamp === alert.timestamp);
  if (existing) {
    Object.assign(existing, alert);
  } else {
    alerts.unshift(alert);
    sendAlertNotification(alert);
  }
  updateAlertVisibility();
}

function isToday(date) {
  return date.toDateString() === new Date().toDateString();
}

export function sendAlertNotification(alert) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const levelLabel =
    alert.level == null ? ALERT_GREEN_LABEL : ALERT_LABELS[alert.level] || alert.level;
  const validTo = new Date(alert.valid_to);
  const time = TIME_FORMAT.format(validTo);
  const validToText = isToday(validTo) ? time : `${DATE_FORMAT.format(validTo)}, ${time}`;
  new Notification("Alert meteorologiczny", {
    body: `${levelLabel} alert: ${alert.value}\nWażny do: ${validToText}`,
    tag: alert.timestamp,
  });
}

export function requestNotificationPermission() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") Notification.requestPermission();
}

export async function loadAlerts() {
  try {
    const data = await getJson("/alerts");
    alerts.length = 0;
    for (const r of data) alerts.push(toAlert({ ...r, value: r.value_str }));
    updateAlertVisibility();
  } catch (err) {
    console.error("[Alerts] Error fetching alerts:", err);
  }
}

export function resetAlerts() {
  alerts.length = 0;
  clearInterval(alertTimerId);
  alertTimerId = null;
}
