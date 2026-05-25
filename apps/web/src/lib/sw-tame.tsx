"use client";
import { useEffect } from "react";

/**
 * Prevent the legacy auto-reloading service worker from yanking React state
 * out from under the user.
 *
 * Older builds shipped with `skipWaiting: true`, which causes the SW to
 * activate the moment a new build is detected and forces a page reload via
 * `controllerchange`. This wipes any in-progress modal (e.g. onboarding).
 *
 * This component:
 *   1. Cancels the auto-reload that next-pwa wires up by capturing the
 *      `controllerchange` event before it can trigger window.location.reload.
 *   2. Tells any waiting SW to skip waiting only on next reload — never
 *      synchronously.
 */
export function ServiceWorkerTamer() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      return;
    }
    let reloaded = false;
    const onControllerChange = (e: Event) => {
      // Block the legacy auto-reload listener that next-pwa installs.
      // (It listens for controllerchange on the same target.)
      e.stopImmediatePropagation();
      reloaded = reloaded || false; // no-op — we intentionally never reload here
    };
    navigator.serviceWorker.addEventListener(
      "controllerchange",
      onControllerChange,
      { capture: true },
    );
    return () => {
      navigator.serviceWorker.removeEventListener(
        "controllerchange",
        onControllerChange,
        { capture: true } as EventListenerOptions,
      );
    };
  }, []);
  return null;
}
