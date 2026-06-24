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
  init,
  charts,
  sensorsConfig,
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
