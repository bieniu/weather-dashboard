// Bumped by scripts/set_version.sh together with the ?v= cache-bust in
// index.html, so every release installs a fresh cache and the activate step
// drops the previous one. Never edit the VERSION line by hand.
const VERSION = "163";
const CACHE = `weather-dashboard-v${VERSION}`;

const WEATHER_ICONS = [
  "air-quality",
  "alert-green",
  "alert-orange",
  "alert-red",
  "alert-yellow",
  "clear-night",
  "cloudy",
  "exceptional",
  "fog",
  "hail",
  "lightning-rainy",
  "lightning",
  "not-available",
  "partly-cloudy-day",
  "partly-cloudy-night",
  "pouring",
  "rainy",
  "snowy-rainy",
  "snowy",
  "sunny",
  "windy",
  "windy-variant",
];

// The app shell, requested with the exact URLs index.html uses (query string
// included, otherwise the cache never matches), plus every icon a card can
// show. "/" doubles as the offline fallback for navigations.
const PRECACHE = [
  "/",
  `/style.css?v=${VERSION}`,
  `/app.js?v=${VERSION}`,
  `/manifest.json?v=${VERSION}`,
  `/vendor/chart.umd.min.js?v=${VERSION}`,
  `/vendor/chartjs-adapter-date-fns.bundle.min.js?v=${VERSION}`,
  "/favicon.svg",
  "/icons/apple-touch-icon.png",
  "/icons/icon-192.png",
  "/icons/icon-512-maskable.png",
  "/icons/icon-512.png",
  ...WEATHER_ICONS.map((name) => `/weather_icons/${name}.svg`),
];

// The sensor configuration is the one API response worth keeping: without it
// the offline shell cannot even draw the cards. Live data stays uncached.
const SENSORS_API = "/api/weather/sensors";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      // cache: "reload" bypasses the HTTP cache (and any edge cache), so the
      // precached shell can never be an older build than the worker itself.
      .then((cache) => cache.addAll(PRECACHE.map((url) => new Request(url, { cache: "reload" }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

// Storing a copy must never delay or fail the response itself (quota errors),
// so it runs under waitUntil instead of being awaited.
function storeInBackground(event, request, response) {
  if (!response.ok) return;
  const copy = response.clone();
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.put(request, copy))
      .catch(() => {}),
  );
}

// Static assets are immutable per version (cache-busted URLs), so a cached
// copy is always right; anything fetched later is stored for offline use.
async function cacheFirst(event) {
  const cached = await caches.match(event.request);
  if (cached) return cached;
  const response = await fetch(event.request);
  storeInBackground(event, event.request, response);
  return response;
}

// Fresh from the network whenever possible (a deploy or config change is
// picked up immediately); the cached copy only serves when the network is down.
async function networkFirst(event, fallbackKey) {
  try {
    const response = await fetch(event.request);
    storeInBackground(event, fallbackKey, response);
    return response;
  } catch (err) {
    const cached = await caches.match(fallbackKey);
    if (cached) return cached;
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // fonts, analytics: browser default
  if (request.mode === "navigate") {
    event.respondWith(networkFirst(event, "/"));
    return;
  }
  if (url.pathname === SENSORS_API) {
    event.respondWith(networkFirst(event, SENSORS_API));
    return;
  }
  if (url.pathname.startsWith("/api/")) return; // live data is never cached
  event.respondWith(cacheFirst(event));
});
