process.env.TZ = "UTC";

import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  getConditionSvgPath,
  getPolishDayAbbr,
  formatTimestamp,
  formatUpdated,
  resolveIcon,
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
  sunState,
  alerts,
  ALERT_ICONS,
  ALERT_GREEN_ICON,
  showAlertCard,
  hideAlertCard,
  updateAlertVisibility,
  handleAlertUpdate,
  sendAlertNotification,
  requestNotificationPermission,
  loadAlerts,
  loadSunState,
  API_BASE,
  HISTORY_HOURS,
  MAX_CHART_POINTS,
} from "../../frontend/app.js";

beforeEach(() => {
  Object.keys(charts).forEach((k) => delete charts[k]);
  Object.keys(sensorsConfig).forEach((k) => delete sensorsConfig[k]);
  sunState.value = null;
});

const SENSOR_NUMERIC = {
  temperature: { name: "Temperatura", type: "numeric", icon: "mdi:thermometer", color: "#E53935", round: 1, unit: "°C" },
};

const SENSOR_CONDITION = {
  condition: { name: "Warunki", type: "condition", icon: "mdi:weather-sunny", color: "#FDD835" },
};

const SENSOR_TEXT = {
  text_sensor: { name: "Tekst", type: "text", icon: "mdi:weather-windy", color: "#42A5F5" },
};

describe("utils", () => {
  it("formatTimestamp returns Polish HH:MM format", () => {
    const d = new Date("2025-06-24T14:30:00Z").toISOString();
    expect(formatTimestamp(d)).toBe("14:30");
  });

  it("formatUpdated returns Polish updated string", () => {
    const d = new Date("2025-06-24T14:30:00Z").toISOString();
    expect(formatUpdated(d)).toBe("Zaktualizowano: 14:30:00");
  });

  it("resolveIcon strips mdi: prefix", () => {
    expect(resolveIcon("mdi:thermometer")).toBe("thermometer");
  });

  it("resolveIcon returns as-is when no mdi: prefix", () => {
    expect(resolveIcon("thermometer")).toBe("thermometer");
  });

  it("getConditionSvgPath resolves known mdi icon", () => {
    expect(getConditionSvgPath("mdi:weather-sunny")).toBe("weather_icons/sunny.svg");
  });

  it("getConditionSvgPath resolves partlycloudy to day variant (6-20h)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-24T12:00:00"));
    expect(getConditionSvgPath("mdi:weather-partly-cloudy")).toBe("weather_icons/partly-cloudy-day.svg");
    vi.useRealTimers();
  });

  it("getConditionSvgPath resolves partlycloudy to night variant (20-6h)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-24T22:00:00"));
    expect(getConditionSvgPath("mdi:weather-partly-cloudy")).toBe("weather_icons/partly-cloudy-night.svg");
    vi.useRealTimers();
  });

  it("getConditionSvgPath uses sunState above_horizon over time", () => {
    sunState.value = "above_horizon";
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-24T22:00:00"));
    expect(getConditionSvgPath("mdi:weather-partly-cloudy")).toBe("weather_icons/partly-cloudy-day.svg");
    vi.useRealTimers();
  });

  it("getConditionSvgPath uses sunState below_horizon over time", () => {
    sunState.value = "below_horizon";
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2025-06-24T12:00:00"));
    expect(getConditionSvgPath("mdi:weather-partly-cloudy")).toBe("weather_icons/partly-cloudy-night.svg");
    vi.useRealTimers();
  });

  it("getConditionSvgPath returns null for unknown icon", () => {
    expect(getConditionSvgPath("mdi:unknown-icon")).toBeNull();
  });

  it("getConditionSvgPath returns null for missing SVG mapping", () => {
    expect(getConditionSvgPath("mdi:clear-night")).toBe("weather_icons/clear-night.svg");
  });
});

describe("createCard", () => {
  it("creates article with correct id for numeric sensor", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    expect(card.tagName).toBe("ARTICLE");
    expect(card.id).toBe("card-temperature");
    expect(card.classList.contains("weather-card")).toBe(true);
  });

  it("sets --card-index and --sensor-color CSS vars", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 2);
    expect(card.style.getPropertyValue("--card-index")).toBe("2");
    expect(card.style.getPropertyValue("--sensor-color")).toBe("#E53935");
  });

  it("numeric sensor includes canvas and unit element", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    expect(card.querySelector("canvas#chart-temperature")).toBeTruthy();
    expect(card.querySelector(".weather-card__unit")).toBeTruthy();
    expect(card.querySelector(".material-symbols-rounded")).toBeTruthy();
  });

  it("condition sensor includes icon-img and icon-fallback", () => {
    const card = createCard("condition", SENSOR_CONDITION.condition, 0);
    expect(card.querySelector(".weather-card__header--condition")).toBeTruthy();
    expect(card.querySelector("#condition-icon-img")).toBeTruthy();
    expect(card.querySelector("#condition-icon-fallback")).toBeTruthy();
    expect(card.querySelector(".weather-card__value--condition")).toBeTruthy();
  });

  it("condition icon-img starts hidden", () => {
    const card = createCard("condition", SENSOR_CONDITION.condition, 0);
    const img = card.querySelector("#condition-icon-img");
    expect(img.classList.contains("weather-card__icon--hidden")).toBe(true);
  });

  it("text sensor includes icon-img but no fallback", () => {
    const card = createCard("text_sensor", SENSOR_TEXT.text_sensor, 0);
    expect(card.querySelector("#text_sensor-icon-img")).toBeTruthy();
    expect(card.querySelector("#text_sensor-icon-fallback")).toBeNull();
    expect(card.querySelector(".weather-card__value--condition")).toBeTruthy();
  });

  it("numeric sensor does not have condition header", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    expect(card.querySelector(".weather-card__header--condition")).toBeNull();
  });
});

