import { describe, it, expect, vi } from "vitest";
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import vm from "node:vm";

// vitest (and `npm test`) run from the repository root; happy-dom's URL class
// makes import.meta.url unusable for a file path here.
const ROOT = process.cwd();
const SW_SOURCE = readFileSync(join(ROOT, "frontend/service-worker.js"), "utf8");
const ORIGIN = "http://localhost:8332";

function relative(urlOrRequest) {
  const url = typeof urlOrRequest === "string" ? urlOrRequest : urlOrRequest.url;
  return url.startsWith(ORIGIN) ? url.slice(ORIGIN.length) : url;
}

/** Evaluate the worker script against a fake ServiceWorkerGlobalScope + Cache API. */
function loadWorker({ fetch = vi.fn(), existingCaches = [] } = {}) {
  const store = new Map(existingCaches.map((name) => [name, new Map()]));
  const listeners = {};
  const caches = {
    open: vi.fn(async (name) => {
      if (!store.has(name)) store.set(name, new Map());
      const entries = store.get(name);
      return {
        addAll: vi.fn(async (requests) => {
          for (const request of requests) entries.set(relative(request), { cachedFrom: request });
        }),
        put: vi.fn(async (request, response) => {
          entries.set(relative(request), response);
        }),
      };
    }),
    match: vi.fn(async (request) => {
      for (const entries of store.values()) {
        const hit = entries.get(relative(request));
        if (hit) return hit;
      }
      return undefined;
    }),
    keys: vi.fn(async () => [...store.keys()]),
    delete: vi.fn(async (name) => store.delete(name)),
  };
  const self = {
    addEventListener: (type, fn) => {
      listeners[type] = fn;
    },
    skipWaiting: vi.fn(async () => {}),
    clients: { claim: vi.fn(async () => {}) },
    location: { origin: ORIGIN },
  };
  class FakeRequest {
    constructor(url, init = {}) {
      this.url = url.startsWith("http") ? url : `${ORIGIN}${url}`;
      this.cache = init.cache ?? "default";
      this.method = "GET";
    }
  }
  vm.runInNewContext(SW_SOURCE, { self, caches, fetch, URL, Request: FakeRequest, console });
  return { listeners, self, caches, store, fetch };
}

function lifecycleEvent() {
  const event = { waitUntil: vi.fn() };
  event.settled = () => event.waitUntil.mock.calls[0][0];
  return event;
}

function fetchEvent({ url, method = "GET", mode = "cors" }) {
  const event = {
    request: { url: `${ORIGIN}${url}`, method, mode },
    respondWith: vi.fn(),
    waitUntil: vi.fn(),
  };
  if (url.startsWith("http")) event.request.url = url;
  event.response = () => event.respondWith.mock.calls[0][0];
  return event;
}

function currentCacheName() {
  return `weather-dashboard-v${SW_SOURCE.match(/const VERSION = "(\d+)"/)[1]}`;
}

