// Chart.js line charts for numeric sensors (Chart is the vendored UMD global).
import { getJson, historyHours, sensorsConfig } from "./api.js";
import { formatTimestamp } from "./format.js";

const CHART_DECIMATION_SAMPLES = 200;
const Y_AXIS_WIDTH = 52; // px, fixed so every card's plot area lines up
const TICK_FONT = { family: "JetBrains Mono", size: 11 };
const FILL_ALPHA = "22"; // hex alpha byte, ~13 % opacity

export const charts = {};
// Source arrays of chart points, keyed by parameter. Once the decimation
// plugin kicks in, Chart.js replaces `dataset.data` with an accessor to the
// decimated copy, so the real array must be owned here and re-assigned.
export const chartPoints = {};

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Axis colours of the current theme, read from the CSS tokens once per call. */
function axisStyle() {
  return { grid: getCssVar("--color-border"), ticks: getCssVar("--color-text-secondary") };
}

function applyAxisStyle(scales, style) {
  for (const axis of [scales.x, scales.y]) {
    axis.grid.color = style.grid;
    axis.ticks.color = style.ticks;
  }
}

/** `color` at the fill opacity: #rgb or #rrggbb gets an alpha byte, anything else is transparent. */
export function withAlpha(color) {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color ?? "")?.[1];
  if (!hex) return "transparent";
  const full = hex.length === 3 ? [...hex].map((c) => c + c).join("") : hex;
  return `#${full}${FILL_ALPHA}`;
}

/** Chart options without theme colours (see applyAxisStyle). */
export function buildChartOptions(decimals, unit) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    // Points are stored as { x: epoch ms, y } already sorted by time, so
    // Chart.js can skip parsing and decimate long histories before drawing.
    parsing: false,
    normalized: true,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      decimation: {
        enabled: true,
        algorithm: "lttb",
        samples: CHART_DECIMATION_SAMPLES,
        threshold: 2 * CHART_DECIMATION_SAMPLES, // default would be 4x canvas width
      },
      tooltip: {
        callbacks: {
          label: (ctx) => ` ${ctx.parsed.y.toFixed(decimals)} ${unit}`,
          title: (items) => formatTimestamp(items[0].raw.x),
        },
      },
    },
    scales: {
      x: {
        type: "time",
        time: { unit: "hour", tooltipFormat: "HH:mm", displayFormats: { hour: "HH:mm" } },
        grid: {},
        ticks: { font: TICK_FONT, maxTicksLimit: 6 },
      },
      y: {
        grid: {},
        ticks: { font: TICK_FONT, callback: (value) => Number(value).toFixed(decimals) },
        afterFit(scale) {
          scale.width = Y_AXIS_WIDTH;
        },
      },
    },
  };
}

export function createChart(canvasId, color, decimals, unit) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  const options = buildChartOptions(decimals, unit);
  applyAxisStyle(options.scales, axisStyle());

  return new Chart(ctx, {
    type: "line",
    data: {
      datasets: [
        {
          data: [],
          borderColor: color,
          backgroundColor: withAlpha(color),
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.3,
          fill: true,
        },
      ],
    },
    options,
  });
}

export function updateChartTheme() {
  const style = axisStyle();
  for (const chart of Object.values(charts)) {
    applyAxisStyle(chart.options.scales, style);
    chart.update("none"); // colours only: no need to animate every chart
  }
}

// Keeps the last `history_hours` of data, measured from the newest point so
// the window is exactly what the backend would return for the same sensor.
export function trimChartData(parameter, data) {
  if (data.length === 0) return;
  const windowMs = historyHours(sensorsConfig[parameter]) * 60 * 60 * 1000;
  const cutoff = data[data.length - 1].x - windowMs;
  while (data.length && data[0].x < cutoff) data.shift();
}

function sourcePoints(parameter) {
  chartPoints[parameter] ??= charts[parameter].data.datasets[0].data;
  return chartPoints[parameter];
}

function setChartData(parameter, data, mode) {
  chartPoints[parameter] = data;
  charts[parameter].data.datasets[0].data = data; // through the accessor if decimated
  charts[parameter].update(mode);
}

export function appendChartPoint(parameter, value, timestamp) {
  if (!charts[parameter]) return;
  const data = sourcePoints(parameter);
  data.push({ x: Date.parse(timestamp), y: value });
  trimChartData(parameter, data);
  setChartData(parameter, data, "none");
}

export async function loadHistory(parameter) {
  if (!charts[parameter]) return;
  try {
    const hours = historyHours(sensorsConfig[parameter]);
    const history = await getJson(`/history/${parameter}?hours=${hours}`);
    const points = history.map((r) => ({ x: Date.parse(r.timestamp), y: r.value }));
    const newest = points.length > 0 ? points[points.length - 1].x : -Infinity;
    // The WebSocket is open while this request is in flight: keep the live
    // points that are newer than the history instead of overwriting them.
    const live = sourcePoints(parameter).filter((p) => p.x > newest);
    const data = points.concat(live);
    trimChartData(parameter, data);
    setChartData(parameter, data, undefined);
  } catch (err) {
    console.error(`[History] Error fetching ${parameter}:`, err);
  }
}

/** History for every chart that exists (i.e. every numeric sensor). */
export function loadAllHistory() {
  return Promise.all(Object.keys(charts).map(loadHistory));
}

export function resetCharts() {
  for (const store of [charts, chartPoints]) {
    for (const key of Object.keys(store)) delete store[key];
  }
}
