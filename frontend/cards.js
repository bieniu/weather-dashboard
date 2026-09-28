// Sensor cards: markup per sensor type, value updates and the REST loaders
// that feed them.
import { getJson, historyHours, sensorsConfig } from "./api.js";
import { esc, formatUpdated, getPolishDayAbbr } from "./format.js";
import { getConditionSvgPath, isSunValue, resolveIcon, sunState } from "./icons.js";

const FORECAST_COLUMNS = 5;
const PLACEHOLDER = "--";
const WAITING = "Oczekiwanie na dane...";

const FORECAST_COL_HTML = `
  <div class="forecast-col">
    <div class="forecast-col__day">--</div>
    <div class="forecast-col__period">--</div>
    <img class="forecast-col__icon" src="" alt="">
    <div class="forecast-col__temp"><span class="material-symbols-rounded forecast-col__val-icon">thermometer</span><span class="forecast-col__temp-value">--</span></div>
    <div class="forecast-col__wind"><span class="material-symbols-rounded forecast-col__val-icon">air</span><span class="forecast-col__wind-value">--</span></div>
    <div class="forecast-col__precip"><span class="material-symbols-rounded forecast-col__val-icon">water_drop</span><span class="forecast-col__precip-value">--</span></div>
    <div class="forecast-col__cloud"><span class="material-symbols-rounded forecast-col__val-icon">cloud</span><span class="forecast-col__cloud-value">--</span></div>
  </div>`;

// Last icon code per condition sensor, re-resolved when the sun state changes.
const conditionIconMap = {};

// --- markup ---------------------------------------------------------------

const conditionHeader = (name) => `
  <div class="weather-card__header weather-card__header--condition">
    <span class="weather-card__label">${name}</span>
  </div>`;

function conditionBody(key, name, icons, updatedText) {
  return `${conditionHeader(name)}
    <div class="weather-card__value-wrap weather-card__value-wrap--condition">
      ${icons}
      <span class="weather-card__value weather-card__value--condition" id="${key}-value">--</span>
    </div>
    <p class="weather-card__updated" id="${key}-updated">${updatedText}</p>`;
}

const iconImg = (id, src, extraClass = "") =>
  `<img class="weather-card__icon weather-card__icon--condition weather-card__icon--img${extraClass}" id="${id}" src="${src}" alt="">`;

function alertsMarkup(key, name) {
  return conditionBody(key, name, iconImg(`${key}-icon-img`, ""), "");
}

function forecastMarkup(key, name) {
  return `
    <div class="weather-card__header">
      <span class="weather-card__label">${name}</span>
    </div>
    <div class="forecast-grid" id="${key}-forecast">${FORECAST_COL_HTML.repeat(FORECAST_COLUMNS)}
    </div>
    <p class="weather-card__updated" id="${key}-updated">${WAITING}</p>`;
}

function conditionMarkup(key, name) {
  const icons =
    iconImg(`${key}-icon-img`, "", " weather-card__icon--hidden") +
    iconImg(`${key}-icon-fallback`, "weather_icons/not-available.svg");
  return conditionBody(key, name, icons, WAITING);
}

function textMarkup(key, name) {
  const icon = iconImg(`${key}-icon-img`, `weather_icons/${key.replace(/_/g, "-")}.svg`);
  return conditionBody(key, name, icon, WAITING);
}

function numericMarkup(key, name, sensor) {
  return `
    <div class="weather-card__header">
      <span class="weather-card__icon material-symbols-rounded">${esc(resolveIcon(sensor.icon))}</span>
      <span class="weather-card__label">${name}</span>
    </div>
    <div class="weather-card__value-wrap">
      <span class="weather-card__value" id="${key}-value">--</span>
      <span class="weather-card__unit" id="${key}-unit"></span>
    </div>
    <p class="weather-card__updated" id="${key}-updated">${WAITING}</p>
    <div class="weather-card__chart">
      <canvas id="chart-${key}" aria-label="${name} — wykres z ostatnich ${esc(historyHours(sensor))} godzin" role="img"></canvas>
    </div>`;
}

// --- updates --------------------------------------------------------------

const fmt = (value, suffix) => (value != null ? `${Math.round(value)}${suffix}` : PLACEHOLDER);

/** Fills one forecast column, or resets it to placeholders when `item` is null. */
function fillForecastCol(col, item) {
  const set = (part, text) => {
    col.querySelector(`.forecast-col__${part}`).textContent = text;
  };
  set("day", item ? getPolishDayAbbr(new Date(item.datetime)) : PLACEHOLDER);
  set("period", item ? (item.is_daytime ? "dzień" : "noc") : PLACEHOLDER);
  const img = col.querySelector(".forecast-col__icon");
  img.src = item ? getConditionSvgPath(item.condition, item.datetime, item.is_daytime) : "";
  img.alt = item ? item.condition : "";
  set("temp-value", fmt(item?.temperature, "°C"));
  set("precip-value", fmt(item?.precipitation, " mm"));
  set("cloud-value", fmt(item?.cloud_coverage, "%"));
  set("wind-value", fmt(item?.wind_speed, " km/h"));
}