describe("service worker: install", () => {
  it("precaches only files that exist in frontend/ (a single 404 would abort the install)", async () => {
    const { listeners, store } = loadWorker();
    const event = lifecycleEvent();
    listeners.install(event);
    await event.settled();

    const precached = [...store.get(currentCacheName()).keys()];
    expect(precached.length).toBeGreaterThan(20);
    for (const url of precached) {
      const path = url === "/" ? "index.html" : url.replace(/\?v=\d+$/, "").slice(1);
      expect(existsSync(join(ROOT, "frontend", path)), `${url} is missing on disk`).toBe(true);
    }
    expect(precached.some((url) => url.startsWith("/vendor/chart.umd.min.js?v="))).toBe(true);
    const requests = [...store.get(currentCacheName()).values()].map((v) => v.cachedFrom);
    expect(requests.every((request) => request.cache === "reload")).toBe(true);
  });

  it("stays in step with scripts/set_version.sh (round-trip on a copy)", () => {
    const dir = mkdtempSync(join(tmpdir(), "sv-"));
    try {
      for (const f of ["pyproject.toml", "docker-compose.yml"]) cpSync(join(ROOT, f), join(dir, f));
      cpSync(join(ROOT, "frontend/index.html"), join(dir, "frontend/index.html"));
      cpSync(join(ROOT, "frontend/service-worker.js"), join(dir, "frontend/service-worker.js"));
      cpSync(join(ROOT, "scripts/set_version.sh"), join(dir, "scripts/set_version.sh"));
      execFileSync("bash", [join(dir, "scripts/set_version.sh"), "9.8.7"]);

      const html = readFileSync(join(dir, "frontend/index.html"), "utf8");
      const sw = readFileSync(join(dir, "frontend/service-worker.js"), "utf8");
      expect(new Set([...html.matchAll(/\?v=(\d+)/g)].map((m) => m[1]))).toEqual(new Set(["987"]));
      expect(sw).toMatch(/^const VERSION = "987";$/m);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("uses the same version as the ?v= cache-bust in index.html and calls skipWaiting", async () => {
    const html = readFileSync(join(ROOT, "frontend/index.html"), "utf8");
    const htmlVersions = new Set([...html.matchAll(/\?v=(\d+)/g)].map((m) => m[1]));
    const swVersion = SW_SOURCE.match(/const VERSION = "(\d+)"/)[1];
    expect(htmlVersions).toEqual(new Set([swVersion]));

    const { listeners, self } = loadWorker();
    const event = lifecycleEvent();
    listeners.install(event);
    await event.settled();
    expect(self.skipWaiting).toHaveBeenCalledTimes(1);
  });
});

describe("service worker: activate", () => {
  it("deletes every other cache before claiming clients", async () => {
    const stale = "weather-dashboard-v1";
    const { listeners, self, caches, store } = loadWorker({
      existingCaches: [stale, currentCacheName()],
    });
    const event = lifecycleEvent();
    listeners.activate(event);
    await event.settled();

    expect([...store.keys()]).toEqual([currentCacheName()]);
    expect(caches.delete).toHaveBeenCalledWith(stale);
    expect(self.clients.claim).toHaveBeenCalledTimes(1);
    expect(caches.delete.mock.invocationCallOrder[0]).toBeLessThan(
      self.clients.claim.mock.invocationCallOrder[0],
    );
  });
});

describe("service worker: fetch", () => {
  it.each([
    ["POST", "/style.css?v=163", "cors"],
    ["GET", "/api/weather/history/temperature?hours=24", "cors"],
    ["GET", "/api/weather/current", "cors"],
    ["GET", "https://fonts.googleapis.com/css2?family=Sora", "no-cors"],
  ])("leaves %s %s to the browser", (method, url, mode) => {
    const { listeners } = loadWorker();
    const event = fetchEvent({ url, method, mode });
    listeners.fetch(event);
    expect(event.respondWith).not.toHaveBeenCalled();
  });

  it("serves navigations from the network first", async () => {
    const network = { fromNetwork: true };
    const { listeners } = loadWorker({ fetch: vi.fn(async () => network) });
    const event = fetchEvent({ url: "/", mode: "navigate" });
    listeners.fetch(event);
    expect(await event.response()).toBe(network);
  });

  it("falls back to the precached shell for navigations when offline", async () => {
    const { listeners, store } = loadWorker({
      fetch: vi.fn(async () => Promise.reject(new TypeError("offline"))),
    });
    const shell = { shell: true };
    store.set(currentCacheName(), new Map([["/", shell]]));
    const event = fetchEvent({ url: "/", mode: "navigate" });
    listeners.fetch(event);
    expect(await event.response()).toBe(shell);
  });

  it("rejects an offline navigation when no shell was ever cached", async () => {
    const offline = new TypeError("offline");
    const { listeners } = loadWorker({ fetch: vi.fn(async () => Promise.reject(offline)) });
    const event = fetchEvent({ url: "/", mode: "navigate" });
    listeners.fetch(event);
    await expect(event.response()).rejects.toBe(offline);
  });

  it("serves the sensor config network-first and stores it for offline", async () => {
    const network = { ok: true, clone: vi.fn(() => "sensors-copy") };
    const { listeners, store } = loadWorker({ fetch: vi.fn(async () => network) });
    const event = fetchEvent({ url: "/api/weather/sensors" });
    event.waitUntil = vi.fn();
    listeners.fetch(event);
    expect(await event.response()).toBe(network);
    await event.waitUntil.mock.calls[0][0];
    expect(store.get(currentCacheName()).get("/api/weather/sensors")).toBe("sensors-copy");
  });

  it("serves the cached sensor config when the network is down", async () => {
    const { listeners, store } = loadWorker({
      fetch: vi.fn(async () => Promise.reject(new TypeError("offline"))),
    });
    const cachedConfig = { sensors: true };
    store.set(currentCacheName(), new Map([["/api/weather/sensors", cachedConfig]]));
    const event = fetchEvent({ url: "/api/weather/sensors" });
    listeners.fetch(event);
    expect(await event.response()).toBe(cachedConfig);
  });

  it("serves a cached static asset without touching the network", async () => {
    const fetch = vi.fn();
    const { listeners, store } = loadWorker({ fetch });
    const css = { css: true };
    store.set(currentCacheName(), new Map([["/style.css?v=163", css]]));
    const event = fetchEvent({ url: "/style.css?v=163" });
    listeners.fetch(event);
    expect(await event.response()).toBe(css);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("fetches an uncached static asset and stores the successful response", async () => {
    const network = { ok: true, clone: vi.fn(() => "clone") };
    const { listeners, store } = loadWorker({ fetch: vi.fn(async () => network) });
    const event = fetchEvent({ url: "/weather_icons/sunny.svg" });
    listeners.fetch(event);
    expect(await event.response()).toBe(network);
    await event.waitUntil.mock.calls[0][0];
    expect(store.get(currentCacheName()).get("/weather_icons/sunny.svg")).toBe("clone");
  });

  it("does not store failed responses", async () => {
    const network = { ok: false, status: 404, clone: vi.fn() };
    const { listeners, store } = loadWorker({ fetch: vi.fn(async () => network) });
    const event = fetchEvent({ url: "/weather_icons/missing.svg" });
    listeners.fetch(event);
    expect(await event.response()).toBe(network);
    expect(store.get(currentCacheName())).toBeUndefined();
    expect(network.clone).not.toHaveBeenCalled();
  });
});
