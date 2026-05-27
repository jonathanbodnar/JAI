"use client";
import { apiBase, wsToken } from "./api";

export type CanvasAction = {
  id: string;
  label: string;
  prompt: string;
  is_template?: boolean;
};

export type CanvasPayload = {
  kind: "email_draft" | "document" | "code" | "plan" | "list";
  title: string;
  content: string;
  language?: string;
  metadata?: Record<string, unknown> | null;
  actions?: CanvasAction[];
  source_skill?: string | null;
};

export type ServerMsg =
  | { type: "user_transcript"; text: string }
  | { type: "assistant_delta"; text: string }
  // Per-token chunk streamed from respond/reflect/strategize while the
  // graph node is still running. The client appends these to a live
  // assistant bubble so the user sees progress instead of a 30-second
  // silence on slow Kimi calls.
  | { type: "token"; node: string; text: string }
  | {
      type: "assistant_final";
      text: string;
      role_used?: string;
      canvas?: CanvasPayload | null;
    }
  | { type: "step"; node: string; label: string; detail?: string | null }
  | { type: "audio_chunk"; b64: string }
  | { type: "audio_done"; skipped?: boolean }
  | { type: "pong" }
  | { type: "error"; message: string };

type Opts = {
  onMessage: (m: ServerMsg) => void;
  onOpen?: () => void;
  onClose?: () => void;
};

/**
 * Resilient chat WebSocket.
 *
 * - Reconnects automatically with exponential backoff (1s → 30s).
 * - Sends a JSON `ping` every 25s so Cloudflare / Railway proxies don't
 *   reap the connection as idle. The server replies with `pong`.
 * - Reconnects immediately when the tab becomes visible again or the
 *   network comes back online (browsers often quietly kill background
 *   sockets).
 * - Treats the socket as "live" only when `readyState === OPEN`, so the
 *   indicator never lies.
 */
export class ChatSocket {
  private ws: WebSocket | null = null;
  private onMsg: (m: ServerMsg) => void;
  private onOpen?: () => void;
  private onClose?: () => void;

  private closedByUser = false;
  private retry = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;

  constructor(opts: Opts) {
    this.onMsg = opts.onMessage;
    this.onOpen = opts.onOpen;
    this.onClose = opts.onClose;

    if (typeof window !== "undefined") {
      window.addEventListener("online", this.handleOnline);
      document.addEventListener("visibilitychange", this.handleVisibility);
    }
  }

  private handleOnline = () => {
    // Kick a fresh attempt the moment we regain a network.
    if (this.ws?.readyState !== WebSocket.OPEN) {
      this.retry = 0;
      this.scheduleReconnect(50);
    }
  };

  private handleVisibility = () => {
    if (document.visibilityState !== "visible") return;
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.retry = 0;
    this.scheduleReconnect(50);
  };

  async connect() {
    this.closedByUser = false;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    let token: string | undefined;
    try {
      token = await wsToken();
    } catch {
      // We'll still try without — backend will reject and we'll retry.
    }

    const url =
      apiBase.replace(/^http/, "ws") +
      `/chat/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      this.retry = 0;
      this.startPing();
      this.onOpen?.();
    };

    ws.onclose = () => {
      this.stopPing();
      this.onClose?.();
      if (!this.closedByUser) this.scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will follow; nothing to do here besides surfacing if needed.
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      try {
        const msg = JSON.parse(ev.data) as ServerMsg;
        if (msg.type === "pong") return; // swallow heartbeats
        this.onMsg(msg);
      } catch {
        /* ignore malformed frames */
      }
    };

    this.ws = ws;
  }

  private scheduleReconnect(minMs?: number) {
    if (this.closedByUser) return;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    const base = minMs ?? Math.min(30_000, 1_000 * Math.pow(2, this.retry));
    const jitter = Math.floor(Math.random() * 400);
    const delay = base + jitter;
    this.retry = Math.min(this.retry + 1, 6);
    this.retryTimer = setTimeout(() => {
      void this.connect();
    }, delay);
  }

  private startPing() {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ type: "ping" }));
        } catch {
          /* ignore */
        }
      }
    }, 25_000);
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  sendText(text: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      // Try to (re)connect so a quick send-after-blip still goes through.
      void this.connect();
      return;
    }
    this.ws.send(JSON.stringify({ type: "user_text", text }));
  }

  sendAudioStart() {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: "user_audio_start" }));
  }

  sendAudioChunk(buf: ArrayBuffer) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(buf);
  }

  sendAudioDone() {
    if (this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ type: "user_audio_done" }));
  }

  close() {
    this.closedByUser = true;
    if (this.retryTimer) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.stopPing();
    if (typeof window !== "undefined") {
      window.removeEventListener("online", this.handleOnline);
      document.removeEventListener("visibilitychange", this.handleVisibility);
    }
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
  }
}
