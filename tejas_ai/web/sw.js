// Keeps the Tejas screen loading even if the home computer restarts its server.
const CACHE = "tejas-v1";
const SHELL = ["./", "index.html", "styles.css", "app.js", "manifest.webmanifest", "icons/mark.png",
  "icons/icon-192.png", "icons/icon-512.png", "fonts/Geist.woff2", "fonts/Michroma.woff2"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.pathname.startsWith("/api/") || u.origin !== location.origin) return;
  // Network first (so updates show), cache as the fallback.
  e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request)));
});
