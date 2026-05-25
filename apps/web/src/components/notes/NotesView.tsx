"use client";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Pin, Plus, Search } from "lucide-react";
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
  const { data: notes } = useSWR<Note[]>("/notes", (k: string) => api(k));
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
    <div className="flex flex-col h-full">
      <header className="safe-top px-3 py-2 flex items-center gap-2 border-b border-[var(--line)]">
        <div className="flex-1 flex items-center gap-2 bg-[var(--bg-elev2)] rounded-full px-3 py-1.5">
          <Search size={16} className="text-[var(--fg-mute)]" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search your notes"
            className="bg-transparent outline-none text-sm flex-1"
          />
        </div>
      </header>

      <Composer onCreated={() => mutate("/notes")} />

      <div className="flex-1 overflow-y-auto px-3 pb-6">
        {pinned.length > 0 && (
          <>
            <SectionLabel>Pinned</SectionLabel>
            <Masonry>
              {pinned.map((n) => (
                <NoteCard key={n.id} n={n} onMutate={() => mutate("/notes")} />
              ))}
            </Masonry>
            {others.length > 0 && <SectionLabel>Others</SectionLabel>}
          </>
        )}
        <Masonry>
          {others.map((n) => (
            <NoteCard key={n.id} n={n} onMutate={() => mutate("/notes")} />
          ))}
        </Masonry>
        {(!notes || notes.length === 0) && (
          <div className="px-6 py-16 text-center text-sm text-[var(--fg-mute)]">
            No notes yet. Say &ldquo;make a note: …&rdquo; to JAI or tap the box above.
          </div>
        )}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-1 pt-3 pb-2 text-xs uppercase tracking-wider text-[var(--fg-mute)]">
      {children}
    </div>
  );
}

function Masonry({ children }: { children: React.ReactNode }) {
  return <div className="keep-masonry py-1">{children}</div>;
}

/**
 * Google Keep–style composer: click to expand, then anything you type
 * auto-saves when you click outside the card. No explicit Save button.
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

  // Auto-close + auto-save when the user clicks anywhere outside.
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
    // submit closes over title/body via refs implicitly; we want fresh values
    // each call so re-bind on changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, title, body]);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mx-3 mt-3 flex items-center gap-2 px-4 py-3 rounded-xl border border-[var(--line)] text-[var(--fg-mute)] text-sm bg-[var(--bg-elev)]"
      >
        <Plus size={16} />
        Take a note…
      </button>
    );
  }
  return (
    <div
      ref={containerRef}
      className="mx-3 mt-3 rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-3"
    >
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        className="w-full bg-transparent outline-none text-[15px] font-medium mb-1"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit();
        }}
        rows={2}
        placeholder="Take a note…"
        className="w-full bg-transparent outline-none text-[14px] resize-none"
      />
      <div className="flex justify-end mt-2">
        <button
          onClick={() => void submit()}
          className="text-xs text-[var(--fg-mute)] hover:text-white px-2 py-1"
        >
          Close
        </button>
      </div>
    </div>
  );
}

function NoteCard({ n, onMutate }: { n: Note; onMutate: () => void }) {
  const bg = colorClass(n.color || "default");
  const togglePin = async () => {
    await api(`/notes/${n.id}`, {
      method: "PATCH",
      body: JSON.stringify({ pinned: !n.pinned }),
    });
    onMutate();
  };
  return (
    <div
      className={cn(
        "rounded-xl border border-[var(--line)] p-3 text-[14px] leading-snug",
        bg,
      )}
    >
      <div className="flex items-start gap-2">
        {n.title && <div className="font-medium flex-1 break-words">{n.title}</div>}
        {!n.title && <div className="flex-1" />}
        <button
          onClick={togglePin}
          className={cn(
            "p-1 rounded-md text-[var(--fg-mute)] hover:text-white",
            n.pinned && "text-[var(--accent)]"
          )}
          aria-label="Pin"
        >
          <Pin size={14} className={n.pinned ? "fill-current" : ""} />
        </button>
      </div>
      {n.checklist && n.checklist.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {n.checklist.map((c, i) => (
            <li key={i} className="flex items-center gap-2 text-sm">
              <span
                className={cn(
                  "h-3.5 w-3.5 rounded-sm border",
                  c.checked
                    ? "bg-[var(--accent)] border-[var(--accent)]"
                    : "border-[var(--fg-mute)]"
                )}
              />
              <span className={c.checked ? "line-through text-[var(--fg-mute)]" : ""}>{c.text}</span>
            </li>
          ))}
        </ul>
      ) : n.body ? (
        <div className="mt-1 whitespace-pre-wrap break-words text-[var(--fg)]/95">{n.body}</div>
      ) : null}
      {n.labels && n.labels.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {n.labels.map((l) => (
            <span
              key={l}
              className="text-[11px] px-2 py-0.5 rounded-full bg-black/30 text-[var(--fg-mute)]"
            >
              {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function colorClass(c: string | undefined) {
  switch (c) {
    case "red":    return "bg-keep-red";
    case "orange": return "bg-keep-orange";
    case "yellow": return "bg-keep-yellow";
    case "green":  return "bg-keep-green";
    case "teal":   return "bg-keep-teal";
    case "blue":   return "bg-keep-blue";
    case "dblue":  return "bg-keep-dblue";
    case "purple": return "bg-keep-purple";
    case "pink":   return "bg-keep-pink";
    case "brown":  return "bg-keep-brown";
    case "gray":   return "bg-keep-gray";
    default:       return "bg-[var(--bg-elev)]";
  }
}
