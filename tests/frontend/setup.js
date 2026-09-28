import { vi, beforeEach, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Before any app module loads: format.js builds its Intl formatters at import.
process.env.TZ = "UTC";

// The real page markup (vitest runs from the repository root), minus the
// module script tag, so tests exercise the same DOM the browser gets.
const INDEX_HTML = readFileSync(join(process.cwd(), "frontend/index.html"), "utf8");
const bodyMatch = INDEX_HTML.match(/<body[^>]*>([\s\S]*)<\/body>/);
if (!bodyMatch) throw new Error("frontend/index.html has no <body>…</body> to load into tests");
const BODY_HTML = bodyMatch[1].replace(/<script[\s\S]*?<\/script>/g, "");

function mockChartInstance() {
  return {
    data: { datasets: [{ data: [] }] },
    options: {
      scales: {
        x: { grid: { color: "" }, ticks: { color: "" } },
        y: { grid: { color: "" }, ticks: { color: "" } },
      },
    },
    update: vi.fn(),
    destroy: vi.fn(),
  };
}

function mockMediaQueryList(query) {
  return {
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  };
}

beforeEach(() => {
  vi.stubGlobal("Chart", vi.fn(mockChartInstance));
  const NotificationMock = vi.fn();
  NotificationMock.permission = "granted";
  NotificationMock.requestPermission = vi.fn();
  vi.stubGlobal("Notification", NotificationMock);
  vi.stubGlobal("matchMedia", vi.fn(mockMediaQueryList));
  // Tests that talk to the API stub their own responses; nothing reaches the network.
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("fetch is not stubbed in this test"))),
  );

  document.body.innerHTML = BODY_HTML;
  document.documentElement.setAttribute("data-theme", "light");
  document.documentElement.style.setProperty("--color-border", "#ccc");
  document.documentElement.style.setProperty("--color-text-secondary", "#666");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

Element.prototype.animate = vi.fn(function () {
  return {
    finished: Promise.resolve(),
    cancel: vi.fn(),
  };
});

HTMLCanvasElement.prototype.getContext = vi.fn(function () {
  return {};
});
