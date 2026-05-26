"use client";

import { useSyncExternalStore } from "react";
import type { CanvasPayload } from "./ws";

/**
 * Tiny module-level store for the canvas side panel.
 *
 * Why not Context: we need to open the canvas from deep in the chat
 * message tree AND react to it at the layout root. Lifting state up
 * would be fine but a 30-line store with useSyncExternalStore is simpler
 * and avoids a top-level Provider every time we add a new surface.
 *
 * Why not zustand: one moving part isn't worth a dependency.
 */
export type CanvasState = {
  open: boolean;
  payload: CanvasPayload | null;
  /** Message id the payload was attached to, so we can deep-link / re-open. */
  messageId: string | null;
};

let state: CanvasState = { open: false, payload: null, messageId: null };
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

export const canvasStore = {
  get: () => state,
  open(payload: CanvasPayload, messageId: string | null = null) {
    state = { open: true, payload, messageId };
    emit();
  },
  close() {
    if (!state.open && !state.payload) return;
    state = { open: false, payload: state.payload, messageId: state.messageId };
    emit();
  },
  clear() {
    state = { open: false, payload: null, messageId: null };
    emit();
  },
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

const serverSnapshot: CanvasState = { open: false, payload: null, messageId: null };

export function useCanvas(): CanvasState {
  return useSyncExternalStore(
    canvasStore.subscribe,
    canvasStore.get,
    () => serverSnapshot,
  );
}
