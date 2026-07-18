process.env.TZ = "UTC";

import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  getConditionSvgPath,
  formatTimestamp,
  formatUpdated,
  resolveIcon,
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
  ALERT_ICONS,
  showAlertCard,
  hideAlertCard,
  updateAlertVisibility,
  handleAlertUpdate,
  sendAlertNotification,
  requestNotificationPermission,
  loadAlerts,
  API_BASE,
  HISTORY_HOURS,
  MAX_CHART_POINTS,
} from "../../frontend/app.js";

beforeEach(() => {
  Object.keys(charts).forEach((k) => delete charts[k]);
  Object.keys(sensorsConfig).forEach((k) => delete sensorsConfig[k]);
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
      body: expect.stringMatching(/Pomarańczowy: burze\nWażny do: 1 stycznia, \d{2}:\d{2}/),
      tag: "ts1",
    });
  });

  it("sendAlertNotification shows only time for today expiry", () => {
    Notification.mockClear();
    const future = new Date();
    future.setHours(future.getHours() + 3);
    const iso = future.toISOString();
    sendAlertNotification({ value: "mgła", level: "yellow", timestamp: "ts2", valid_to: iso });
    const callBody = Notification.mock.calls[0][1].body;
    expect(callBody).toContain("Żółty: mgła");
    expect(callBody).toContain("Ważny do:");
    expect(callBody).not.toContain(","); // no comma = date part omitted
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
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sensors),
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
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sensors),
    });

    await init();
    expect(charts.temperature).toBeTruthy();
  });
});
