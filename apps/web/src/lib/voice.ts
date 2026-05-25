"use client";

/** MediaRecorder that captures audio while a button is held and resolves
 * a Blob on stop. Streams chunks via onChunk so the server can begin
 * processing before the user releases.
 */
export class PressRecorder {
  private rec: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: BlobPart[] = [];
  public mime = "audio/webm;codecs=opus";

  async start(onChunk?: (chunk: ArrayBuffer) => void): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
      },
    });
    // pick a supported mime
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
    ];
    this.mime =
      candidates.find((m) => MediaRecorder.isTypeSupported(m)) ?? "audio/webm";

    this.chunks = [];
    this.rec = new MediaRecorder(this.stream, { mimeType: this.mime, audioBitsPerSecond: 32000 });
    this.rec.ondataavailable = async (ev) => {
      if (ev.data && ev.data.size > 0) {
        this.chunks.push(ev.data);
        if (onChunk) onChunk(await ev.data.arrayBuffer());
      }
    };
    this.rec.start(250);
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
