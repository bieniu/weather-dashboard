// Backend access and the sensor configuration it serves.
export const API_BASE = "/api/weather";
export const HISTORY_HOURS = 24; // mirrors DEFAULT_HISTORY_HOURS in backend/app/config.py

// Filled once by loadSensors(); every other module reads it by parameter key.
export const sensorsConfig = {};

export async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function historyHours(sensor) {
  return sensor?.history_hours ?? HISTORY_HOURS;
}

export async function loadSensors() {
  const sensors = await getJson("/sensors");
  resetSensors();
  return Object.assign(sensorsConfig, sensors);
}

export function resetSensors() {
  for (const key of Object.keys(sensorsConfig)) delete sensorsConfig[key];
}
