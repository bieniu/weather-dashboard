import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  API_BASE,
  HISTORY_HOURS,
  getJson,
  loadSensors,
  sensorsConfig,
} from "../../frontend/api.js";
import {
  ALERT_GREEN_ICON,
  ALERT_ICONS,
  alerts,
  handleAlertUpdate,
  hideAlertCard,
  loadAlerts,
  requestNotificationPermission,
  scheduleAlertCheck,
  sendAlertNotification,
  showAlertCard,
  updateAlertVisibility,
} from "../../frontend/alerts.js";
import { init, initAnalytics, registerServiceWorker, resetState } from "../../frontend/app.js";
import {
  createCard,
  isChartSensor,
  loadCurrent,
  loadForecast,
  loadSunState,
  updateCard,
} from "../../frontend/cards.js";
import {
  appendChartPoint,
  buildChartOptions,
  chartPoints,
  charts,
  createChart,
  loadHistory,
  trimChartData,
  updateChartTheme,
  withAlpha,
} from "../../frontend/charts.js";
import { esc, formatTimestamp, formatUpdated, getPolishDayAbbr } from "../../frontend/format.js";
import { getConditionSvgPath, resolveIcon, sunState } from "../../frontend/icons.js";
import { THEME_STORAGE_KEY, initThemeToggle } from "../../frontend/theme.js";
import { connectWebSocket, reconnectNow, wsState } from "../../frontend/ws.js";

beforeEach(() => {
  resetState();
});