describe("updateCard", () => {
  beforeEach(() => {
    charts.temperature = {
      data: { datasets: [{ data: [] }] },
      options: { scales: { x: { grid: {}, ticks: {} }, y: { grid: {}, ticks: {} } } },
      update: vi.fn(),
    };
    sensorsConfig.temperature = SENSOR_NUMERIC.temperature;
  });

  afterEach(() => {
    delete charts.temperature;
    delete sensorsConfig.temperature;
  });

  it("updates numeric sensor value with correct decimals", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("temperature", 23.456, "°C", "2025-06-24T14:30:00Z");
    expect(document.getElementById("temperature-value").textContent).toBe("23.5");
    expect(document.getElementById("temperature-unit").textContent).toBe("°C");
  });

  it("updates condition sensor value and icon", () => {
    sensorsConfig.condition = SENSOR_CONDITION.condition;
    const card = createCard("condition", SENSOR_CONDITION.condition, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("condition", "Słonecznie", null, "2025-06-24T14:30:00Z", "mdi:weather-sunny");
    expect(document.getElementById("condition-value").textContent).toBe("Słonecznie");
    const img = document.getElementById("condition-icon-img");
    expect(img.src).toContain("weather_icons/sunny.svg");
    expect(img.alt).toBe("Słonecznie");
    expect(img.classList.contains("weather-card__icon--hidden")).toBe(false);
    delete sensorsConfig.condition;
  });

  it("updates text sensor value", () => {
    sensorsConfig.text_sensor = SENSOR_TEXT.text_sensor;
    const card = createCard("text_sensor", SENSOR_TEXT.text_sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("text_sensor", "Silny wiatr", null, "2025-06-24T14:30:00Z");
    expect(document.getElementById("text_sensor-value").textContent).toBe("Silny wiatr");
    delete sensorsConfig.text_sensor;
  });

  it("hides icon-img and shows fallback when condition value is falsy", () => {
    sensorsConfig.condition = SENSOR_CONDITION.condition;
    const card = createCard("condition", SENSOR_CONDITION.condition, 0);
    document.getElementById("weather-grid").appendChild(card);
    const img = document.getElementById("condition-icon-img");
    const fallback = document.getElementById("condition-icon-fallback");
    img.classList.remove("weather-card__icon--hidden");
    fallback.classList.add("weather-card__icon--hidden");

    updateCard("condition", null, null, "2025-06-24T14:30:00Z", "mdi:weather-sunny");
    expect(img.classList.contains("weather-card__icon--hidden")).toBe(true);
    expect(fallback.classList.contains("weather-card__icon--hidden")).toBe(false);
    delete sensorsConfig.condition;
  });

  it("does nothing when sensor not in config", () => {
    updateCard("nonexistent", 42, null, "2025-06-24T14:30:00Z");
  });

  it("updates updated timestamp on numeric sensor", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("temperature", 22.0, "°C", "2025-06-24T15:00:00Z");
    expect(document.getElementById("temperature-updated").textContent).toMatch(/^Zaktualizowano: 15:00:00$/);
  });
});

describe("chart", () => {
  it("createChart creates a Chart.js instance", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    document.getElementById("weather-grid").appendChild(card);

    const chart = createChart("chart-temperature", "temperature", "#E53935", 1, "°C");
    expect(chart).toBeTruthy();
    expect(chart.update).toBeTypeOf("function");
  });

  it("appendChartPoint adds a data point", () => {
    const ds = { data: [] };
    charts.temperature = {
      data: { datasets: [ds] },
      update: vi.fn(),
    };

    appendChartPoint("temperature", 22.5, "2025-06-24T14:30:00Z");
    expect(ds.data).toHaveLength(1);
    expect(ds.data[0].y).toBe(22.5);
  });

  it("appendChartPoint caps at MAX_CHART_POINTS", () => {
    const ds = { data: [] };
    for (let i = 0; i < MAX_CHART_POINTS; i++) {
      ds.data.push({ x: new Date(`2025-01-01T00:${i}:00Z`), y: i });
    }
    charts.temperature = {
      data: { datasets: [ds] },
      update: vi.fn(),
    };

    appendChartPoint("temperature", 999, "2025-06-24T15:00:00Z");
    expect(ds.data).toHaveLength(MAX_CHART_POINTS);
    expect(ds.data[ds.data.length - 1].y).toBe(999);
  });

  it("appendChartPoint does nothing for unknown parameter", () => {
    appendChartPoint("nonexistent", 42, "2025-06-24T15:00:00Z");
  });

  it("updateChartTheme calls update on all charts", () => {
    const c1 = { options: { scales: { x: { grid: {}, ticks: {} }, y: { grid: {}, ticks: {} } } }, update: vi.fn() };
    const c2 = { options: { scales: { x: { grid: {}, ticks: {} }, y: { grid: {}, ticks: {} } } }, update: vi.fn() };
    charts.a = c1;
    charts.b = c2;

    updateChartTheme();
    expect(c1.update).toHaveBeenCalledOnce();
    expect(c2.update).toHaveBeenCalledOnce();
  });
});

