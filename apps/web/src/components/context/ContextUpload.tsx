"use client";
import { useRef, useState } from "react";
import { authHeader, BASE } from "@/lib/api";
import { FileText, Upload, X } from "lucide-react";

type IngestStub = {
  document_id: string;
  filename: string;
  status: string;
  error?: string | null;
};

type IngestResponse = {
  accepted: IngestStub[];
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
  const [summary, setSummary] = useState<IngestResponse | null>(null);
  const [dragOver, setDragOver] = useState(false);
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
    setProgress(`Uploading ${files.length} file${files.length > 1 ? "s" : ""}…`);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const headers = await authHeader();
      // 5 minute timeout — uploads are fast, but huge ChatGPT exports can
      // take a while to *parse* server-side before the response returns.
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 5 * 60_000);
      let res: Response;
      try {
        res = await fetch(`${BASE}/context/ingest`, {
          method: "POST",
          body: fd,
          headers,
          signal: ctrl.signal,
        });
      } finally {
        clearTimeout(timer);
      }
      if (!res.ok) throw new Error(`Upload failed: ${res.status} ${await res.text()}`);
      const s = (await res.json()) as IngestResponse;
      setSummary(s);
      setFiles([]);
      setProgress(
        s.accepted.length
          ? `Accepted ${s.accepted.length} — embedding in the background. Watch the Docs tab.`
          : null,
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "unknown";
      setProgress(`Error: ${msg}`);
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
    </div>
  );
}

function SummaryCard({ s }: { s: IngestResponse }) {
  return (
    <div className="rounded-lg bg-[var(--bg-elev2)] border border-[var(--line)] px-3 py-2.5 text-xs space-y-1.5">
      {s.accepted.length > 0 && (
        <>
          <div>
            <span className="text-[var(--ok)]">✓</span> {s.accepted.length} file
            {s.accepted.length === 1 ? "" : "s"} accepted — processing in background
          </div>
          <ul className="text-[var(--fg-mute)] space-y-0.5">
            {s.accepted.map((a) => (
              <li key={a.document_id}>· {a.filename}</li>
            ))}
          </ul>
          <div className="text-[var(--fg-mute)] italic">
            Watch the Docs tab for status to flip from &ldquo;processing&rdquo; to
            &ldquo;complete&rdquo;.
          </div>
        </>
      )}
      {s.skipped.length > 0 && (
        <div className="text-[var(--warn)]">Skipped: {s.skipped.join(", ")}</div>
      )}
    </div>
  );
}
