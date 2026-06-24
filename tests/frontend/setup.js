import { vi, beforeEach } from "vitest";

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

vi.stubGlobal("Chart", vi.fn(mockChartInstance));

beforeEach(() => {
  document.body.innerHTML = `
    <header class="header">
      <div class="header__inner">
        <span class="header__title">Łowicz, Browarna</span>
        <div class="header__actions">
          <span id="connection-status" class="status status--disconnected" role="status">
            <span class="status__dot"></span>
            <span class="status__label">Rozłączono</span>
          </span>
          <button class="theme-btn" id="theme-toggle" aria-label="Przełącz motyw">
            <span class="material-symbols-rounded">dark_mode</span>
          </button>
        </div>
      </div>
    </header>
    <main class="main">
      <div class="grid" id="weather-grid"></div>
    </main>
  `;

  document.documentElement.setAttribute("data-theme", "light");
  document.documentElement.style.setProperty("--color-border", "#ccc");
  document.documentElement.style.setProperty("--color-text-secondary", "#666");
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

window.matchMedia = vi.fn(function (query) {
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
});