function updateForecast(parameter, { value }) {
  const container = document.getElementById(`${parameter}-forecast`);
  if (!container || !Array.isArray(value)) return;
  const items = value.slice(0, FORECAST_COLUMNS);
  [...container.children].forEach((col, i) => fillForecastCol(col, items[i] ?? null));
}

function updateText(parameter, { value }) {
  const valueEl = document.getElementById(`${parameter}-value`);
  if (valueEl) valueEl.textContent = value ?? "—";
}

function updateCondition(parameter, reading) {
  updateText(parameter, reading);
  const { value, timestamp } = reading;
  const iconField = reading.icon || value;
  conditionIconMap[parameter] = iconField;
  const img = document.getElementById(`${parameter}-icon-img`);
  const fallback = document.getElementById(`${parameter}-icon-fallback`);
  if (value && img) {
    img.src = getConditionSvgPath(iconField, timestamp);
    img.alt = value;
  }
  img?.classList.toggle("weather-card__icon--hidden", !value);
  fallback?.classList.toggle("weather-card__icon--hidden", Boolean(value));
}

function updateNumeric(parameter, { value, unit, sensor }) {
  const valueEl = document.getElementById(`${parameter}-value`);
  if (valueEl) valueEl.textContent = Number(value).toFixed(sensor.round ?? 1);
  const unitEl = document.getElementById(`${parameter}-unit`);
  if (unitEl) unitEl.textContent = unit;
}

// Markup and value renderer per sensor type; unknown types render as numeric.
// Alerts have no updater: alerts.js drives that card.
const CARD_TYPES = {
  alerts: { markup: alertsMarkup, update: null },
  forecast: { markup: forecastMarkup, update: updateForecast },
  condition: { markup: conditionMarkup, update: updateCondition },
  text: { markup: textMarkup, update: updateText },
  numeric: { markup: numericMarkup, update: updateNumeric },
};

function cardType(sensor) {
  return Object.hasOwn(CARD_TYPES, sensor.type) ? sensor.type : "numeric";
}

/** Numeric sensors are the ones with a history chart. */
export function isChartSensor(sensor) {
  return cardType(sensor) === "numeric";
}

export function createCard(sensorKey, sensor, index) {
  const type = cardType(sensor);
  const card = document.createElement("article");
  card.className = `weather-card weather-card--${type}`;
  card.id = `card-${sensorKey.replace(/_/g, "-")}`;
  card.style.setProperty("--card-index", index);
  if (sensor.color) card.style.setProperty("--sensor-color", sensor.color);
  if (type === "alerts") card.style.display = "none"; // shown by alerts.js
  card.innerHTML = CARD_TYPES[type].markup(esc(sensorKey), esc(sensor.name), sensor);
  return card;
}

export function updateCard(parameter, value, unit, timestamp, icon) {
  const sensor = sensorsConfig[parameter];
  const update = sensor && CARD_TYPES[cardType(sensor)].update;
  if (!update) return;
  const updatedEl = document.getElementById(`${parameter}-updated`);
  if (updatedEl) updatedEl.textContent = formatUpdated(timestamp);
  update(parameter, { value, unit, timestamp, icon, sensor });
}

function rerenderConditionIcons() {
  for (const [parameter, iconField] of Object.entries(conditionIconMap)) {
    const img = iconField && document.getElementById(`${parameter}-icon-img`);
    if (img) img.src = getConditionSvgPath(iconField);
  }
}

/** Stores a valid sun position (anything else is ignored) and redraws the icons. */
export function applySunState(value) {
  if (!isSunValue(value)) return;
  sunState.value = value;
  rerenderConditionIcons();
}

// --- loaders --------------------------------------------------------------

// Card values for every sensor in one request; histories are only for charts.
export async function loadCurrent() {
  try {
    const current = await getJson("/current");
    for (const [parameter, reading] of Object.entries(current)) {
      const sensor = sensorsConfig[parameter];
      if (!reading || !sensor) continue;
      const type = cardType(sensor);
      if (type === "condition" || type === "text") {
        updateCard(parameter, reading.value_str, null, reading.timestamp, reading.icon);
      } else if (type === "numeric") {
        updateCard(parameter, reading.value, reading.unit, reading.timestamp);
      }
    }
  } catch (err) {
    console.error("[Current] Error fetching current readings:", err);
  }
}

export async function loadForecast() {
  try {
    const { forecast, timestamp } = await getJson("/forecast");
    const forecastKey = Object.keys(sensorsConfig).find(
      (key) => sensorsConfig[key].type === "forecast",
    );
    if (forecastKey && Array.isArray(forecast) && forecast.length > 0) {
      updateCard(forecastKey, forecast, null, timestamp ?? new Date().toISOString());
    }
  } catch (err) {
    console.error("[Forecast] Error loading forecast:", err);
  }
}

export async function loadSunState() {
  try {
    applySunState((await getJson("/sun")).value);
  } catch (err) {
    console.warn("[Sun] Error loading sun state:", err);
  }
}

export function resetCards() {
  for (const key of Object.keys(conditionIconMap)) delete conditionIconMap[key];
}
