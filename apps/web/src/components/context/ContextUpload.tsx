"use client";
import { useRef, useState } from "react";
import { authHeader, BASE } from "@/lib/api";
import { FileText, Upload, X } from "lucide-react";

type IngestSummary = {
  files: number;
  chunks_added: number;
  facts_added: number;
  conversations_added: number;
  skipped: string[];
};

/**
 * Standalone uploader used in Context tab — same backend route as onboarding
 * (`POST /context/ingest`), so anything dropped here is chunked into Qdrant
 * and identity-facts are extracted into Mem0 exactly like onboarding.
 */
export function ContextUpload() {
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [summary, setSummary] = useState<IngestSummary | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [history, setHistory] = useState<IngestSummary[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  function addFiles(picked: FileList | File[]) {
    const arr = Array.from(picked).filter((f) => f.size > 0);
    setFiles((prev) => [...prev, ...arr]);
  }

  function removeFile(i: number) {
    setFiles((prev) => prev.filter((_, j) => j !== i));
  }

  async function ingest() {
    if (!files.length || busy) return;
    setBusy(true);
    setSummary(null);
    setProgress(`Ingesting ${files.length} file${files.length > 1 ? "s" : ""}…`);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const headers = await authHeader();
      const res = await fetch(`${BASE}/context/ingest`, {
        method: "POST",
        body: fd,
        headers,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      const s = (await res.json()) as IngestSummary;
      setSummary(s);
      setHistory((h) => [s, ...h].slice(0, 8));
      setFiles([]);
      setProgress(null);
    } catch (e) {
      setProgress(`Error: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-4 space-y-4 max-w-2xl mx-auto">
      <header>
        <h2 className="text-base font-semibold">Add to context</h2>
        <p className="text-xs text-[var(--fg-mute)] mt-1 leading-relaxed">
          Drop PDFs, Word docs, text, markdown, ChatGPT exports, or any zip
          containing those. Each upload gets chunked into semantic memory and
          identity facts are extracted into long-term memory.
        </p>
      </header>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
        }}
        className={`block border-2 border-dashed rounded-xl px-5 py-8 text-center cursor-pointer transition ${
          dragOver
            ? "border-[var(--accent)] bg-[var(--bg-elev2)]"
            : "border-[var(--line)] hover:border-[var(--fg-mute)]"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          accept=".pdf,.docx,.txt,.md,.json,.zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown,application/json,application/zip"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
        <Upload size={20} className="mx-auto text-[var(--fg-mute)] mb-2" />
        <div className="text-sm">
          <span className="font-medium">Drop files</span>{" "}
          <span className="text-[var(--fg-mute)]">or click to browse</span>
        </div>
        <div className="text-xs text-[var(--fg-mute)] mt-1">
          PDF, DOCX, TXT, MD, JSON, ZIP · up to 25MB each
        </div>
      </label>

      {files.length > 0 && (
        <>
          <ul className="space-y-1.5">
            {files.map((f, i) => (
              <li
                key={`${f.name}-${i}`}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--bg-elev2)] border border-[var(--line)]"
              >
                <FileText size={14} className="text-[var(--fg-mute)] shrink-0" />
                <span className="text-sm truncate flex-1">{f.name}</span>
                <span className="text-xs text-[var(--fg-mute)] shrink-0">
                  {(f.size / 1024).toFixed(0)} KB
                </span>
                <button
                  onClick={() => removeFile(i)}
                  disabled={busy}
                  className="text-[var(--fg-mute)] hover:text-white"
                >
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setFiles([])}
              disabled={busy}
              className="text-sm text-[var(--fg-mute)] hover:text-white px-3 py-1.5 disabled:opacity-40"
            >
              Clear
            </button>
            <button
              onClick={ingest}
              disabled={busy}
              className="bg-[var(--accent)] text-white text-sm font-medium rounded-full px-5 py-2 disabled:opacity-50"
            >
              {busy
                ? "Working…"
                : `Ingest ${files.length} file${files.length > 1 ? "s" : ""}`}
            </button>
          </div>
        </>
      )}

      {progress && <div className="text-xs text-[var(--fg-mute)]">{progress}</div>}

      {summary && <SummaryCard s={summary} />}

      {history.length > 1 && (
        <section className="pt-2">
          <h3 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2">
            Recent uploads
          </h3>
          <ul className="space-y-1.5">
            {history.slice(1).map((s, i) => (
              <li
                key={i}
                className="text-xs text-[var(--fg-mute)] px-3 py-1.5 rounded bg-[var(--bg-elev)] border border-[var(--line)]"
              >
                {s.files} file{s.files === 1 ? "" : "s"} · {s.chunks_added} chunks ·{" "}
                {s.facts_added} facts
                {s.conversations_added > 0
                  ? ` · ${s.conversations_added} chats`
                  : ""}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function SummaryCard({ s }: { s: IngestSummary }) {
  return (
    <div className="rounded-lg bg-[var(--bg-elev2)] border border-[var(--line)] px-3 py-2.5 text-xs space-y-0.5">
      <div>
        <span className="text-[var(--ok)]">✓</span> {s.files} file
        {s.files === 1 ? "" : "s"} ingested
      </div>
      <div className="text-[var(--fg-mute)]">
        {s.chunks_added} chunks embedded into semantic memory
      </div>
      {s.conversations_added > 0 && (
        <div className="text-[var(--fg-mute)]">
          {s.conversations_added} ChatGPT conversation
          {s.conversations_added === 1 ? "" : "s"} indexed
        </div>
      )}
      {s.facts_added > 0 && (
        <div className="text-[var(--fg-mute)]">
          {s.facts_added} identity facts saved to long-term memory
        </div>
      )}
      {s.skipped.length > 0 && (
        <div className="text-[var(--warn)]">Skipped: {s.skipped.join(", ")}</div>
      )}
    </div>
  );
}