const SENSOR_NUMERIC = {
  temperature: {
    name: "Temperatura",
    type: "numeric",
    icon: "mdi:thermometer",
    color: "#E53935",
    round: 1,
    unit: "°C",
  },
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

  it.each([
    [null, "2025-06-24T12:00:00", "partly-cloudy-day"],
    [null, "2025-06-24T22:00:00", "partly-cloudy-night"],
    [null, "2025-06-24T06:00:00", "partly-cloudy-day"],
    [null, "2025-06-24T20:00:00", "partly-cloudy-night"],
    ["above_horizon", "2025-06-24T22:00:00", "partly-cloudy-day"],
    ["below_horizon", "2025-06-24T12:00:00", "partly-cloudy-night"],
  ])("getConditionSvgPath picks partly cloudy by sun state %s at %s", (sun, now, icon) => {
    sunState.value = sun;
    vi.useFakeTimers();
    vi.setSystemTime(new Date(now));
    expect(getConditionSvgPath("mdi:weather-partly-cloudy")).toBe(`weather_icons/${icon}.svg`);
    vi.useRealTimers();
  });

  it("getConditionSvgPath uses the reading's timestamp when there is no sun state", () => {
    expect(getConditionSvgPath("mdi:weather-partly-cloudy", "2025-06-24T23:00:00Z")).toBe(
      "weather_icons/partly-cloudy-night.svg",
    );
  });

  it("getConditionSvgPath returns null for unknown icon", () => {
    expect(getConditionSvgPath("mdi:unknown-icon")).toBeNull();
  });

  it("getConditionSvgPath resolves a bare mdi alias (clear-night) to its SVG", () => {
    expect(getConditionSvgPath("mdi:clear-night")).toBe("weather_icons/clear-night.svg");
  });

  it("esc escapes every HTML-special character", () => {
    expect(esc(`<b a="1" b='2'>&</b>`)).toBe(
      "&lt;b a=&quot;1&quot; b=&#39;2&#39;&gt;&amp;&lt;/b&gt;",
    );
    expect(esc(24)).toBe("24");
  });

  it("getJson prefixes API_BASE and throws on HTTP errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(1) }));
    await expect(getJson("/x")).resolves.toBe(1);
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/x`);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(getJson("/x")).rejects.toThrow("HTTP 404");
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

  it.each([
    ["numeric", "numeric"],
    ["condition", "condition"],
    ["text", "text"],
    ["alerts", "alerts"],
    ["forecast", "forecast"],
    ["pm", "numeric"],
    [undefined, "numeric"],
  ])("sensor type %s gets the weather-card--%s class", (type, cardClass) => {
    const card = createCard("x", { name: "X", type, icon: "mdi:air" }, 0);
    expect(card.classList.contains(`weather-card--${cardClass}`)).toBe(true);
    expect(isChartSensor({ type })).toBe(cardClass === "numeric");
  });

  it("never interpolates config strings as HTML", () => {
    const sensor = {
      name: '<img src=x onerror="alert(1)">',
      type: "numeric",
      icon: "mdi:<b>air</b>",
      unit: "°C",
    };
    const card = createCard("temperature", sensor, 0);
    expect(card.querySelector("img")).toBeNull();
    expect(card.querySelector("b")).toBeNull();
    expect(card.querySelector(".weather-card__label").textContent).toBe(sensor.name);
    expect(card.querySelector(".weather-card__icon").textContent).toBe("<b>air</b>");
    expect(card.querySelector("canvas").getAttribute("aria-label")).toBe(
      `${sensor.name} — wykres z ostatnich ${HISTORY_HOURS} godzin`,
    );
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
  });

  it("updates text sensor value", () => {
    sensorsConfig.text_sensor = SENSOR_TEXT.text_sensor;
    const card = createCard("text_sensor", SENSOR_TEXT.text_sensor, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("text_sensor", "Silny wiatr", null, "2025-06-24T14:30:00Z");
    expect(document.getElementById("text_sensor-value").textContent).toBe("Silny wiatr");
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
  });

  it("does nothing when sensor not in config", () => {
    const before = document.getElementById("weather-grid").innerHTML;
    expect(() => updateCard("nonexistent", 42, null, "2025-06-24T14:30:00Z")).not.toThrow();
    expect(document.getElementById("weather-grid").innerHTML).toBe(before);
  });

  it("updates updated timestamp on numeric sensor", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    document.getElementById("weather-grid").appendChild(card);

    updateCard("temperature", 22.0, "°C", "2025-06-24T15:00:00Z");
    expect(document.getElementById("temperature-updated").textContent).toMatch(
      /^Zaktualizowano: 15:00:00$/,
    );
  });
});

describe("chart", () => {
  beforeEach(() => {});

  it("createChart creates a Chart.js instance", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    document.getElementById("weather-grid").appendChild(card);

    const chart = createChart("chart-temperature", "#E53935", 1, "°C");
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

  it("appendChartPoint stores epoch milliseconds and drops points older than the history window", () => {
    const t0 = Date.parse("2025-06-24T00:00:00Z");
    const hour = 3600 * 1000;
    const ds = {
      data: [
        { x: t0, y: 1 },
        { x: t0 + 2 * hour, y: 2 },
      ],
    };
    charts.temperature = { data: { datasets: [ds] }, update: vi.fn() };

    appendChartPoint("temperature", 3, new Date(t0 + (HISTORY_HOURS + 1) * hour).toISOString());

    expect(ds.data.map((p) => p.y)).toEqual([2, 3]);
    expect(typeof ds.data[1].x).toBe("number");
    expect(charts.temperature.update).toHaveBeenCalledWith("none");
  });

  it("keeps appending to the source array after the decimation plugin swaps dataset.data", () => {
    // Emulates Chart.js: once decimated, `data` reads the decimated view and writes go to `_data`.
    const source = [{ x: 1, y: 1 }];
    const ds = {
      _data: source,
      _decimated: [{ x: 1, y: 1 }],
      get data() {
        return this._decimated;
      },
      set data(value) {
        this._data = value;
      },
    };
    charts.temperature = { data: { datasets: [ds] }, update: vi.fn() };
    chartPoints.temperature = source;

    appendChartPoint("temperature", 2, new Date(2).toISOString());

    expect(source.map((p) => p.y)).toEqual([1, 2]);
    expect(ds._data).toBe(source);
    expect(ds._decimated).toHaveLength(1); // the view is left to the plugin
  });

  it("trimChartData honours the sensor's own history_hours", () => {
    sensorsConfig.water_level = { name: "Woda", type: "numeric", history_hours: 1 };
    const t0 = Date.parse("2025-06-24T00:00:00Z");
    const data = [
      { x: t0, y: 1 },
      { x: t0 + 30 * 60 * 1000, y: 2 },
      { x: t0 + 61 * 60 * 1000, y: 3 },
    ];

    trimChartData("water_level", data);

    expect(data.map((p) => p.y)).toEqual([2, 3]);
  });

  it("createChart disables parsing and enables LTTB decimation", () => {
    const card = createCard("temperature", SENSOR_NUMERIC.temperature, 0);
    document.getElementById("weather-grid").appendChild(card);

    createChart("chart-temperature", "#E53935", 1, "°C");

    const config = Chart.mock.calls.at(-1)[1];
    expect(config.options.parsing).toBe(false);
    expect(config.options.normalized).toBe(true);
    expect(config.options.plugins.decimation).toMatchObject({
      enabled: true,
      algorithm: "lttb",
      threshold: 400,
    });
  });

  it("appendChartPoint does nothing for unknown parameter", () => {
    charts.temperature = { data: { datasets: [{ data: [] }] }, update: vi.fn() };

    appendChartPoint("nonexistent", 42, "2025-06-24T15:00:00Z");

    expect(chartPoints).toEqual({});
    expect(charts.temperature.update).not.toHaveBeenCalled();
  });

  it("createChart themes both axes from the CSS tokens and fills with the sensor colour", () => {
    document
      .getElementById("weather-grid")
      .appendChild(createCard("temperature", SENSOR_NUMERIC.temperature, 0));

    createChart("chart-temperature", "#E53935", 1, "°C");

    const config = Chart.mock.calls.at(-1)[1];
    const { x, y } = config.options.scales;
    expect([x.grid.color, y.grid.color, x.ticks.color, y.ticks.color]).toEqual([
      "#ccc",
      "#ccc",
      "#666",
      "#666",
    ]);
    expect(config.data.datasets[0]).toMatchObject({
      borderColor: "#E53935",
      backgroundColor: "#E5393522",
    });
  });

  it.each([
    ["#E53935", "#E5393522"],
    ["#abc", "#aabbcc22"],
    ["rgb(1, 2, 3)", "transparent"],
    ["#12345", "transparent"],
    [undefined, "transparent"],
  ])("withAlpha(%s) is %s", (color, expected) => {
    expect(withAlpha(color)).toBe(expected);
  });

  it("buildChartOptions formats tooltips and ticks with the sensor's decimals and unit", () => {
    const options = buildChartOptions(2, "hPa");
    const { label, title } = options.plugins.tooltip.callbacks;

    expect(label({ parsed: { y: 1013.256 } })).toBe(" 1013.26 hPa");
    expect(title([{ raw: { x: Date.parse("2025-06-24T14:30:00Z") } }])).toBe("14:30");
    expect(options.scales.y.ticks.callback("7")).toBe("7.00");
    const scale = { width: 0 };
    options.scales.y.afterFit(scale);
    expect(scale.width).toBe(52);
  });

  it("updateChartTheme calls update on all charts", () => {
    const c1 = {
      options: { scales: { x: { grid: {}, ticks: {} }, y: { grid: {}, ticks: {} } } },
      update: vi.fn(),
    };
    const c2 = {
      options: { scales: { x: { grid: {}, ticks: {} }, y: { grid: {}, ticks: {} } } },
      update: vi.fn(),
    };
    charts.a = c1;
    charts.b = c2;

    updateChartTheme();
    expect(c1.update).toHaveBeenCalledExactlyOnceWith("none");
    expect(c2.update).toHaveBeenCalledExactlyOnceWith("none");
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
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(history),
      }),
    );

    await loadHistory("temperature");
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/history/temperature?hours=${HISTORY_HOURS}`);
    expect(charts.temperature.data.datasets[0].data).toHaveLength(2);
  });

  it("keeps live points newer than the history that arrived while loading", async () => {
    const history = [
      { timestamp: "2025-06-24T13:00:00Z", value: 22.0, unit: "°C" },
      { timestamp: "2025-06-24T14:00:00Z", value: 23.0, unit: "°C" },
    ];
    charts.temperature.data.datasets[0].data = [
      { x: Date.parse("2025-06-24T13:30:00Z"), y: 99 }, // covered by history: dropped
      { x: Date.parse("2025-06-24T14:05:00Z"), y: 24.0 }, // newer than history: kept
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(history) }),
    );

    await loadHistory("temperature");

    expect(charts.temperature.data.datasets[0].data.map((p) => p.y)).toEqual([22.0, 23.0, 24.0]);
  });

  it("merges live points from the source array, not the decimated view", async () => {
    const source = [{ x: Date.parse("2025-06-24T14:05:00Z"), y: 24.0 }];
    const ds = {
      _data: source,
      _decimated: [],
      get data() {
        return this._decimated;
      },
      set data(value) {
        this._data = value;
      },
    };
    charts.temperature = { data: { datasets: [ds] }, update: vi.fn() };
    chartPoints.temperature = source;
    const history = [{ timestamp: "2025-06-24T14:00:00Z", value: 23.0, unit: "°C" }];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(history) }),
    );

    await loadHistory("temperature");

    expect(ds._data.map((p) => p.y)).toEqual([23.0, 24.0]);
    expect(chartPoints.temperature).toBe(ds._data);
  });

  it("does nothing for sensors without a chart", async () => {
    vi.stubGlobal("fetch", vi.fn());

    await loadHistory("pressure");

    expect(fetch).not.toHaveBeenCalled();
  });

  it("logs error on HTTP failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await loadHistory("temperature");
    expect(console.error).toHaveBeenCalled();
  });

  it("handles empty history gracefully", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      }),
    );

    await loadHistory("temperature");
    expect(charts.temperature.data.datasets[0].data).toHaveLength(0);
  });

  it("uses per-sensor history_hours when configured in sensor config", async () => {
    sensorsConfig.water_level = {
      name: "Woda",
      type: "numeric",
      icon: "mdi:waves",
      color: "#2196F3",
      round: 0,
      unit: "cm",
      history_hours: 48,
    };
    charts.water_level = {
      data: { datasets: [{ data: [] }] },
      update: vi.fn(),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      }),
    );

    await loadHistory("water_level");
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/history/water_level?hours=48`);
  });
});

describe("connectWebSocket", () => {
  let sockets;
  const latest = () => sockets[sockets.length - 1];

  beforeEach(() => {
    sockets = [];
    vi.stubGlobal(
      "WebSocket",
      vi.fn(function () {
        const socket = {
          readyState: 0,
          onopen: null,
          onmessage: null,
          onclose: null,
          onerror: null,
          close: vi.fn(),
        };
        sockets.push(socket);
        return socket;
      }),
    );
    // Every reconnect backfills over REST.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }),
    );
    vi.useFakeTimers();
  });

  afterEach(() => {
    resetState(); // clears the reconnect timer while it is still a fake one
    vi.useRealTimers();
  });

  it.each([
    ["http:", "ws://example.org:8332/api/weather/ws"],
    ["https:", "wss://example.org:8332/api/weather/ws"],
  ])("connects over the page's scheme (%s)", (protocol, url) => {
    vi.stubGlobal("location", { protocol, host: "example.org:8332" });
    connectWebSocket();
    expect(WebSocket).toHaveBeenCalledWith(url);
  });

  it("updates status to connected on open", () => {
    connectWebSocket();
    latest().onopen();
    const status = document.getElementById("connection-status");
    expect(status.classList.contains("status--connected")).toBe(true);
    expect(status.textContent).toContain("Połączono");
  });

  it("updates status to disconnected on close", () => {
    connectWebSocket();
    latest().onclose();
    const status = document.getElementById("connection-status");
    expect(status.classList.contains("status--disconnected")).toBe(true);
    expect(status.textContent).toContain("Rozłączono");
  });

  it("reconnects with exponential backoff and jitter", () => {
    connectWebSocket();
    expect(sockets).toHaveLength(1);

    latest().onclose(); // attempt 0: 5 s ± 20 %
    vi.advanceTimersByTime(3999);
    expect(sockets).toHaveLength(1);
    vi.advanceTimersByTime(2001);
    expect(sockets).toHaveLength(2);

    latest().onclose(); // attempt 1: 10 s ± 20 %
    vi.advanceTimersByTime(7999);
    expect(sockets).toHaveLength(2);
    vi.advanceTimersByTime(4001);
    expect(sockets).toHaveLength(3);
  });

  it("resets the backoff after a successful connection", () => {
    connectWebSocket();
    latest().onclose();
    vi.advanceTimersByTime(6000);
    latest().onopen();

    latest().onclose(); // back to attempt 0
    vi.advanceTimersByTime(6000);
    expect(sockets).toHaveLength(3);
  });

  it("backfills cards, charts, alerts and forecast after a reconnect, not on the first connection", async () => {
    charts.temperature = { data: { datasets: [{ data: [] }] }, update: vi.fn() };
    sensorsConfig.temperature = SENSOR_NUMERIC.temperature;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve([]) }),
    );

    connectWebSocket();
    latest().onopen();
    expect(fetch).not.toHaveBeenCalled();

    latest().onclose();
    vi.advanceTimersByTime(6000);
    latest().onopen();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(4));

    const urls = fetch.mock.calls.map((c) => c[0]);
    expect(urls).toEqual(
      expect.arrayContaining([
        `${API_BASE}/current`,
        `${API_BASE}/history/temperature?hours=${HISTORY_HOURS}`,
        `${API_BASE}/alerts`,
        `${API_BASE}/forecast`,
      ]),
    );
  });

  it("backfills on the first successful open when the initial attempt failed (server was down)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }),
    );

    connectWebSocket();
    latest().onclose(); // never opened
    vi.advanceTimersByTime(6000);
    latest().onopen();

    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(fetch.mock.calls.map((c) => c[0])).toContain(`${API_BASE}/current`);
  });

  it("ignores close events from a socket that was already replaced", () => {
    connectWebSocket();
    const stale = latest();
    stale.readyState = 3;
    reconnectNow(); // opens a new socket immediately
    expect(sockets).toHaveLength(2);

    stale.onclose();
    vi.advanceTimersByTime(60000);
    expect(sockets).toHaveLength(2); // no extra reconnect scheduled by the stale socket
  });

  it("reconnectNow skips the pending backoff but does nothing while connected", () => {
    connectWebSocket();
    latest().onclose(); // schedules a reconnect in ~5 s
    latest().readyState = 3;
    reconnectNow();
    expect(sockets).toHaveLength(2);
    expect(wsState.reconnectTimer).toBeNull();

    latest().readyState = 1; // open
    reconnectNow();
    expect(sockets).toHaveLength(2);
  });

  it("closes socket on error", () => {
    connectWebSocket();
    latest().onerror(new Event("error"));
    expect(latest().close).toHaveBeenCalledOnce();
  });

  it("logs warning on parse error", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    connectWebSocket();
    latest().onmessage({ data: "not-json" });
    expect(console.warn).toHaveBeenCalledWith("[WS] Message parse error:", expect.any(Error));
    vi.restoreAllMocks();
  });
});

describe("initThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("uses the stored preference over the OS preference", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    initThemeToggle();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("persists an explicit choice", () => {
    initThemeToggle();
    document.getElementById("theme-toggle").click();
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("follows OS theme changes only while there is no stored choice", () => {
    const listeners = {};
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        addEventListener: (type, fn) => {
          listeners[type] = fn;
        },
      })),
    );
    initThemeToggle();

    listeners.change({ matches: true });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    listeners.change({ matches: false });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("sets data-theme attribute on html", () => {
    document.documentElement.removeAttribute("data-theme");
    initThemeToggle();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("falls back to the OS preference when storage is blocked", () => {
    const blocked = vi.fn(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked });
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true })),
    );

    initThemeToggle();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    document.getElementById("theme-toggle").click();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(blocked).toHaveBeenCalledTimes(2); // one read, one write, both swallowed
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
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(data),
      }),
    );

    const result = await loadSensors();
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/sensors`);
    expect(result).toEqual(data);
  });

  it("throws on HTTP error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(loadSensors()).rejects.toThrow("HTTP 500");
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
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ host: "https://umami.example.com", id: "abc-123" }),
      }),
    );

    await initAnalytics();
    const scripts = document.head.querySelectorAll("script");
    const injected = Array.from(scripts).find((s) => s.src.includes("script.js"));
    expect(injected).toBeTruthy();
    expect(injected.src).toBe("https://umami.example.com/script.js");
    expect(injected.dataset.websiteId).toBe("abc-123");
    expect(injected.defer).toBe(true);
  });

  it("normalizes trailing slash in host", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ host: "https://umami.example.com/", id: "abc-123" }),
      }),
    );

    await initAnalytics();
    const scripts = document.head.querySelectorAll("script");
    const injected = Array.from(scripts).find((s) => s.src.includes("script.js"));
    expect(injected).toBeTruthy();
    expect(injected.src).toBe("https://umami.example.com/script.js");
  });

  it.each([
    ["no host/id", async () => ({ ok: true, json: async () => ({}) })],
    [
      "no id",
      async () => ({ ok: true, json: async () => ({ host: "https://umami.example.com" }) }),
    ],
    ["HTTP error", async () => ({ ok: false, status: 404 })],
    ["network error", async () => Promise.reject(new Error("network error"))],
  ])("injects nothing on %s", async (_case, fetchImpl) => {
    vi.stubGlobal("fetch", vi.fn(fetchImpl));
    const originalLength = document.head.querySelectorAll("script").length;

    await initAnalytics();
    expect(document.head.querySelectorAll("script")).toHaveLength(originalLength);
  });
});

