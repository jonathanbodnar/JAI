// Self-destructing service worker.
//
// next-pwa shipped a worker named `/sw.js` that aggressively cached the
// whole app. Returning ANY worker at this path is required (the browser
// keeps the old one alive until the new install completes), but our
// replacement intentionally does the bare minimum: it unregisters itself
// and wipes every cache it knows about, so the next page load goes
// through the network and picks up the real, hot bundle.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      } catch (_) {
        // ignore
      }
      try {
        await self.registration.unregister();
      } catch (_) {
        // ignore
      }
      try {
        const clientList = await self.clients.matchAll({ type: "window" });
        for (const client of clientList) {
          client.navigate(client.url);
        }
      } catch (_) {
        // ignore
      }
    })(),
  );
});

// Never serve anything from cache — always go to network.
self.addEventListener("fetch", () => {});
