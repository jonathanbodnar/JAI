"use client";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Pin, Plus, Search, Trash2, Archive, StickyNote, Loader2, FolderHeart } from "lucide-react";
import { cn } from "@/lib/cn";
import { useRealtimeRevalidate } from "@/lib/realtime";

type Note = {
  id: string;
  title?: string | null;
  body?: string | null;
  color?: string;
  pinned?: boolean;
  archived?: boolean;
  labels?: string[];
  checklist?: { text: string; checked: boolean }[];
  updated_at: string;
};

export function NotesView() {
  const { mutate } = useSWRConfig();
  const { data: notes, isLoading } = useSWR<Note[]>("/notes", (k: string) => api(k));
  useRealtimeRevalidate("notes", "/notes");
  const [q, setQ] = useState("");

  const filtered = (notes || []).filter((n) => {
    if (!q.trim()) return true;
    const hay = `${n.title ?? ""}\n${n.body ?? ""}\n${(n.labels ?? []).join(" ")}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  });

  const pinned = filtered.filter((n) => n.pinned);
  const others = filtered.filter((n) => !n.pinned);

  return (
    <div className="flex flex-col h-full bg-[#131314] select-none text-[#ececef]">
      {/* Header with Search */}
      <header className="header-safe-pt px-6 pb-4 flex flex-col sm:flex-row sm:items-center gap-4 border-b border-[#2d2f31] bg-[#131314]/80 backdrop-blur-xl z-20 shrink-0">
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-tr from-[#ec4899] to-[#8b5cf6] shadow-[0_0_15px_rgba(236,72,153,0.3)]">
            <StickyNote size={18} className="text-white" />
          </div>
          <h1 className="text-base font-bold tracking-tight text-white">My Notes</h1>
        </div>

        {/* Floating Search Pill */}
        <div className="flex-1 max-w-md flex items-center gap-2.5 bg-[#1e1f20] border border-[#2d2f31] rounded-full px-4 py-1.5 focus-within:border-zinc-700 transition-all duration-200">
          <Search size={15} className="text-[#8e918f]" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search notes..."
            className="bg-transparent outline-none text-[14px] flex-1 text-[#e3e3e3] placeholder-[#8e918f]"
          />
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto pb-28">
        <div className="max-w-7xl mx-auto px-6 py-6 space-y-8">
          <div className="max-w-2xl mx-auto">
            <Composer onCreated={() => mutate("/notes")} />
          </div>

          {isLoading && (
            <div className="flex justify-center py-12">
              <Loader2 size={24} className="animate-spin text-[#8e918f]" />
            </div>
          )}

          {!isLoading && (
            <div className="space-y-6">
              {pinned.length > 0 && (
                <div className="space-y-2">
                  <SectionLabel>Pinned</SectionLabel>
                  <Masonry>
                    {pinned.map((n) => (
                      <NoteCard key={n.id} n={n} onMutate={() => mutate("/notes")} />
                    ))}
                  </Masonry>
                </div>
              )}

              {others.length > 0 && (
                <div className="space-y-2">
                  {pinned.length > 0 && <SectionLabel>Others</SectionLabel>}
                  <Masonry>
                    {others.map((n) => (
                      <NoteCard key={n.id} n={n} onMutate={() => mutate("/notes")} />
                    ))}
                  </Masonry>
                </div>
              )}

              {(!notes || notes.length === 0) && (
                <div className="flex flex-col items-center justify-center gap-3 py-16 text-center text-sm text-[#8e918f] max-w-sm mx-auto">
                  <FolderHeart size={36} className="text-[#3c3d3f]" />
                  <p className="font-semibold text-zinc-300">Your whiteboard is empty</p>
                  <p className="text-xs leading-normal">
                    Say &ldquo;make a note: …&rdquo; to JAI or tap the bar above to start writing. Notes are saved instantly.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-1 text-xs font-bold uppercase tracking-wider text-[#8e918f]">
      {children}
    </div>
  );
}

function Masonry({ children }: { children: React.ReactNode }) {
  return <div className="keep-masonry py-1">{children}</div>;
}

/**
 * Clean elegant note composer. Auto-saves on click-away or Escape.
 */
function Composer({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const submittingRef = useRef(false);

  const submit = async () => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      const t = title.trim();
      const b = body.trim();
      if (!t && !b) {
        setOpen(false);
        return;
      }
      await api("/notes", {
        method: "POST",
        body: JSON.stringify({ title: t || null, body: b || null }),
      });
      setTitle("");
      setBody("");
      setOpen(false);
      onCreated();
    } finally {
      submittingRef.current = false;
    }
  };

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (!containerRef.current) return;
      if (containerRef.current.contains(e.target as Node)) return;
      void submit();
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("touchstart", onDown);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("touchstart", onDown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, title, body]);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2.5 px-5 py-3.5 rounded-2xl border border-dashed border-[#2d2f31] text-[var(--accent)] text-sm font-semibold hover:border-[var(--accent)]/50 hover:bg-[#1e1f20]/30 transition-all w-full select-none"
      >
        <span className="h-6 w-6 rounded-full bg-[var(--accent)]/10 flex items-center justify-center">
          <Plus size={14} strokeWidth={2.5} />
        </span>
        Take a note...
      </button>
    );
  }

  return (
    <div
      ref={containerRef}
      className="rounded-2xl border border-[var(--accent)]/30 bg-[#1e1f20] p-5 space-y-3 shadow-lg"
    >
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        className="w-full bg-transparent outline-none text-[15px] font-bold text-white placeholder-[#8e918f]"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit();
        }}
        rows={3}
        placeholder="Take a note..."
        className="w-full bg-transparent outline-none text-[14px] text-[#e3e3e3] placeholder-[#8e918f] resize-none leading-relaxed"
      />
      <div className="flex justify-end pt-1">
        <button
          onClick={() => void submit()}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[var(--accent)]/10 hover:bg-[var(--accent)]/20 text-[var(--accent)] transition-all flex items-center gap-1"
        >
          Close & Auto-Save
        </button>
      </div>
    </div>
  );
}

function NoteCard({ n, onMutate }: { n: Note; onMutate: () => void }) {
  const bg = colorClass(n.color || "default");
  const [busy, setBusy] = useState(false);

  const togglePin = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await api(`/notes/${n.id}`, {
      method: "PATCH",
      body: JSON.stringify({ pinned: !n.pinned }),
    });
    onMutate();
  };

  const remove = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (busy) return;
    const preview = (n.title || n.body || "").slice(0, 45).trim() || "this note";
    if (!confirm(`Delete "${preview}"? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await api(`/notes/${n.id}`, { method: "DELETE" });
      onMutate();
    } catch (err) {
      alert(`Delete failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const archive = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(true);
    try {
      await api(`/notes/${n.id}`, {
        method: "PATCH",
        body: JSON.stringify({ archived: !n.archived }),
      });
      onMutate();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={cn(
        "group rounded-2xl border border-[#2d2f31]/60 p-5 text-[15px] leading-relaxed relative hover:border-zinc-600 transition-all duration-200 shadow-md hover:shadow-lg",
        bg,
      )}
    >
      <div className="flex items-start gap-3">
        {n.title && <div className="font-bold text-white flex-1 break-words leading-snug text-[16px]">{n.title}</div>}
        {!n.title && <div className="flex-1" />}
        <button
          onClick={togglePin}
          className={cn(
            "p-1 rounded-md text-[#8e918f] hover:text-white transition-colors shrink-0",
            n.pinned && "text-[var(--accent)]"
          )}
          title={n.pinned ? "Unpin note" : "Pin note"}
          aria-label="Pin"
        >
          <Pin size={13} className={n.pinned ? "fill-current" : ""} />
        </button>
      </div>

      {n.checklist && n.checklist.length > 0 ? (
        <ul className="mt-2.5 space-y-1.5">
          {n.checklist.map((c, i) => (
            <li key={i} className="flex items-center gap-2.5 text-[13.5px] font-medium text-zinc-300">
              <span
                className={cn(
                  "h-4 w-4 rounded-sm border shrink-0 transition-colors",
                  c.checked
                    ? "bg-[var(--accent)] border-[var(--accent)]"
                    : "border-[#8e918f]/50"
                )}
              />
              <span className={c.checked ? "line-through text-[#8e918f]" : ""}>{c.text}</span>
            </li>
          ))}
        </ul>
      ) : n.body ? (
        <div className="mt-2 whitespace-pre-wrap break-words text-zinc-200 leading-relaxed font-normal text-[14.5px]">
          {n.body}
        </div>
      ) : null}

      {n.labels && n.labels.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {n.labels.map((l) => (
            <span
              key={l}
              className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#131314]/50 border border-[#2d2f31]/40 text-[#8e918f]"
            >
              {l}
            </span>
          ))}
        </div>
      )}

      {/* Dynamic Actions Row on Hover */}
      <div className="mt-3 -mb-1 flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <button
          onClick={archive}
          disabled={busy}
          className="p-1.5 rounded hover:bg-black/20 text-[#8e918f] hover:text-white disabled:opacity-40 transition-colors"
          title={n.archived ? "Unarchive" : "Archive"}
          aria-label="Archive"
        >
          <Archive size={13} />
        </button>
        <button
          onClick={remove}
          disabled={busy}
          className="p-1.5 rounded hover:bg-red-500/10 text-[#8e918f] hover:text-red-400 disabled:opacity-40 transition-colors"
          title="Delete note"
          aria-label="Delete"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}

function colorClass(c: string | undefined) {
  switch (c) {
    case "red":    return "bg-[#331c1c]/80 border-red-900/40";
    case "orange": return "bg-[#3c2415]/80 border-amber-900/40";
    case "yellow": return "bg-[#352d11]/80 border-yellow-900/40";
    case "green":  return "bg-[#1c3222]/80 border-emerald-900/40";
    case "teal":   return "bg-[#112d2b]/80 border-teal-900/40";
    case "blue":   return "bg-[#1c293a]/80 border-blue-900/40";
    case "dblue":  return "bg-[#131d2c]/80 border-blue-950/40";
    case "purple": return "bg-[#291a3a]/80 border-purple-900/40";
    case "pink":   return "bg-[#321626]/80 border-pink-900/40";
    case "brown":  return "bg-[#292019]/80 border-stone-800/40";
    case "gray":   return "bg-[#1e1f20]/90 border-[#2d2f31]";
    default:       return "bg-[#1e1f20] hover:bg-[#202124]";
  }
}
