/* TaxiAI service worker — hand-rolled, no build step.
 *
 * Strategy:
 *  - App shell + PWA assets (incl. offline.html) are precached on install.
 *  - /_next/static/* is cache-first (content-hashed, immutable).
 *  - Map raster tiles (tile.openstreetmap.org) are stale-while-revalidate into
 *    a bounded cache, so the map keeps painting in tunnels / dead zones.
 *  - API GET requests (any origin, path /v1/*) are network-first with a cache
 *    fallback, LRU-trimmed so dated finance URLs don't grow the cache forever.
 *  - Page navigations are network-first → cached page → "/" shell →
 *    offline.html as the last-resort fallback.
 *  - Non-GET requests (POST/PATCH/...) are never intercepted or cached.
 *
 * Bump VERSION on any change to this file — old caches are dropped on activate.
 */

const VERSION = "v2";
const SHELL_CACHE = `taxiai-shell-${VERSION}`;
const STATIC_CACHE = `taxiai-static-${VERSION}`;
const API_CACHE = `taxiai-api-${VERSION}`;
const TILE_CACHE = `taxiai-tiles-${VERSION}`;
const EXPECTED_CACHES = [SHELL_CACHE, STATIC_CACHE, API_CACHE, TILE_CACHE];

// Bounded caches: keep the newest N entries, evict the oldest (LRU by re-put).
const API_MAX_ENTRIES = 60;
const TILE_MAX_ENTRIES = 300;

// Raster tile hosts we serve from cache. OSM only for now (a paid provider
// swap is deferred); matched by hostname so subdomains (a/b/c) are covered.
const TILE_HOSTS = ["tile.openstreetmap.org"];

const OFFLINE_URL = "/offline.html";

const APP_SHELL = [
  "/",
  "/plan",
  "/trips",
  "/finance",
  "/chat",
  "/onboarding",
  OFFLINE_URL,
  "/manifest.json",
  "/icon.svg",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-maskable-192.png",
  "/icon-maskable-512.png",
  "/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      // Tolerate individual failures (e.g. a route momentarily 500s) —
      // an incomplete shell cache is better than no service worker.
      Promise.allSettled(APP_SHELL.map((url) => cache.add(url)))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => !EXPECTED_CACHES.includes(k)).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

/** Evict oldest entries so the cache holds at most `max` (keys() is insertion
 * order; re-putting a hit moves it to the tail, giving LRU-ish behaviour). */
async function trimCache(cache, max) {
  const keys = await cache.keys();
  if (keys.length <= max) return;
  await Promise.all(keys.slice(0, keys.length - max).map((k) => cache.delete(k)));
}

async function networkFirst(request, cacheName, fallbackUrl, max) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) {
      // Re-put (delete first) so this entry becomes the freshest for LRU trim.
      if (max != null) await cache.delete(request);
      await cache.put(request, response.clone());
      if (max != null) await trimCache(cache, max);
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (fallbackUrl) {
      const fallback = await caches.match(fallbackUrl);
      if (fallback) return fallback;
    }
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) {
    cache.put(request, response.clone());
  }
  return response;
}

/** Stale-while-revalidate for map tiles: serve the cached tile instantly and
 * refresh it in the background; bound the cache so it can't grow without limit.
 * Opaque cross-origin responses (OSM sends no CORS headers) are cached too —
 * they render fine as <img>/raster and are what keeps the map alive offline. */
async function tileStaleWhileRevalidate(request) {
  const cache = await caches.open(TILE_CACHE);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then(async (response) => {
      if (response.ok || response.type === "opaque") {
        await cache.put(request, response.clone());
        await trimCache(cache, TILE_MAX_ENTRIES);
      }
      return response;
    })
    .catch(() => undefined);
  if (cached) {
    network; // fire-and-forget revalidation
    return cached;
  }
  const response = await network;
  if (response) return response;
  return Response.error();
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Never intercept mutations — POST/PATCH/DELETE go straight to the network.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Map raster tiles (cross-origin): keep the map painting when the network drops.
  if (TILE_HOSTS.includes(url.hostname)) {
    event.respondWith(tileStaleWhileRevalidate(request));
    return;
  }

  // API reads (the backend lives on its own origin, path is always /v1/*).
  if (url.pathname.startsWith("/v1/")) {
    event.respondWith(networkFirst(request, API_CACHE, undefined, API_MAX_ENTRIES));
    return;
  }

  // Page navigations: fresh when online, cached page (or shell) when offline,
  // and finally the precached offline.html so a cold navigate never 404s.
  if (request.mode === "navigate") {
    event.respondWith(
      networkFirst(request, SHELL_CACHE, "/").catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // Everything else we handle is same-origin static content.
  if (url.origin !== self.location.origin) return;

  // Content-hashed build assets never change under the same URL.
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // public/ assets (icons, manifest): network-first with cache fallback.
  event.respondWith(networkFirst(request, SHELL_CACHE));
});