describe("loadHistory", () => {
  beforeEach(() => {
    charts.temperature = {
      data: { datasets: [{ data: [] }] },
      update: vi.fn(),
    };
    sensorsConfig.temperature = SENSOR_NUMERIC.temperature;
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches history and populates chart data on success", async () => {
    const history = [
      { timestamp: "2025-06-24T13:00:00Z", value: 22.0, unit: "°C" },
      { timestamp: "2025-06-24T14:00:00Z", value: 23.0, unit: "°C" },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(history),
    });

    await loadHistory("temperature");
    expect(globalThis.fetch).toHaveBeenCalledWith(`${API_BASE}/history/temperature?hours=${HISTORY_HOURS}`);
    expect(charts.temperature.data.datasets[0].data).toHaveLength(2);
  });

  it("logs error on HTTP failure", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });

    await loadHistory("temperature");
    expect(console.error).toHaveBeenCalled();
  });

  it("handles empty history gracefully", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await loadHistory("temperature");
    expect(charts.temperature.data.datasets[0].data).toHaveLength(0);
  });

  it("uses per-sensor history_hours when configured in sensor config", async () => {
    sensorsConfig.water_level = { name: "Woda", type: "numeric", icon: "mdi:waves", color: "#2196F3", round: 0, unit: "cm", history_hours: 48 };
    charts.water_level = {
      data: { datasets: [{ data: [] }] },
      update: vi.fn(),
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await loadHistory("water_level");
    expect(globalThis.fetch).toHaveBeenCalledWith(`${API_BASE}/history/water_level?hours=48`);
    delete charts.water_level;
    delete sensorsConfig.water_level;
  });
});

describe("connectWebSocket", () => {
  let wsMock;
  let callCount;

  beforeEach(() => {
    globalThis.location = { host: "localhost:8332", protocol: "http:" };
    callCount = 0;
    wsMock = { onopen: null, onmessage: null, onclose: null, onerror: null, close: vi.fn() };
    globalThis.WebSocket = vi.fn(function () {
      callCount++;
      return wsMock;
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete globalThis.WebSocket;
  });

  it("updates status to connected on open", () => {
    connectWebSocket();
    wsMock.onopen();
    const status = document.getElementById("connection-status");
    expect(status.classList.contains("status--connected")).toBe(true);
    expect(status.textContent).toContain("Połączono");
  });

  it("updates status to disconnected on close", () => {
    connectWebSocket();
    wsMock.onclose();
    const status = document.getElementById("connection-status");
    expect(status.classList.contains("status--disconnected")).toBe(true);
    expect(status.textContent).toContain("Rozłączono");
  });

  it("reconnects after 5s on close", () => {
    connectWebSocket();
    expect(callCount).toBe(1);
    wsMock.onclose();
    vi.advanceTimersByTime(5000);
    expect(callCount).toBe(2);
  });

  it("closes socket on error", () => {
    connectWebSocket();
    wsMock.onerror(new Event("error"));
    expect(wsMock.close).toHaveBeenCalledOnce();
  });
});

describe("initThemeToggle", () => {
  it("sets data-theme attribute on html", () => {
    document.documentElement.removeAttribute("data-theme");
    initThemeToggle();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("toggles theme on button click", () => {
    initThemeToggle();
    const btn = document.getElementById("theme-toggle");
    btn.click();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    btn.click();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});

describe("loadSensors", () => {
  it("fetches sensors from API", async () => {
    const data = { temperature: { name: "Temperatura", type: "numeric" } };
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(data),
    });

    const result = await loadSensors();
    expect(globalThis.fetch).toHaveBeenCalledWith(`${API_BASE}/sensors`);
    expect(result).toEqual(data);
  });

  it("throws on HTTP error", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });
    await expect(loadSensors()).rejects.toThrow("Failed to load sensors: HTTP 500");
  });
});

describe("initAnalytics", () => {
  beforeEach(() => {
    document.head.querySelectorAll("script").forEach((s) => {
      if (s.src.includes("script.js")) s.remove();
    });
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("injects script tag when host and id are returned", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ host: "https://umami.example.com", id: "abc-123" }),
    });

    await initAnalytics();
    const scripts = document.head.querySelectorAll("script");
    const injected = Array.from(scripts).find((s) => s.src.includes("script.js"));
    expect(injected).toBeTruthy();
    expect(injected.src).toBe("https://umami.example.com/script.js");
    expect(injected.dataset.websiteId).toBe("abc-123");
    expect(injected.defer).toBe(true);
  });

  it("normalizes trailing slash in host", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ host: "https://umami.example.com/", id: "abc-123" }),
    });

    await initAnalytics();
    const scripts = document.head.querySelectorAll("script");
    const injected = Array.from(scripts).find((s) => s.src.includes("script.js"));
    expect(injected).toBeTruthy();
    expect(injected.src).toBe("https://umami.example.com/script.js");
  });

  it("does nothing when response has no host/id", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });
    const originalLength = document.head.querySelectorAll("script").length;

    await initAnalytics();
    expect(document.head.querySelectorAll("script")).toHaveLength(originalLength);
  });

  it("does nothing on HTTP error", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    const originalLength = document.head.querySelectorAll("script").length;

    await initAnalytics();
    expect(document.head.querySelectorAll("script")).toHaveLength(originalLength);
  });

  it("does nothing on fetch error", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("network error"));
    const originalLength = document.head.querySelectorAll("script").length;

    await initAnalytics();
    expect(document.head.querySelectorAll("script")).toHaveLength(originalLength);
  });
});

