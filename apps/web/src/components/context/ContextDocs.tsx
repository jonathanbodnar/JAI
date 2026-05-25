"use client";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { useRealtimeRevalidate } from "@/lib/realtime";
import { FileText, MessageSquare, Search, Trash2 } from "lucide-react";

type Doc = {
  id: string;
  filename: string;
  size_bytes: number | null;
  content_type: string | null;
  kind: "document" | "chatgpt_export";
  chunks_count: number;
  conversations_count: number;
  facts_count: number;
  created_at: string;
};

type Note = {
  id: string;
  title?: string | null;
  body?: string | null;
  updated_at: string;
};

type SearchHit = {
  text: string;
  score: number;
  source?: string | null;
  filename?: string | null;
  title?: string | null;
};

/**
 * Library view. Three sections:
 *   1. Ingested documents (PDFs, DOCX, ChatGPT exports)
 *   2. Semantic search across everything that was indexed
 *   3. Notes (raw user notes that haven't been processed into docs)
 *
 * Documents come from `documents` table (one row per upload). Vectors live in
 * Qdrant. The search bar hits POST /context/search → Qdrant semantic recall.
 */
export function ContextDocs() {
  const { data: docs, mutate: mutateDocs } = useSWR<Doc[]>(
    "/context/documents",
    (k: string) => api(k),
  );
  useRealtimeRevalidate("documents", "/context/documents");

  const { data: notes } = useSWR<Note[]>(
    "/notes?include_archived=true",
    (k: string) => api<Note[]>(k),
  );

  return (
    <div className="p-3 space-y-6 max-w-2xl mx-auto">
      <IngestedDocs docs={docs} onDelete={() => mutateDocs()} />
      <SemanticSearch />
      <NotesSection notes={notes || []} />
    </div>
  );
}

// ---------- Ingested documents ------------------------------------------

