/* TaxiAI service worker — hand-rolled, no build step.
 *
 * Strategy:
 *  - App shell + PWA assets are precached on install.
 *  - /_next/static/* is cache-first (content-hashed, immutable).
 *  - API GET requests (any origin, path /v1/*) are network-first with a
 *    cache fallback, so the last known data survives going offline.
 *  - Page navigations are network-first, falling back to the cached page
 *    and finally to the cached "/" shell.
 *  - Non-GET requests (POST/PATCH/...) are never intercepted or cached.
 *
 * Bump VERSION on any change to this file — old caches are dropped on activate.
 */

const VERSION = "v1";
const SHELL_CACHE = `taxiai-shell-${VERSION}`;
const STATIC_CACHE = `taxiai-static-${VERSION}`;
const API_CACHE = `taxiai-api-${VERSION}`;
const EXPECTED_CACHES = [SHELL_CACHE, STATIC_CACHE, API_CACHE];

const APP_SHELL = [
  "/",
  "/plan",
  "/trips",
  "/finance",
  "/chat",
  "/onboarding",
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

async function networkFirst(request, cacheName, fallbackUrl) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
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

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Never intercept mutations — POST/PATCH/DELETE go straight to the network.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // API reads (the backend lives on its own origin, path is always /v1/*).
  if (url.pathname.startsWith("/v1/")) {
    event.respondWith(networkFirst(request, API_CACHE));
    return;
  }

  // Page navigations: fresh when online, cached page (or shell) when offline.
  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, SHELL_CACHE, "/"));
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