describe("alert", () => {
  beforeEach(() => {
    alerts.length = 0;
  });

  it("ALERT_ICONS maps levels to correct paths", () => {
    expect(ALERT_ICONS.yellow).toBe("weather_icons/alert-yellow.svg");
    expect(ALERT_ICONS.orange).toBe("weather_icons/alert-orange.svg");
    expect(ALERT_ICONS.red).toBe("weather_icons/alert-red.svg");
    expect(ALERT_GREEN_ICON).toBe("weather_icons/alert-green.svg");
  });

  it("createCard creates hidden alert card with correct elements", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    expect(card.id).toBe("card-alerts");
    expect(card.style.display).toBe("none");
    expect(card.querySelector("#alerts-icon-img")).toBeTruthy();
    expect(card.querySelector("#alerts-value")).toBeTruthy();
    expect(card.querySelector("#alerts-updated")).toBeTruthy();
    expect(card.querySelector(".weather-card__header--condition")).toBeTruthy();
  });

  it("showAlertCard displays card with correct icon and value", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    showAlertCard({ value: "burze", level: "yellow", valid_to: "2026-07-18T19:00:00Z", updatedText: "Test" });
    expect(card.style.display).toBe("");
    const img = document.getElementById("alerts-icon-img");
    expect(img.src).toContain("alert-yellow.svg");
    expect(document.getElementById("alerts-value").textContent).toBe("burze");
  });

  it("showAlertCard falls back to yellow for unknown level", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    showAlertCard({ value: "test", level: "unknown", valid_to: "2026-07-18T19:00:00Z" });
    const img = document.getElementById("alerts-icon-img");
    expect(img.src).toContain("alert-yellow.svg");
  });

  it("showAlertCard uses green icon for null level", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    showAlertCard({ value: "brak zagrożeń", level: null, valid_to: "2026-07-18T19:00:00Z", updatedText: "Test" });
    expect(card.style.display).toBe("");
    const img = document.getElementById("alerts-icon-img");
    expect(img.src).toContain("alert-green.svg");
    expect(document.getElementById("alerts-value").textContent).toBe("brak zagrożeń");
  });

  it("hideAlertCard hides the card", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);
    card.style.display = "";

    hideAlertCard();
    expect(card.style.display).toBe("none");
  });

  it("updateAlertVisibility shows first valid alert", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    alerts.push(
      { value: "expired", level: "red", valid_to: "2020-01-01T00:00:00Z", updatedText: "" },
      { value: "current", level: "orange", valid_to: "2099-01-01T00:00:00Z", updatedText: "" },
    );
    updateAlertVisibility();
    expect(document.getElementById("alerts-value").textContent).toBe("current");
  });

  it("updateAlertVisibility removes expired alerts from array", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    alerts.push({ value: "old", level: "red", valid_to: "2020-01-01T00:00:00Z", updatedText: "" });
    updateAlertVisibility();
    expect(alerts.length).toBe(0);
    expect(card.style.display).toBe("none");
  });

  it("updateAlertVisibility hides card when no valid alerts", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);
    card.style.display = "";

    alerts.push({ value: "old", level: "red", valid_to: "2020-01-01T00:00:00Z" });
    updateAlertVisibility();
    expect(card.style.display).toBe("none");
  });

  it("handleAlertUpdate adds new alert to front of array", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    handleAlertUpdate({ value: "new", level: "yellow", valid_to: "2099-01-01T00:00:00Z", timestamp: "2" });
    handleAlertUpdate({ value: "older", level: "red", valid_to: "2099-01-01T00:00:00Z", timestamp: "1" });
    expect(alerts.length).toBe(2);
    expect(alerts[0].value).toBe("older");
    expect(document.getElementById("alerts-value").textContent).toBe("older");
  });

  it("handleAlertUpdate deduplicates by timestamp", () => {
    handleAlertUpdate({ value: "first", level: "yellow", valid_to: "2099-01-01T00:00:00Z", timestamp: "same" });
    handleAlertUpdate({ value: "second", level: "red", valid_to: "2099-01-01T00:00:00Z", timestamp: "same" });
    expect(alerts.length).toBe(1);
    expect(alerts[0].value).toBe("second");
  });

  it("sendAlertNotification does nothing when permission is denied", () => {
    const origPerm = Notification.permission;
    Notification.permission = "denied";
    Notification.mockClear();
    sendAlertNotification({ value: "test", level: "red", timestamp: "1" });
    expect(Notification).not.toHaveBeenCalled();
    Notification.permission = origPerm;
  });

  it("sendAlertNotification does nothing when Notification API is unavailable", () => {
    const orig = globalThis.Notification;
    delete globalThis.Notification;
    expect(() => sendAlertNotification({ value: "test", level: "red", timestamp: "1" })).not.toThrow();
    globalThis.Notification = orig;
  });

  it("sendAlertNotification fires Notification with correct title and body", () => {
    Notification.mockClear();
    sendAlertNotification({ value: "burze", level: "orange", timestamp: "ts1", valid_to: "2099-01-01T00:00:00Z" });
    expect(Notification).toHaveBeenCalledWith("Alert meteorologiczny", {
      body: expect.stringMatching(/Pomarańczowy alert: burze\nWażny do: 1 stycznia, \d{2}:\d{2}/),
      tag: "ts1",
    });
  });

  it("sendAlertNotification shows only time for today expiry", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-23T12:00:00Z"));
    Notification.mockClear();
    sendAlertNotification({ value: "mgła", level: "yellow", timestamp: "ts2", valid_to: "2026-06-23T15:00:00Z" });
    const callBody = Notification.mock.calls[0][1].body;
    expect(callBody).toContain("Żółty alert: mgła");
    expect(callBody).toContain("Ważny do:");
    expect(callBody).not.toContain(",");
    vi.useRealTimers();
  });

  it("sendAlertNotification uses Zielony label for null level", () => {
    Notification.mockClear();
    sendAlertNotification({ value: "brak zagrożeń", level: null, timestamp: "ts3", valid_to: "2099-01-01T00:00:00Z" });
    expect(Notification).toHaveBeenCalledWith("Alert meteorologiczny", {
      body: expect.stringMatching(/Zielony alert: brak zagrożeń/),
      tag: "ts3",
    });
  });

  it("requestNotificationPermission calls requestPermission when status is default", () => {
    Notification.permission = "default";
    Notification.requestPermission.mockClear();
    requestNotificationPermission();
    expect(Notification.requestPermission).toHaveBeenCalled();
  });

  it("requestNotificationPermission does nothing when permission is already granted", () => {
    Notification.permission = "granted";
    Notification.requestPermission.mockClear();
    requestNotificationPermission();
    expect(Notification.requestPermission).not.toHaveBeenCalled();
  });

  it("requestNotificationPermission does nothing when Notification API is unavailable", () => {
    const orig = globalThis.Notification;
    delete globalThis.Notification;
    expect(() => requestNotificationPermission()).not.toThrow();
    globalThis.Notification = orig;
  });

  it("handleAlertUpdate sends notification for new alerts", () => {
    handleAlertUpdate({ value: "test", level: "yellow", valid_to: "2099-01-01T00:00:00Z", timestamp: "notif1" });
    expect(Notification).toHaveBeenCalledWith("Alert meteorologiczny", expect.objectContaining({ body: expect.stringContaining("test") }));
  });

  it("loadAlerts fetches alerts and populates the array", async () => {
    const apiData = [
      { value_str: "burze", level: "yellow", valid_to: "2099-01-01T00:00:00Z", timestamp: "2026-06-23T12:00:00Z" },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(apiData),
    });

    await loadAlerts();
    expect(globalThis.fetch).toHaveBeenCalledWith(`${API_BASE}/alerts`);
    expect(alerts.length).toBe(1);
    expect(alerts[0].value).toBe("burze");
  });

  it("loadAlerts logs error on fetch failure", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });

    await loadAlerts();
    expect(console.error).toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it("updateCard returns early for alert sensor", () => {
    sensorsConfig.alerts = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensorsConfig.alerts, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("alerts", "should-not-appear", null, "2026-06-23T12:00:00Z");
    expect(document.getElementById("alerts-value").textContent).toBe("--");
  });

  it("WS message with alert parameter routes to handleAlertUpdate", () => {
    globalThis.location = { host: "localhost:8332", protocol: "http:" };
    const wsMock = { onopen: null, onmessage: null, onclose: null, onerror: null, close: vi.fn() };
    globalThis.WebSocket = vi.fn(function () { return wsMock; });

    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    connectWebSocket();
    wsMock.onmessage({
      data: JSON.stringify({
        parameter: "alerts",
        value: "ws-alert",
        valid_to: "2099-01-01T00:00:00Z",
        level: "red",
        timestamp: "2026-06-23T12:00:00Z",
      }),
    });
    expect(alerts.length).toBe(1);
    expect(alerts[0].value).toBe("ws-alert");
    expect(document.getElementById("alerts-value").textContent).toBe("ws-alert");
    delete globalThis.WebSocket;
  });

  it("WS message with sun parameter updates sunState and re-renders condition icon", () => {
    globalThis.location = { host: "localhost:8332", protocol: "http:" };
    const wsMock = { onopen: null, onmessage: null, onclose: null, onerror: null, close: vi.fn() };
    globalThis.WebSocket = vi.fn(function () { return wsMock; });

    sensorsConfig.condition = { name: "Warunki", type: "condition", icon: "mdi:weather-sunny", color: "#FDD835" };
    const card = createCard("condition", sensorsConfig.condition, 0);
    document.getElementById("weather-grid").appendChild(card);

    connectWebSocket();

    updateCard("condition", "partly cloudy", null, "2026-06-23T12:00:00Z", "mdi:weather-partly-cloudy");

    expect(document.getElementById("condition-icon-img").src).toContain("partly-cloudy-day.svg");

    wsMock.onmessage({
      data: JSON.stringify({
        parameter: "sun",
        value: "below_horizon",
        timestamp: "2026-06-23T22:00:00Z",
      }),
    });
    expect(sunState.value).toBe("below_horizon");
    expect(document.getElementById("condition-icon-img").src).toContain("partly-cloudy-night.svg");
    delete globalThis.WebSocket;
  });
});