function IngestedDocs({
  docs,
  onDelete,
}: {
  docs: Doc[] | undefined;
  onDelete: () => void;
}) {
  return (
    <section>
      <SectionHeader
        title="Ingested files"
        subtitle="What you've uploaded to JAI's memory. Vectors live in Qdrant; identity facts in Mem0."
      />
      {!docs || docs.length === 0 ? (
        <EmptyState text="Drop PDFs, DOCX, or ChatGPT exports in the Upload tab to seed your memory." />
      ) : (
        <ul className="space-y-1.5">
          {docs.map((d) => (
            <DocRow key={d.id} d={d} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </section>
  );
}

function DocRow({ d, onDelete }: { d: Doc; onDelete: () => void }) {
  const [busy, setBusy] = useState(false);
  const Icon = d.kind === "chatgpt_export" ? MessageSquare : FileText;
  const remove = async () => {
    if (busy) return;
    if (!confirm(`Remove ${d.filename} from the library? (Vectors stay until nightly cleanup.)`))
      return;
    setBusy(true);
    try {
      await api(`/context/documents/${d.id}`, { method: "DELETE" });
      onDelete();
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]">
      <Icon size={14} className="text-[var(--fg-mute)] shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{d.filename}</div>
        <div className="text-xs text-[var(--fg-mute)] mt-0.5 flex gap-2 flex-wrap">
          <span>{fmtSize(d.size_bytes)}</span>
          <span>·</span>
          <span>{d.chunks_count} chunks</span>
          {d.conversations_count > 0 && (
            <>
              <span>·</span>
              <span>{d.conversations_count} chats</span>
            </>
          )}
          {d.facts_count > 0 && (
            <>
              <span>·</span>
              <span>{d.facts_count} facts</span>
            </>
          )}
          <span>·</span>
          <span>{fmtDate(d.created_at)}</span>
        </div>
      </div>
      <button
        onClick={remove}
        disabled={busy}
        className="p-1.5 text-[var(--fg-mute)] hover:text-white disabled:opacity-40"
        aria-label="Remove"
      >
        <Trash2 size={14} />
      </button>
    </li>
  );
}

// ---------- Semantic search ---------------------------------------------

function SemanticSearch() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!q.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<SearchHit[]>("/context/search", {
        method: "POST",
        body: JSON.stringify({ q: q.trim(), limit: 10 }),
      });
      setHits(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "search failed");
      setHits(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <SectionHeader
        title="Search your memory"
        subtitle="Semantic recall across every chunk you've ingested or said. Sanity-check that your docs went in."
      />
      <div className="flex items-center gap-2 bg-[var(--bg-elev2)] rounded-full px-3 py-2 border border-[var(--line)]">
        <Search size={14} className="text-[var(--fg-mute)]" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="e.g. what do I believe about leadership"
          className="bg-transparent outline-none text-sm flex-1"
        />
        <button
          onClick={run}
          disabled={busy || !q.trim()}
          className="text-xs text-[var(--accent)] hover:text-white disabled:opacity-40"
        >
          {busy ? "…" : "Search"}
        </button>
      </div>

      {error && <div className="text-xs text-[var(--err)] mt-2">{error}</div>}

      {hits && (
        <ul className="mt-3 space-y-1.5">
          {hits.length === 0 ? (
            <EmptyState text="No matches. Try a broader phrase." />
          ) : (
            hits.map((h, i) => (
              <li
                key={i}
                className="px-3 py-2 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]"
              >
                <div className="text-sm whitespace-pre-wrap line-clamp-4">{h.text}</div>
                <div className="text-xs text-[var(--fg-mute)] mt-1 flex gap-2 flex-wrap">
                  <span>score {h.score.toFixed(3)}</span>
                  {h.filename && (
                    <>
                      <span>·</span>
                      <span>{h.filename}</span>
                    </>
                  )}
                  {h.title && (
                    <>
                      <span>·</span>
                      <span>{h.title}</span>
                    </>
                  )}
                  {h.source && (
                    <>
                      <span>·</span>
                      <span className="opacity-70">{h.source}</span>
                    </>
                  )}
                </div>
              </li>
            ))
          )}
        </ul>
      )}
    </section>
  );
}

// ---------- Notes (raw, not ingested files) -----------------------------

function NotesSection({ notes }: { notes: Note[] }) {
  if (!notes.length) return null;
  const groups = groupByMonth(notes);
  return (
    <section>
      <SectionHeader title="Notes" subtitle="Your Keep-style notes, auto-organized by month." />
      {groups.map(([label, items]) => (
        <div key={label} className="mt-2">
          <h3 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-1.5 px-1">
            {label}
          </h3>
          <ul className="space-y-1.5">
            {items.map((n) => (
              <li
                key={n.id}
                className="px-3 py-2 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]"
              >
                <div className="text-sm font-medium">
                  {n.title || (n.body?.slice(0, 60) ?? "Untitled")}
                </div>
                {n.body && (
                  <div className="text-xs text-[var(--fg-mute)] mt-0.5 line-clamp-2">
                    {n.body}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

// ---------- helpers -----------------------------------------------------

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="mb-2 px-1">
      <h2 className="text-sm font-semibold">{title}</h2>
      {subtitle && <p className="text-xs text-[var(--fg-mute)] mt-0.5">{subtitle}</p>}
    </header>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="px-6 py-8 text-center text-xs text-[var(--fg-mute)] border border-dashed border-[var(--line)] rounded-lg">
      {text}
    </div>
  );
}

function fmtSize(b: number | null | undefined): string {
  if (b == null) return "—";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function groupByMonth(notes: Note[]): [string, Note[]][] {
  const out = new Map<string, Note[]>();
  for (const n of notes) {
    const k = new Date(n.updated_at).toLocaleString(undefined, {
      year: "numeric",
      month: "long",
    });
    out.set(k, [...(out.get(k) ?? []), n]);
  }
  return [...out.entries()];
}
