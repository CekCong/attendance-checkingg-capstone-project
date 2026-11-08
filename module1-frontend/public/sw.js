/* Public shell only. Authentication, API responses and submissions never enter CacheStorage. */
const CACHE = "saiv-public-shell-v1";
const SHELL = ["/offline.html", "/manifest.json", "/icon-192.png", "/icon-512.png"];
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys
    .filter((key) => key.startsWith("saiv-public-shell-") && key !== CACHE)
    .map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin ||
      request.headers.has("authorization") || url.pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline.html")));
    return;
  }
  if (SHELL.includes(url.pathname) || url.pathname.startsWith("/_next/static/")) {
    event.respondWith(caches.open(CACHE).then(async (cache) => {
      const saved = await cache.match(request);
      if (saved) return saved;
      const response = await fetch(request);
      if (response.ok && response.type === "basic" && !response.redirected)
        await cache.put(request, response.clone());
      return response;
    }));
  }
});