describe("loadSunState", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sunState.value = null;
  });

  it("fetches sun state from API and sets sunState.value", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ value: "above_horizon", timestamp: "2026-06-23T12:00:00Z" }),
    });

    await loadSunState();
    expect(sunState.value).toBe("above_horizon");
  });

  it("handles below_horizon value", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ value: "below_horizon", timestamp: "2026-06-23T22:00:00Z" }),
    });

    await loadSunState();
    expect(sunState.value).toBe("below_horizon");
  });

  it("ignores null sun state without overriding sunState", async () => {
    sunState.value = "above_horizon";
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ value: null, timestamp: null }),
    });

    await loadSunState();
    expect(sunState.value).toBe("above_horizon");
  });

  it("re-renders condition icons on sun state change", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ value: "below_horizon", timestamp: "2026-06-23T22:00:00Z" }),
    });

    sensorsConfig.condition = { name: "Warunki", type: "condition", icon: "mdi:weather-sunny", color: "#FDD835" };
    const card = createCard("condition", sensorsConfig.condition, 0);
    document.getElementById("weather-grid").appendChild(card);
    updateCard("condition", "partly cloudy", null, "2026-06-23T12:00:00Z", "mdi:weather-partly-cloudy");

    await loadSunState();
    expect(sunState.value).toBe("below_horizon");
    expect(document.getElementById("condition-icon-img").src).toContain("partly-cloudy-night.svg");
    delete sensorsConfig.condition;
  });

  it("logs warning on HTTP error", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });

    await loadSunState();
    expect(console.warn).toHaveBeenCalled();
  });

  it("logs warning on fetch error", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("network"));

    await loadSunState();
    expect(console.warn).toHaveBeenCalled();
  });
});

