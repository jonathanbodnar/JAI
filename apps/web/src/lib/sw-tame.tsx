"use client";
import { useEffect } from "react";

/**
 * Aggressively kill the legacy next-pwa service worker that was caching
 * stale bundles and preventing hotfixes from reaching the user.
 *
 * We no longer ship a real PWA worker (see `next.config.ts`), so the only
 * thing this component does is:
 *   1. Find every registered SW and `.unregister()` it.
 *   2. Wipe every cache the browser created for our origin.
 *   3. Hard-reload exactly once after the first cleanup so the user
 *      immediately sees the fresh bundle.
 *
 * It's safe to leave mounted forever — after the first successful pass it
 * becomes a no-op (no registrations, no caches).
 */
const RELOAD_FLAG = "jai.sw.kill.reloaded.v2";

export function ServiceWorkerTamer() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }

    let cancelled = false;

    const kill = async () => {
      try {
        const regs = await navigator.serviceWorker.getRegistrations();
        if (regs.length === 0 && (await safeCacheKeys()).length === 0) {
          return; // already clean
        }
        await Promise.all(regs.map((r) => r.unregister().catch(() => false)));
        try {
          const keys = await safeCacheKeys();
          await Promise.all(keys.map((k) => caches.delete(k).catch(() => false)));
        } catch {
          // ignore
        }
        if (cancelled) return;
        // One-shot hard reload so the freshly-fetched HTML/JS replaces the
        // SW-served version that's currently rendering this page.
        if (!sessionStorage.getItem(RELOAD_FLAG)) {
          sessionStorage.setItem(RELOAD_FLAG, "1");
          window.location.reload();
        }
      } catch {
        // ignore
      }
    };

    void kill();
    return () => {
      cancelled = true;
    };
  }, []);

  return null;
}

async function safeCacheKeys(): Promise<string[]> {
  try {
    if (typeof caches === "undefined") return [];
    return await caches.keys();
  } catch {
    return [];
  }
}