describe("alert", () => {
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

  it.each([
    ["yellow", "alert-yellow.svg", "yellow"],
    ["orange", "alert-orange.svg", "orange"],
    ["red", "alert-red.svg", "red"],
    ["unknown", "alert-yellow.svg", "unknown"],
    [null, "alert-green.svg", "green"],
  ])("showAlertCard shows level %s with %s", (level, icon, alt) => {
    const card = createCard("alerts", { name: "Alerty", type: "alerts" }, 0);
    document.getElementById("weather-grid").appendChild(card);

    showAlertCard({ value: "burze", level, valid_to: "2026-07-18T19:00:00Z", updatedText: "Test" });

    expect(card.style.display).toBe("");
    const img = document.getElementById("alerts-icon-img");
    expect(img.src).toContain(icon);
    expect(img.alt).toBe(alt);
    expect(document.getElementById("alerts-value").textContent).toBe("burze");
    expect(document.getElementById("alerts-updated").textContent).toBe("Test");
  });

  it("hideAlertCard hides the card", () => {
    const sensor = { name: "Alerty", type: "alerts" };
    const card = createCard("alerts", sensor, 0);
    document.getElementById("weather-grid").appendChild(card);
    card.style.display = "";

    hideAlertCard();
    expect(card.style.display).toBe("none");
  });

  it("scheduleAlertCheck hides an alert once it expires, with a single timer", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-23T12:00:00Z"));
    const card = createCard("alerts", { name: "Alerty", type: "alerts" }, 0);
    document.getElementById("weather-grid").appendChild(card);
    handleAlertUpdate({
      value: "burze",
      level: "red",
      valid_to: "2026-06-23T12:00:45Z",
      timestamp: "a",
    });
    expect(card.style.display).toBe("");
    const setIntervalSpy = vi.spyOn(globalThis, "setInterval");

    scheduleAlertCheck();
    scheduleAlertCheck();
    vi.advanceTimersByTime(30000);
    expect(card.style.display).toBe("");
    vi.advanceTimersByTime(30000);

    expect(card.style.display).toBe("none");
    expect(alerts).toHaveLength(0);
    expect(setIntervalSpy).toHaveBeenCalledTimes(1);
    setIntervalSpy.mockRestore();
    resetState(); // clears the interval while it is still a fake timer
    vi.useRealTimers();
  });

  it("updateAlertVisibility drops alerts without a valid expiry", () => {
    alerts.push({ value: "undated", level: "red", valid_to: "not a date" });
    updateAlertVisibility();
    expect(alerts).toHaveLength(0);
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

    handleAlertUpdate({
      value: "new",
      level: "yellow",
      valid_to: "2099-01-01T00:00:00Z",
      timestamp: "2",
    });
    handleAlertUpdate({
      value: "older",
      level: "red",
      valid_to: "2099-01-01T00:00:00Z",
      timestamp: "1",
    });
    expect(alerts.length).toBe(2);
    expect(alerts[0].value).toBe("older");
    expect(document.getElementById("alerts-value").textContent).toBe("older");
  });

  it("handleAlertUpdate deduplicates by timestamp", () => {
    handleAlertUpdate({
      value: "first",
      level: "yellow",
      valid_to: "2099-01-01T00:00:00Z",
      timestamp: "same",
    });
    handleAlertUpdate({
      value: "second",
      level: "red",
      valid_to: "2099-01-01T00:00:00Z",
      timestamp: "same",
    });
    expect(alerts.length).toBe(1);
    expect(alerts[0].value).toBe("second");
  });

  it("sendAlertNotification does nothing when permission is denied", () => {
    Notification.permission = "denied";
    sendAlertNotification({ value: "test", level: "red", timestamp: "1" });
    expect(Notification).not.toHaveBeenCalled();
  });

  it("sendAlertNotification does nothing when Notification API is unavailable", () => {
    delete globalThis.Notification; // setup.js stubs it again for the next test
    expect(() =>
      sendAlertNotification({ value: "test", level: "red", timestamp: "1" }),
    ).not.toThrow();
  });

  it("sendAlertNotification fires Notification with correct title and body", () => {
    sendAlertNotification({
      value: "burze",
      level: "orange",
      timestamp: "ts1",
      valid_to: "2099-01-01T00:00:00Z",
    });
    expect(Notification).toHaveBeenCalledWith("Alert meteorologiczny", {
      body: expect.stringMatching(/Pomarańczowy alert: burze\nWażny do: 1 stycznia, \d{2}:\d{2}/),
      tag: "ts1",
    });
  });

  it("sendAlertNotification shows only time for today expiry", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-23T12:00:00Z"));
    sendAlertNotification({
      value: "mgła",
      level: "yellow",
      timestamp: "ts2",
      valid_to: "2026-06-23T15:00:00Z",
    });
    const callBody = Notification.mock.calls[0][1].body;
    expect(callBody).toContain("Żółty alert: mgła");
    expect(callBody).toContain("Ważny do:");
    expect(callBody).not.toContain(",");
    vi.useRealTimers();
  });

  it("sendAlertNotification uses Zielony label for null level", () => {
    sendAlertNotification({
      value: "brak zagrożeń",
      level: null,
      timestamp: "ts3",
      valid_to: "2099-01-01T00:00:00Z",
    });
    expect(Notification).toHaveBeenCalledWith("Alert meteorologiczny", {
      body: expect.stringMatching(/Zielony alert: brak zagrożeń/),
      tag: "ts3",
    });
  });

  it.each([
    ["default", true],
    ["granted", false],
    ["denied", false],
  ])("requestNotificationPermission with permission %s asks: %s", (permission, asks) => {
    Notification.permission = permission;
    requestNotificationPermission();
    expect(Notification.requestPermission).toHaveBeenCalledTimes(asks ? 1 : 0);
  });

  it("requestNotificationPermission does nothing when Notification API is unavailable", () => {
    delete globalThis.Notification; // setup.js stubs it again for the next test
    expect(() => requestNotificationPermission()).not.toThrow();
  });

  it("handleAlertUpdate sends notification for new alerts", () => {
    handleAlertUpdate({
      value: "test",
      level: "yellow",
      valid_to: "2099-01-01T00:00:00Z",
      timestamp: "notif1",
    });
    expect(Notification).toHaveBeenCalledWith(
      "Alert meteorologiczny",
      expect.objectContaining({ body: expect.stringContaining("test") }),
    );
  });

  it("loadAlerts fetches alerts and populates the array", async () => {
    const apiData = [
      {
        value_str: "burze",
        level: "yellow",
        valid_to: "2099-01-01T00:00:00Z",
        timestamp: "2026-06-23T12:00:00Z",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(apiData),
      }),
    );

    await loadAlerts();
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/alerts`);
    expect(alerts.length).toBe(1);
    expect(alerts[0].value).toBe("burze");
  });

  it("loadAlerts logs error on fetch failure", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

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
    const wsMock = { onopen: null, onmessage: null, onclose: null, onerror: null, close: vi.fn() };
    vi.stubGlobal(
      "WebSocket",
      vi.fn(function () {
        return wsMock;
      }),
    );

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
  });

  it("WS message with sun parameter updates sunState and re-renders condition icon", () => {
    const wsMock = { onopen: null, onmessage: null, onclose: null, onerror: null, close: vi.fn() };
    vi.stubGlobal(
      "WebSocket",
      vi.fn(function () {
        return wsMock;
      }),
    );

    sensorsConfig.condition = {
      name: "Warunki",
      type: "condition",
      icon: "mdi:weather-sunny",
      color: "#FDD835",
    };
    const card = createCard("condition", sensorsConfig.condition, 0);
    document.getElementById("weather-grid").appendChild(card);

    connectWebSocket();

    updateCard(
      "condition",
      "partly cloudy",
      null,
      "2026-06-23T12:00:00Z",
      "mdi:weather-partly-cloudy",
    );

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
  });
});

describe("loadSunState", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each([["above_horizon"], ["below_horizon"]])(
    "fetches sun state %s from the API into sunState",
    async (value) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ value }) }),
      );

      await loadSunState();
      expect(fetch).toHaveBeenCalledWith(`${API_BASE}/sun`);
      expect(sunState.value).toBe(value);
    },
  );

  it("ignores null sun state without overriding sunState", async () => {
    sunState.value = "above_horizon";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ value: null, timestamp: null }),
      }),
    );

    await loadSunState();
    expect(sunState.value).toBe("above_horizon");
  });

  it("re-renders condition icons on sun state change", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ value: "below_horizon", timestamp: "2026-06-23T22:00:00Z" }),
      }),
    );

    sensorsConfig.condition = {
      name: "Warunki",
      type: "condition",
      icon: "mdi:weather-sunny",
      color: "#FDD835",
    };
    const card = createCard("condition", sensorsConfig.condition, 0);
    document.getElementById("weather-grid").appendChild(card);
    updateCard(
      "condition",
      "partly cloudy",
      null,
      "2026-06-23T12:00:00Z",
      "mdi:weather-partly-cloudy",
    );

    await loadSunState();
    expect(sunState.value).toBe("below_horizon");
    expect(document.getElementById("condition-icon-img").src).toContain("partly-cloudy-night.svg");
  });

  it("logs warning on HTTP error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await loadSunState();
    expect(console.warn).toHaveBeenCalled();
  });

  it("logs warning on fetch error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));

    await loadSunState();
    expect(console.warn).toHaveBeenCalled();
  });
});

describe("registerServiceWorker", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("registers service-worker.js when the browser supports it", () => {
    const register = vi.fn().mockResolvedValue({});
    vi.stubGlobal("navigator", { serviceWorker: { register } });

    registerServiceWorker();

    expect(register).toHaveBeenCalledWith("/service-worker.js", { scope: "/" });
  });

  it("only warns when registration fails", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const register = vi.fn().mockRejectedValue(new Error("nope"));
    vi.stubGlobal("navigator", { serviceWorker: { register } });

    registerServiceWorker();
    await vi.waitFor(() => expect(warn).toHaveBeenCalled());

    expect(warn.mock.calls[0][0]).toContain("[SW]");
  });

  it("does nothing when the browser has no serviceWorker", () => {
    expect("serviceWorker" in navigator).toBe(false);
    expect(() => registerServiceWorker()).not.toThrow();
  });
});

describe("init", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "WebSocket",
      vi.fn(function () {
        return {
          readyState: 0, // CONNECTING, like a real socket right after construction
          onopen: null,
          onmessage: null,
          onclose: null,
          onerror: null,
          close: vi.fn(),
        };
      }),
    );
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates cards for all sensors", async () => {
    const sensors = {
      temperature: {
        name: "Temp",
        type: "numeric",
        icon: "mdi:thermometer",
        color: "#E53935",
        round: 1,
        unit: "°C",
      },
      condition: {
        name: "Warunki",
        type: "condition",
        icon: "mdi:weather-sunny",
        color: "#FDD835",
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url) => {
        if (url.includes("/sensors")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(sensors) });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ value: "above_horizon" }),
        });
      }),
    );

    await init();
    const grid = document.getElementById("weather-grid");
    expect(grid.children).toHaveLength(2);
    expect(grid.querySelector("#card-temperature")).toBeTruthy();
    expect(grid.querySelector("#card-condition")).toBeTruthy();
    expect(grid.querySelector("#chart-temperature")).toBeTruthy();
    expect(grid.querySelector("#condition-icon-img")).toBeTruthy();
  });

  it("reconnects the WebSocket when the tab becomes visible or the browser comes back online", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) }),
    );

    await init();
    expect(WebSocket).toHaveBeenCalledTimes(1);

    wsState.socket.readyState = 3; // closed
    document.dispatchEvent(new Event("visibilitychange"));
    expect(WebSocket).toHaveBeenCalledTimes(2);

    wsState.socket.readyState = 3;
    window.dispatchEvent(new Event("online"));
    expect(WebSocket).toHaveBeenCalledTimes(3);

    wsState.socket.readyState = 1; // open: nothing to do
    window.dispatchEvent(new Event("online"));
    expect(WebSocket).toHaveBeenCalledTimes(3);
  });

  it("registers the service worker before touching the API", async () => {
    const register = vi.fn().mockResolvedValue({});
    vi.stubGlobal("navigator", { serviceWorker: { register } });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("offline"))),
    );

    await init();

    expect(register).toHaveBeenCalledWith("/service-worker.js", { scope: "/" });
  });

  it("shows an error in the grid and stops when the sensor config cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    await init();

    const grid = document.getElementById("weather-grid");
    expect(grid.children).toHaveLength(1);
    expect(grid.querySelector(".grid__error[role=alert]").textContent).toContain(
      "Nie udało się wczytać konfiguracji czujników",
    );
    expect(console.error).toHaveBeenCalledWith(
      "[Sensors] Error loading sensor configuration:",
      expect.any(Error),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(WebSocket).not.toHaveBeenCalled();
  });

  it("sets charts for numeric sensors", async () => {
    const sensors = {
      temperature: {
        name: "Temp",
        type: "numeric",
        icon: "mdi:thermometer",
        color: "#E53935",
        round: 1,
        unit: "°C",
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url) => {
        if (url.includes("/sensors")) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(sensors) });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ value: "above_horizon" }),
        });
      }),
    );

    await init();
    expect(charts.temperature).toBeTruthy();
  });
});

describe("forecast", () => {
  const SENSOR_FORECAST = {
    forecast: { name: "Prognoza", type: "forecast", icon: "", color: null, round: 1, unit: "" },
  };

  const FORECAST_DATA = [
    {
      datetime: "2026-07-22T00:00:00+00:00",
      is_daytime: true,
      condition: "cloudy",
      temperature: 23.1,
      precipitation: 0.0,
      cloud_coverage: 75,
      wind_speed: 15.0,
    },
    {
      datetime: "2026-07-23T00:00:00+00:00",
      is_daytime: false,
      condition: "rainy",
      temperature: 20.5,
      precipitation: 0.1,
      cloud_coverage: 90,
      wind_speed: 27.36,
    },
    {
      datetime: "2026-07-23T00:00:00+00:00",
      is_daytime: true,
      condition: "partlycloudy",
      temperature: 20.2,
      precipitation: 1.6,
      cloud_coverage: 50,
      wind_speed: 17.28,
    },
    {
      datetime: "2026-07-24T00:00:00+00:00",
      is_daytime: false,
      condition: "partlycloudy",
      temperature: 17.9,
      precipitation: 0.6,
      cloud_coverage: 85,
      wind_speed: 24.84,
    },
    {
      datetime: "2026-07-24T00:00:00+00:00",
      is_daytime: true,
      condition: "rainy",
      temperature: 21.7,
      precipitation: 2.0,
      cloud_coverage: 60,
      wind_speed: 18.5,
    },
    {
      datetime: "2026-07-25T00:00:00+00:00",
      is_daytime: false,
      condition: "partlycloudy",
      temperature: 20.3,
      precipitation: 0.0,
      cloud_coverage: 30,
      wind_speed: 16.2,
    },
  ];

  it("getPolishDayAbbr returns correct Polish abbreviations", () => {
    expect(getPolishDayAbbr(new Date("2026-07-20"))).toBe("pon");
    expect(getPolishDayAbbr(new Date("2026-07-21"))).toBe("wto");
    expect(getPolishDayAbbr(new Date("2026-07-22"))).toBe("śro");
    expect(getPolishDayAbbr(new Date("2026-07-23"))).toBe("czw");
    expect(getPolishDayAbbr(new Date("2026-07-24"))).toBe("pią");
    expect(getPolishDayAbbr(new Date("2026-07-25"))).toBe("sob");
    expect(getPolishDayAbbr(new Date("2026-07-26"))).toBe("nie");
  });

  it("getConditionSvgPath uses isDaytime parameter for partlycloudy", () => {
    expect(getConditionSvgPath("partlycloudy", null, true)).toBe(
      "weather_icons/partly-cloudy-day.svg",
    );
    expect(getConditionSvgPath("partlycloudy", null, false)).toBe(
      "weather_icons/partly-cloudy-night.svg",
    );
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
    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("śro");
    expect(cols[0].querySelector(".forecast-col__period").textContent).toBe("dzień");
    expect(cols[0].querySelector(".forecast-col__temp-value").textContent).toBe("23°C");
    expect(cols[0].querySelector(".forecast-col__precip-value").textContent).toBe("0 mm");
    expect(cols[0].querySelector(".forecast-col__cloud-value").textContent).toBe("75%");
    expect(cols[0].querySelector(".forecast-col__wind-value").textContent).toBe("15 km/h");

    // Item 2: daytime partlycloudy
    expect(cols[2].querySelector(".forecast-col__day").textContent).toBe("czw");
    expect(cols[2].querySelector(".forecast-col__period").textContent).toBe("dzień");
    expect(cols[2].querySelector(".forecast-col__temp-value").textContent).toBe("20°C");
    expect(cols[2].querySelector(".forecast-col__precip-value").textContent).toBe("2 mm");
    expect(cols[2].querySelector(".forecast-col__cloud-value").textContent).toBe("50%");
    expect(cols[2].querySelector(".forecast-col__wind-value").textContent).toBe("17 km/h");

    // Item 3: nighttime partlycloudy
    expect(cols[3].querySelector(".forecast-col__day").textContent).toBe("pią");
    expect(cols[3].querySelector(".forecast-col__period").textContent).toBe("noc");
    expect(cols[3].querySelector(".forecast-col__temp-value").textContent).toBe("18°C");
    expect(cols[3].querySelector(".forecast-col__precip-value").textContent).toBe("1 mm");
    expect(cols[3].querySelector(".forecast-col__cloud-value").textContent).toBe("85%");
    expect(cols[3].querySelector(".forecast-col__wind-value").textContent).toBe("25 km/h");

    // Item 4: daytime rainy
    expect(cols[4].querySelector(".forecast-col__day").textContent).toBe("pią");
    expect(cols[4].querySelector(".forecast-col__period").textContent).toBe("dzień");
    expect(cols[4].querySelector(".forecast-col__temp-value").textContent).toBe("22°C");
    expect(cols[4].querySelector(".forecast-col__precip-value").textContent).toBe("2 mm");
    expect(cols[4].querySelector(".forecast-col__cloud-value").textContent).toBe("60%");
    expect(cols[4].querySelector(".forecast-col__wind-value").textContent).toBe("19 km/h");
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
  });

  it("loadForecast fetches from API and updates card", async () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ forecast: FORECAST_DATA, timestamp: "2026-07-22T12:00:00Z" }),
      }),
    );

    await loadForecast();

    const cols = card.querySelectorAll(".forecast-col");
    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("śro");
    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/forecast`);
  });

  it("loadForecast handles empty response gracefully", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ forecast: [], timestamp: null }),
      }),
    );

    await loadForecast();
    // Should not throw
    vi.restoreAllMocks();
  });

  it("loadForecast handles HTTP error gracefully", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    await loadForecast();
    expect(console.error).toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it("updateCard resets remaining columns when fewer than 5 forecast items arrive", () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    // First populate all 5 columns
    updateCard("forecast", FORECAST_DATA, null, "2026-07-22T12:00:00Z");
    const cols = card.querySelectorAll(".forecast-col");
    expect(cols[4].querySelector(".forecast-col__day").textContent).not.toBe("--");

    // Now update with only 2 items — remaining columns should reset
    const partialData = FORECAST_DATA.slice(0, 2);
    updateCard("forecast", partialData, null, "2026-07-22T13:00:00Z");

    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("śro");
    expect(cols[1].querySelector(".forecast-col__day").textContent).toBe("czw");
    // Columns 2-4 should be reset to placeholder
    expect(cols[2].querySelector(".forecast-col__day").textContent).toBe("--");
    expect(cols[2].querySelector(".forecast-col__period").textContent).toBe("--");
    expect(cols[2].querySelector(".forecast-col__icon").src).toBe("");
    expect(cols[2].querySelector(".forecast-col__temp-value").textContent).toBe("--");
    expect(cols[2].querySelector(".forecast-col__precip-value").textContent).toBe("--");
    expect(cols[2].querySelector(".forecast-col__cloud-value").textContent).toBe("--");
    expect(cols[2].querySelector(".forecast-col__wind-value").textContent).toBe("--");
    expect(cols[3].querySelector(".forecast-col__day").textContent).toBe("--");
    expect(cols[4].querySelector(".forecast-col__day").textContent).toBe("--");
  });

  it("updateCard shows -- for null forecast values instead of NaN", () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    const dataWithNulls = [
      {
        datetime: "2026-07-22T00:00:00+00:00",
        is_daytime: true,
        condition: "cloudy",
        temperature: null,
        precipitation: null,
        cloud_coverage: null,
        wind_speed: null,
      },
    ];
    updateCard("forecast", dataWithNulls, null, "2026-07-22T12:00:00Z");

    const cols = card.querySelectorAll(".forecast-col");
    expect(cols[0].querySelector(".forecast-col__temp-value").textContent).toBe("--");
    expect(cols[0].querySelector(".forecast-col__precip-value").textContent).toBe("--");
    expect(cols[0].querySelector(".forecast-col__cloud-value").textContent).toBe("--");
    expect(cols[0].querySelector(".forecast-col__wind-value").textContent).toBe("--");
  });

  it("loadForecast uses server timestamp when available", async () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    const card = createCard("forecast", SENSOR_FORECAST.forecast, 0);
    document.getElementById("weather-grid").appendChild(card);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            forecast: FORECAST_DATA.slice(0, 1),
            timestamp: "2026-07-22T14:00:00Z",
          }),
      }),
    );

    await loadForecast();

    const updated = document.getElementById("forecast-updated");
    expect(updated.textContent).toContain("14:00:00");
  });
  it("loadCurrent fills numeric, condition and text cards from one request", async () => {
    sensorsConfig.condition = SENSOR_CONDITION.condition;
    sensorsConfig.temperature = SENSOR_NUMERIC.temperature;
    charts.temperature = { data: { datasets: [{ data: [] }] }, update: vi.fn() };
    const grid = document.getElementById("weather-grid");
    grid.appendChild(createCard("condition", SENSOR_CONDITION.condition, 0));
    grid.appendChild(createCard("temperature", SENSOR_NUMERIC.temperature, 1));
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            condition: {
              value_str: "Słonecznie",
              icon: "mdi:weather-sunny",
              timestamp: "2025-06-24T14:00:00Z",
            },
            temperature: { value: 21.55, unit: "°C", timestamp: "2025-06-24T14:00:00Z" },
            pressure: null,
          }),
      }),
    );

    await loadCurrent();

    expect(fetch).toHaveBeenCalledWith(`${API_BASE}/current`);
    expect(document.getElementById("condition-value").textContent).toBe("Słonecznie");
    expect(document.getElementById("condition-icon-img").src).toContain("sunny.svg");
    expect(document.getElementById("temperature-value").textContent).toBe("21.6");
    expect(document.getElementById("temperature-unit").textContent).toBe("°C");
  });

  it("loadCurrent logs and survives an API error", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    await loadCurrent();

    expect(console.error).toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it("loadHistory skips forecast sensor", async () => {
    sensorsConfig.forecast = SENSOR_FORECAST.forecast;
    vi.stubGlobal("fetch", vi.fn());
    await loadHistory("forecast");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("WS forecast message updates the card", () => {
    const wsMock = { onopen: null, onmessage: null, onclose: null, onerror: null, close: vi.fn() };
    vi.stubGlobal(
      "WebSocket",
      vi.fn(function () {
        return wsMock;
      }),
    );

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
    expect(cols[0].querySelector(".forecast-col__day").textContent).toBe("śro");
    expect(cols[1].querySelector(".forecast-col__temp-value").textContent).toBe("21°C");
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
  });
});