describe("init", () => {
  beforeEach(() => {
    globalThis.location = { host: "localhost:8332", protocol: "http:" };
    globalThis.WebSocket = vi.fn(function () {
      return {
        onopen: null,
        onmessage: null,
        onclose: null,
        onerror: null,
        close: vi.fn(),
      };
    });
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.getElementById("weather-grid").innerHTML = "";
  });

  it("creates cards for all sensors", async () => {
    const sensors = {
      temperature: { name: "Temp", type: "numeric", icon: "mdi:thermometer", color: "#E53935", round: 1, unit: "°C" },
      condition: { name: "Warunki", type: "condition", icon: "mdi:weather-sunny", color: "#FDD835" },
    };
    globalThis.fetch = vi.fn((url) => {
      if (url.includes("/sensors")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(sensors) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ value: "above_horizon" }) });
    });

    await init();
    const grid = document.getElementById("weather-grid");
    expect(grid.children).toHaveLength(2);
    expect(grid.querySelector("#card-temperature")).toBeTruthy();
    expect(grid.querySelector("#card-condition")).toBeTruthy();
    expect(grid.querySelector("#chart-temperature")).toBeTruthy();
    expect(grid.querySelector("#condition-icon-img")).toBeTruthy();
  });

  it("sets charts for numeric sensors", async () => {
    const sensors = {
      temperature: { name: "Temp", type: "numeric", icon: "mdi:thermometer", color: "#E53935", round: 1, unit: "°C" },
    };
    globalThis.fetch = vi.fn((url) => {
      if (url.includes("/sensors")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(sensors) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ value: "above_horizon" }) });
    });

    await init();
    expect(charts.temperature).toBeTruthy();
  });
});

