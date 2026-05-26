"use client";

/** MediaRecorder that captures audio while a button is held and resolves
 * a single Blob on stop.
 *
 * IMPORTANT: do NOT timeslice (`.start(250)`). MediaRecorder only writes the
 * container header on the FIRST emitted chunk; subsequent chunks are raw
 * codec frames. Concatenating those on the server yields a file Whisper /
 * Groq STT can't decode (you get the classic "could not process file — is
 * it a valid media file?" 400). Streaming chunks made our recorder
 * effectively unusable.
 *
 * The new flow: record once, get one complete file out of `stop()`, send it
 * as one binary frame on the WebSocket.
 */
export class PressRecorder {
  private rec: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: BlobPart[] = [];
  public mime = "audio/webm;codecs=opus";

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
      },
    });
    // Pick the best supported container. Safari/iOS fall back to mp4.
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
    ];
    this.mime =
      candidates.find((m) => MediaRecorder.isTypeSupported(m)) ?? "audio/webm";

    this.chunks = [];
    this.rec = new MediaRecorder(this.stream, {
      mimeType: this.mime,
      audioBitsPerSecond: 64000,
    });
    this.rec.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) this.chunks.push(ev.data);
    };
    // No timeslice → we get one cohesive Blob on stop().
    this.rec.start();
  }

  async stop(): Promise<Blob> {
    const rec = this.rec;
    const stream = this.stream;
    if (!rec) throw new Error("not recording");
    const done = new Promise<Blob>((resolve) => {
      rec.onstop = () => resolve(new Blob(this.chunks, { type: this.mime }));
    });
    rec.stop();
    stream?.getTracks().forEach((t) => t.stop());
    this.rec = null;
    this.stream = null;
    return done;
  }
}

/** Simple chunked-audio player. Append base64 mp3 frames as they arrive and
 * it stitches into a single audio element to play out.
 */
export class StreamingAudioPlayer {
  private chunks: Uint8Array[] = [];
  private el: HTMLAudioElement | null = null;
  private mime: string;
  constructor(mime = "audio/mpeg") {
    this.mime = mime;
  }
  push(b64: string) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    this.chunks.push(bytes);
  }
  finish() {
    if (!this.chunks.length) return;
    const blob = new Blob(this.chunks as BlobPart[], { type: this.mime });
    const url = URL.createObjectURL(blob);
    const el = (this.el = new Audio(url));
    el.play().catch(() => { /* user gesture may be required */ });
    el.onended = () => URL.revokeObjectURL(url);
  }
  stop() {
    this.el?.pause();
    this.el = null;
  }
}
