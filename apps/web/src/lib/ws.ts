"use client";
import { apiBase, wsToken } from "./api";

export type ServerMsg =
  | { type: "user_transcript"; text: string }
  | { type: "assistant_delta"; text: string }
  | { type: "assistant_final"; text: string; role_used?: string }
  | { type: "audio_chunk"; b64: string }
  | { type: "audio_done"; skipped?: boolean }
  | { type: "error"; message: string };

export class ChatSocket {
  private ws: WebSocket | null = null;
  private onMsg: (m: ServerMsg) => void;
  private onOpen?: () => void;
  private onClose?: () => void;

  constructor(opts: {
    onMessage: (m: ServerMsg) => void;
    onOpen?: () => void;
    onClose?: () => void;
  }) {
    this.onMsg = opts.onMessage;
    this.onOpen = opts.onOpen;
    this.onClose = opts.onClose;
  }

  async connect() {
    const token = await wsToken();
    const url =
      apiBase.replace(/^http/, "ws") +
      `/chat/ws${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";
    this.ws.onopen = () => this.onOpen?.();
    this.ws.onclose = () => this.onClose?.();
    this.ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        try {
          this.onMsg(JSON.parse(ev.data));
        } catch {
          /* ignore */
        }
      }
    };
  }

  sendText(text: string) {
    this.ws?.send(JSON.stringify({ type: "user_text", text }));
  }

  sendAudioStart() {
    this.ws?.send(JSON.stringify({ type: "user_audio_start" }));
  }

  sendAudioChunk(buf: ArrayBuffer) {
    this.ws?.send(buf);
  }

  sendAudioDone() {
    this.ws?.send(JSON.stringify({ type: "user_audio_done" }));
  }

  close() {
    this.ws?.close();
    this.ws = null;
  }
}