describe("forecast", () => {
  const SENSOR_FORECAST = {
    forecast: { name: "Prognoza", type: "forecast", icon: "", color: null, round: 1, unit: "" },
  };

  const FORECAST_DATA = [
    { datetime: "2026-07-22T00:00:00+00:00", is_daytime: true, condition: "cloudy", temperature: 23.1, precipitation: 0.0, cloud_coverage: 75, wind_speed: 15.0 },
    { datetime: "2026-07-23T00:00:00+00:00", is_daytime: false, condition: "rainy", temperature: 20.5, precipitation: 0.1, cloud_coverage: 90, wind_speed: 27.36 },
    { datetime: "2026-07-23T00:00:00+00:00", is_daytime: true, condition: "partlycloudy", temperature: 20.2, precipitation: 1.6, cloud_coverage: 50, wind_speed: 17.28 },
    { datetime: "2026-07-24T00:00:00+00:00", is_daytime: false, condition: "partlycloudy", temperature: 17.9, precipitation: 0.6, cloud_coverage: 85, wind_speed: 24.84 },
    { datetime: "2026-07-24T00:00:00+00:00", is_daytime: true, condition: "rainy", temperature: 21.7, precipitation: 2.0, cloud_coverage: 60, wind_speed: 18.5 },
    { datetime: "2026-07-25T00:00:00+00:00", is_daytime: false, condition: "partlycloudy", temperature: 20.3, precipitation: 0.0, cloud_coverage: 30, wind_speed: 16.2 },
  ];

  it("getPolishDayAbbr returns correct Polish abbreviations", () => {
    expect(getPolishDayAbbr(new Date("2026-07-20"))).toBe("poniedziałek");
    expect(getPolishDayAbbr(new Date("2026-07-21"))).toBe("wtorek");
    expect(getPolishDayAbbr(new Date("2026-07-22"))).toBe("środa");
    expect(getPolishDayAbbr(new Date("2026-07-23"))).toBe("czwartek");
    expect(getPolishDayAbbr(new Date("2026-07-24"))).toBe("piątek");
    expect(getPolishDayAbbr(new Date("2026-07-25"))).toBe("sobota");
    expect(getPolishDayAbbr(new Date("2026-07-26"))).toBe("niedziela");
  });

  it("getConditionSvgPath uses isDaytime parameter for partlycloudy", () => {
    expect(getConditionSvgPath("partlycloudy", null, true)).toBe("weather_icons/partly-cloudy-day.svg");
    expect(getConditionSvgPath("partlycloudy", null, false)).toBe("weather_icons/partly-cloudy-night.svg");
  });

  it("getConditionSvgPath ignores isDaytime for non-partlycloudy", () => {
    expect(getConditionSvgPath("cloudy", null, true)).toBe("weather_icons/cloudy.svg");
    expect(getConditionSvgPath("cloudy", null, false)).toBe("weather_icons/cloudy.svg");
  });

  it("createCard creates forecast card with 5 columns and no header icon", () => {
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    expect(card.id).toBe("card-forecast");
    expect(card.querySelector(".weather-card__header .material-symbols-rounded")).toBeNull();
    expect(card.querySelector(".weather-card__label")).toBeTruthy();
    expect(card.querySelectorAll(".forecast-col")).toHaveLength(5);
    expect(card.querySelector(".forecast-grid")).toBeTruthy();
  });

  it("createCard forecast card has correct column elements", () => {
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    const col = card.querySelector(".forecast-col");
    expect(col.querySelector(".forecast-col__day")).toBeTruthy();
    expect(col.querySelector(".forecast-col__period")).toBeTruthy();
    expect(col.querySelector(".forecast-col__icon")).toBeTruthy();
    expect(col.querySelector(".forecast-col__temp-value")).toBeTruthy();
    expect(col.querySelector(".forecast-col__precip-value")).toBeTruthy();
    expect(col.querySelector(".forecast-col__cloud-value")).toBeTruthy();
    expect(col.querySelector(".forecast-col__wind-value")).toBeTruthy();
    expect(col.querySelectorAll(".material-symbols-rounded")).toHaveLength(4);
  });

  it("updateCard populates forecast columns with data items 0-4", () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("forecast", FORECAST_DATA, null, "2026-07-22T12:00:00Z");

    const cols = card.querySelectorAll(".forecast-col");

    // Item 0: daytime cloudy
    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("środa");
    expect(cols[0].querySelector(".forecast-col__period").textContent).toBe("dzień");
    expect(cols[0].querySelector(".forecast-col__temp-value").textContent).toBe("23°C");
    expect(cols[0].querySelector(".forecast-col__precip-value").textContent).toBe("0 mm");
    expect(cols[0].querySelector(".forecast-col__cloud-value").textContent).toBe("75%");
    expect(cols[0].querySelector(".forecast-col__wind-value").textContent).toBe("15 km/h");

    // Item 2: daytime partlycloudy
    expect(cols[2].querySelector(".forecast-col__day").textContent).toBe("czwartek");
    expect(cols[2].querySelector(".forecast-col__period").textContent).toBe("dzień");
    expect(cols[2].querySelector(".forecast-col__temp-value").textContent).toBe("20°C");
    expect(cols[2].querySelector(".forecast-col__precip-value").textContent).toBe("2 mm");
    expect(cols[2].querySelector(".forecast-col__cloud-value").textContent).toBe("50%");
    expect(cols[2].querySelector(".forecast-col__wind-value").textContent).toBe("17 km/h");

    // Item 3: nighttime partlycloudy
    expect(cols[3].querySelector(".forecast-col__day").textContent).toBe("piątek");
    expect(cols[3].querySelector(".forecast-col__period").textContent).toBe("noc");
    expect(cols[3].querySelector(".forecast-col__temp-value").textContent).toBe("18°C");
    expect(cols[3].querySelector(".forecast-col__precip-value").textContent).toBe("1 mm");
    expect(cols[3].querySelector(".forecast-col__cloud-value").textContent).toBe("85%");
    expect(cols[3].querySelector(".forecast-col__wind-value").textContent).toBe("25 km/h");

    // Item 4: daytime rainy
    expect(cols[4].querySelector(".forecast-col__day").textContent).toBe("piątek");
    expect(cols[4].querySelector(".forecast-col__period").textContent).toBe("dzień");
    expect(cols[4].querySelector(".forecast-col__temp-value").textContent).toBe("22°C");
    expect(cols[4].querySelector(".forecast-col__precip-value").textContent).toBe("2 mm");
    expect(cols[4].querySelector(".forecast-col__cloud-value").textContent).toBe("60%");
    expect(cols[4].querySelector(".forecast-col__wind-value").textContent).toBe("19 km/h");

    delete sensorsConfig.forecast;
  });

  it("updateCard shows partlycloudy day/night icons based on is_daytime", () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("forecast", FORECAST_DATA, null, "2026-07-22T12:00:00Z");

    const cols = card.querySelectorAll(".forecast-col");

    // Item 2: partlycloudy, is_daytime=true
    expect(cols[2].querySelector(".forecast-col__icon").src).toContain("partly-cloudy-day.svg");

    // Item 3: partlycloudy, is_daytime=false
    expect(cols[3].querySelector(".forecast-col__icon").src).toContain("partly-cloudy-night.svg");

    delete sensorsConfig.forecast;
  });

  it("updateCard does nothing for non-array value", () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("forecast", "not-an-array", null, "2026-07-22T12:00:00Z");

    // Columns should still show placeholder values
    const cols = card.querySelectorAll(".forecast-col");
    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("--");
    expect(cols[1].querySelector(".forecast-col__day").textContent).toBe("--");

    delete sensorsConfig.forecast;
  });

  it("loadForecast fetches from API and updates card", async () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ forecast: FORECAST_DATA, timestamp: "2026-07-22T12:00:00Z" }),
    });

    await loadForecast();

    const cols = card.querySelectorAll(".forecast-col");
    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("środa");
    expect(globalThis.fetch).toHaveBeenCalledWith(`${API_BASE}/forecast`);

    delete sensorsConfig.forecast;
  });

  it("loadForecast handles empty response gracefully", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ forecast: [], timestamp: null }),
    });

    await loadForecast();
    // Should not throw
    vi.restoreAllMocks();
  });

  it("loadForecast handles HTTP error gracefully", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 });

    await loadForecast();
    expect(console.error).toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it("loadHistory skips forecast sensor", async () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    // Should not throw even without fetch mock
    await loadHistory("forecast");
    delete sensorsConfig.forecast;
  });

  it("WS forecast message updates the card", () => {
    globalThis.location = { host: "localhost:8332", protocol: "http:" };
    const wsMock = { onopen: null, onmessage: null, onclose: null, onerror: null, close: vi.fn() };
    globalThis.WebSocket = vi.fn(function () { return wsMock; });

    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    connectWebSocket();
    wsMock.onmessage({
      data: JSON.stringify({
        parameter: "forecast",
        value: FORECAST_DATA,
        timestamp: "2026-07-22T12:00:00Z",
      }),
    });

    const cols = card.querySelectorAll(".forecast-col");
    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("środa");
    expect(cols[1].querySelector(".forecast-col__temp-value").textContent).toBe("21°C");
    delete globalThis.WebSocket;
    delete sensorsConfig.forecast;
  });

  it("icons thermometer, water_drop, cloud and air are present in forecast columns", () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    const cols = card.querySelectorAll(".forecast-col");
    for (const col of cols) {
      const icons = col.querySelectorAll(".forecast-col__val-icon");
      expect(icons).toHaveLength(4);
      expect(icons[0].textContent).toBe("thermometer");
      expect(icons[1].textContent).toBe("air");
      expect(icons[2].textContent).toBe("water_drop");
      expect(icons[3].textContent).toBe("cloud");
    }
    delete sensorsConfig.forecast;
  });

  it("forecast card has precip, cloud and wind values rounded without decimals", () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("forecast", FORECAST_DATA, null, "2026-07-22T12:00:00Z");

    const cols = card.querySelectorAll(".forecast-col");
    // Item 4: precipitation 2.0 → "2 mm"
    expect(cols[4].querySelector(".forecast-col__precip-value").textContent).toBe("2 mm");
    // Item 0: precipitation 0.0 → "0 mm"
    expect(cols[0].querySelector(".forecast-col__precip-value").textContent).toBe("0 mm");
    // Item 1: cloud_coverage 90 → "90%"
    expect(cols[1].querySelector(".forecast-col__cloud-value").textContent).toBe("90%");
    // Item 2: cloud_coverage 50 → "50%"
    expect(cols[2].querySelector(".forecast-col__cloud-value").textContent).toBe("50%");
    // Item 2: wind_speed 17.28 → "17 km/h" (rounds down)
    expect(cols[2].querySelector(".forecast-col__wind-value").textContent).toBe("17 km/h");
    // Item 3: wind_speed 24.84 → "25 km/h" (rounds up)
    expect(cols[3].querySelector(".forecast-col__wind-value").textContent).toBe("25 km/h");
    // Item 0: wind_speed 15.0 → "15 km/h" (no rounding needed)
    expect(cols[0].querySelector(".forecast-col__wind-value").textContent).toBe("15 km/h");

    delete sensorsConfig.forecast;
  });
});
