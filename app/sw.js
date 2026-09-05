const THEME_CACHE = "ranchr-theme";
const THEME_PATH = new URL("./theme.css", self.registration.scope).pathname;

self.addEventListener("install", (event) => {
  self.skipWaiting();
});
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
self.addEventListener("message", (event) => {
  const data = event.data || {};
  if (data.type !== "ranch-theme" || !data.css) return;
  event.waitUntil(
    caches.open(THEME_CACHE).then((cache) =>
      cache.put(
        new URL("./theme.css", self.registration.scope).href,
        new Response(data.css, {
          headers: {
            "Content-Type": "text/css; charset=utf-8",
            "Cache-Control": "no-store",
          },
        })
      )
    )
  );
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.includes("/api/")) return;
  if (/\.(js|html)$/.test(url.pathname) || url.pathname.endsWith("/")) {
    event.respondWith(fetch(event.request, { cache: "reload" }));
    return;
  }
  if (url.pathname === THEME_PATH || url.pathname.endsWith("/theme.css")) {
    event.respondWith(
      caches.open(THEME_CACHE).then(async (cache) => {
        const hit = await cache.match(new URL("./theme.css", self.registration.scope).href);
        if (hit) return hit;
        return fetch(event.request);
      })
    );
    return;
  }
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
