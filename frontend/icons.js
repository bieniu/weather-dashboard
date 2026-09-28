// Weather condition codes -> SVG icons, with day/night variants.
const DAY_START_HOUR = 6;
const DAY_END_HOUR = 20;
const PARTLY_CLOUDY_DAY = "weather_icons/partly-cloudy-day.svg";
const PARTLY_CLOUDY_NIGHT = "weather_icons/partly-cloudy-night.svg";

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

// Last sun position from the backend ("above_horizon" / "below_horizon").
export const sunState = { value: null };

export function isSunValue(value) {
  return value === "above_horizon" || value === "below_horizon";
}

function isDaytimeNow(timestamp) {
  if (sunState.value) return sunState.value === "above_horizon";
  const hour = (timestamp ? new Date(timestamp) : new Date()).getHours();
  return hour >= DAY_START_HOUR && hour < DAY_END_HOUR;
}

/**
 * Icon path for a condition code (`mdi:` prefix optional). Partly cloudy uses
 * `isDaytime` when given (forecast periods), otherwise the sun state, and
 * without one the local hour of `timestamp` (or now).
 */
export function getConditionSvgPath(iconField, timestamp, isDaytime) {
  const raw = iconField.startsWith("mdi:") ? iconField.slice(4) : iconField;
  const key = MDI_TO_KEY[raw] || raw;

  if (key === "partlycloudy") {
    const day = isDaytime !== undefined ? isDaytime : isDaytimeNow(timestamp);
    return day ? PARTLY_CLOUDY_DAY : PARTLY_CLOUDY_NIGHT;
  }
  const file = SVG_FILE[key];
  return file ? `weather_icons/${file}` : null;
}

export function resolveIcon(iconStr) {
  return iconStr.replace(/^mdi:/, "");
}

export function resetIcons() {
  sunState.value = null;
}
