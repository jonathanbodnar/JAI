"use client";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, authHeader, BASE } from "@/lib/api";
import { FileText, Sparkles, Upload, X } from "lucide-react";

/**
 * Single-screen onboarding. We do NOT ask quiz questions — that data leaks
 * out of normal conversation anyway. Instead:
 *
 *   - Drag/drop PDFs, .txt, .md (bio, beliefs, business docs, journals)
 *   - Drop your ChatGPT data export (`conversations.json` or the .zip)
 *   - Optionally write one line of bio
 *
 * Anything uploaded gets chunked → Qdrant (semantic memory) and the model
 * pulls identity facts → Mem0 (long-term identity). Skip is always an option.
 */
export function OnboardingGate({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useSWR<{ completed: boolean }>(
    "/onboarding/status",
    (k: string) => api(k),
    {
      // Don't yank the modal out from under the user mid-form.
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      revalidateIfStale: false,
      dedupingInterval: 60_000,
    },
  );
  const [skipped, setSkipped] = useState(false);

  if (isLoading) return <>{children}</>;
  if (data?.completed || skipped) return <>{children}</>;

  return (
    <>
      {children}
      <OnboardingModal onClose={() => setSkipped(true)} />
    </>
  );
}

const DRAFT_KEY = "jai.onboarding.draft";

type Draft = { bio: string };

function loadDraft(): Draft {
  if (typeof window === "undefined") return { bio: "" };
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as Draft) : { bio: "" };
  } catch {
    return { bio: "" };
  }
}

function saveDraft(d: Draft) {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(d));
  } catch {
    // sessionStorage may throw in private mode; ignore.
  }
}

function clearDraft() {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // ignore
  }
}

type IngestSummary = {
  files: number;
  chunks_added: number;
  facts_added: number;
  conversations_added: number;
  skipped: string[];
};

function OnboardingModal({ onClose }: { onClose: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  // Hydrate bio from sessionStorage so an unexpected SW reload or remount
  // doesn't wipe partially-typed text. (Files can't be persisted — browser
  // security forbids it — but the user can re-drop them quickly.)
  const [bio, setBio] = useState<string>(() => loadDraft().bio);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [summary, setSummary] = useState<IngestSummary | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { mutate } = useSWRConfig();

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  // Persist bio on every change.
  useEffect(() => {
    saveDraft({ bio });
  }, [bio]);

  function addFiles(picked: FileList | File[]) {
    const arr = Array.from(picked).filter((f) => f.size > 0);
    setFiles((prev) => [...prev, ...arr]);
  }

  function removeFile(i: number) {
    setFiles((prev) => prev.filter((_, j) => j !== i));
  }

  async function finish(opts: { skip: boolean }) {
    if (busy) return;
    setBusy(true);
    try {
      // 1. Upload files if any
      if (files.length) {
        setProgress(`Ingesting ${files.length} file${files.length > 1 ? "s" : ""}…`);
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f));
        const headers = await authHeader();
        const res = await fetch(`${BASE}/context/ingest`, {
          method: "POST",
          body: fd,
          headers, // FormData sets its own Content-Type
        });
        if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
        const s = (await res.json()) as IngestSummary;
        setSummary(s);
      }

      // 2. Mark onboarded + persist bio (also flips the gate)
      setProgress("Saving…");
      await api("/onboarding", {
        method: "POST",
        body: JSON.stringify({
          skip: opts.skip,
          bio: bio.trim() || null,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }),
      });
      mutate("/onboarding/status");
      clearDraft();

      // Show summary briefly, then close
      if (summary || files.length) {
        setTimeout(onClose, 1500);
      } else {
        onClose();
      }
    } catch (e) {
      setProgress(`Error: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6">
      <div className="bg-[var(--bg-elev)] w-full sm:max-w-lg sm:rounded-2xl rounded-t-2xl border border-[var(--line)] flex flex-col max-h-[92vh]">
        <header className="px-5 py-4 border-b border-[var(--line)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[var(--accent)]" />
            <span className="text-sm font-medium">Seed your second brain</span>
          </div>
          <button
            onClick={onClose}
            className="text-xs text-[var(--fg-mute)] hover:text-white"
            disabled={busy}
          >
            Skip
          </button>
        </header>

        <div className="px-5 py-5 flex-1 overflow-y-auto space-y-5">
          <p className="text-sm text-[var(--fg-mute)] leading-relaxed">
            Drop anything that describes you — bio PDFs, beliefs, business plans,
            journals. Even better: your ChatGPT export (the{" "}
            <code className="text-[var(--fg)]">conversations.json</code> file or its
            zip). I&apos;ll extract identity facts and index everything for recall.
          </p>

          {/* Drop zone */}
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
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-[var(--fg-mute)] uppercase tracking-wider">
              Optional one-line bio
            </label>
            <textarea
              value={bio}
              onChange={(e) => setBio(e.target.value)}
              rows={2}
              placeholder="Founder building JAI. Background in X. Care about Y."
              className="w-full bg-[var(--bg-elev2)] rounded-lg px-3 py-2 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none resize-none"
            />
          </div>

          {progress && (
            <div className="text-xs text-[var(--fg-mute)]">{progress}</div>
          )}

          {summary && (
            <div className="rounded-lg bg-[var(--bg-elev2)] border border-[var(--line)] px-3 py-2 text-xs text-[var(--fg-mute)] space-y-0.5">
              <div>
                <span className="text-[var(--ok)]">✓</span> {summary.files} file
                {summary.files === 1 ? "" : "s"} ingested
              </div>
              <div>{summary.chunks_added} chunks embedded into semantic memory</div>
              {summary.conversations_added > 0 && (
                <div>
                  {summary.conversations_added} ChatGPT conversation
                  {summary.conversations_added === 1 ? "" : "s"} indexed
                </div>
              )}
              {summary.facts_added > 0 && (
                <div>{summary.facts_added} identity facts saved to long-term memory</div>
              )}
              {summary.skipped.length > 0 && (
                <div className="text-[var(--warn)]">
                  Skipped: {summary.skipped.join(", ")}
                </div>
              )}
            </div>
          )}
        </div>

        <footer className="px-5 py-4 border-t border-[var(--line)] flex items-center justify-between gap-2 safe-bottom">
          <button
            onClick={() => finish({ skip: true })}
            disabled={busy}
            className="text-sm text-[var(--fg-mute)] hover:text-white disabled:opacity-40"
          >
            Do this later
          </button>
          <button
            onClick={() => finish({ skip: false })}
            disabled={busy}
            className="bg-[var(--accent)] text-white text-sm font-medium rounded-full px-5 py-2 disabled:opacity-50"
          >
            {busy
              ? "Working…"
              : files.length || bio.trim()
                ? `Ingest ${files.length ? `${files.length} file${files.length > 1 ? "s" : ""}` : "bio"}`
                : "Continue"}
          </button>
        </footer>
      </div>
    </div>
  );
}
