"use client";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Archive,
  Check,
  ChevronRight,
  ListTodo,
  Loader2,
  Pin,
  PinOff,
  Plus,
  StickyNote,
  Trash2,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useRealtimeRevalidate } from "@/lib/realtime";
import { cn } from "@/lib/cn";

type TaskList = { id: string; title: string };
type Task = {
  id: string;
  title: string;
  status: "needsAction" | "completed";
  due?: string | null;
};
type Note = {
  id: string;
  title?: string | null;
  body?: string | null;
  pinned?: boolean;
  archived?: boolean;
  updated_at: string;
};

/**
 * Desktop-only right rail with quick access to tasks (top) + notes
 * (bottom). Lives next to the main chat surface so the user can capture
 * something without leaving the conversation. Hidden under `lg:` so
 * tablet portrait doesn't feel cramped.
 */
export function RightPanel() {
  const pathname = usePathname() || "";
  // Skip on the full-screen Tasks/Notes pages (would be redundant),
  // also skip on settings / graph / context flows where the rail's
  // capture surface would just be visual noise.
  const hidden =
    pathname.startsWith("/tasks") ||
    pathname.startsWith("/notes") ||
    pathname.startsWith("/settings") ||
    pathname.startsWith("/graph") ||
    pathname.startsWith("/context") ||
    pathname.startsWith("/onboarding") ||
    pathname.startsWith("/login");
  if (hidden) return null;
  return (
    <aside className="hidden lg:flex w-[320px] xl:w-[360px] shrink-0 border-l border-[#2d2f31] bg-[#181818] flex-col">
      <div className="flex-[1.1] min-h-0 flex flex-col border-b border-[#2d2f31]">
        <QuickTasks />
      </div>
      <div className="flex-1 min-h-0 flex flex-col">
        <QuickNotes />
      </div>
    </aside>
  );
}

function QuickTasks() {
  const { data: lists } = useSWR<TaskList[]>("/tasks/lists", (k: string) => api(k));
  const [listId, setListId] = useState<string | null>(null);
  useEffect(() => {
    if (!listId && lists?.length) setListId(lists[0].id);
  }, [lists, listId]);

  const { data: tasks, isLoading } = useSWR<Task[]>(
    listId ? `/tasks?list_id=${listId}` : null,
    (k: string) => api(k),
  );
  useRealtimeRevalidate("tasks", "/tasks");

  const { mutate } = useSWRConfig();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const open = (tasks || []).filter((t) => t.status !== "completed").slice(0, 12);

  const add = async () => {
    const title = draft.trim();
    if (!title || !listId) return;
    setBusy(true);
    try {
      await api("/tasks", {
        method: "POST",
        body: JSON.stringify({ list_id: listId, title }),
      });
      setDraft("");
      mutate(`/tasks?list_id=${listId}`);
    } catch {
      // Errors propagate via SWR revalidation; no toast needed in the rail.
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (t: Task) => {
    const next: Task["status"] = t.status === "completed" ? "needsAction" : "completed";
    mutate(
      `/tasks?list_id=${listId}`,
      (cur: Task[] = []) => cur.map((x) => (x.id === t.id ? { ...x, status: next } : x)),
      false,
    );
    try {
      await api(`/tasks/${t.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: next }),
      });
    } finally {
      mutate(`/tasks?list_id=${listId}`);
    }
  };

  const remove = async (t: Task) => {
    mutate(
      `/tasks?list_id=${listId}`,
      (cur: Task[] = []) => cur.filter((x) => x.id !== t.id),
      false,
    );
    try {
      await api(`/tasks/${t.id}`, { method: "DELETE" });
    } finally {
      mutate(`/tasks?list_id=${listId}`);
    }
  };

  const saveRename = async (id: string) => {
    const title = editTitle.trim();
    setEditingId(null);
    if (!title) return;
    mutate(
      `/tasks?list_id=${listId}`,
      (cur: Task[] = []) => cur.map((x) => (x.id === id ? { ...x, title } : x)),
      false,
    );
    try {
      await api(`/tasks/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
    } finally {
      mutate(`/tasks?list_id=${listId}`);
    }
  };

  return (
    <>
      <div className="px-3 pt-3 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-gradient-to-tr from-[#3b82f6] to-[#10b981] flex items-center justify-center">
            <ListTodo size={13} className="text-white" />
          </div>
          <span className="text-[12px] font-semibold uppercase tracking-wider text-[#8e918f]">
            Tasks
          </span>
          {open.length > 0 && (
            <span className="text-[10px] text-[#8e918f] font-mono">{open.length}</span>
          )}
        </div>
        <Link
          href="/tasks"
          className="text-[11px] text-[#8e918f] hover:text-white flex items-center gap-0.5"
          title="Open tasks"
        >
          All <ChevronRight size={11} />
        </Link>
      </div>

      <div className="px-3 pb-2">
        <div className="flex items-center gap-2 rounded-lg bg-[#1f2021] border border-[#2d2f31] px-2 focus-within:border-[var(--accent)] transition-colors">
          <Plus size={14} className="text-[#8e918f] shrink-0" />
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void add();
            }}
            placeholder="Add a task…"
            className="flex-1 bg-transparent outline-none py-2 text-[13px] placeholder-[#8e918f] text-white"
          />
          {busy && <Loader2 size={13} className="text-[#8e918f] animate-spin" />}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {isLoading ? (
          <Empty>Loading…</Empty>
        ) : open.length === 0 ? (
          <Empty>Inbox zero. Nothing on the list.</Empty>
        ) : (
          open.map((t) => (
            <div
              key={t.id}
              className="group/row flex items-start gap-2 px-2 py-1.5 rounded-md hover:bg-white/5"
            >
              <button
                type="button"
                onClick={() => toggle(t)}
                aria-label={t.status === "completed" ? "Mark incomplete" : "Mark complete"}
                className={cn(
                  "mt-0.5 w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-all",
                  t.status === "completed"
                    ? "bg-emerald-500 border-emerald-500"
                    : "border-[#5a5d61] hover:border-[var(--accent)]",
                )}
              >
                {t.status === "completed" && <Check size={9} className="text-white" />}
              </button>

              {editingId === t.id ? (
                <input
                  autoFocus
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => void saveRename(t.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void saveRename(t.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  className="flex-1 bg-transparent outline-none text-[13px] text-[#e3e3e3] border-b border-[var(--accent)]/40"
                />
              ) : (
                <button
                  type="button"
                  onDoubleClick={() => {
                    setEditingId(t.id);
                    setEditTitle(t.title);
                  }}
                  onClick={() => toggle(t)}
                  className="text-left flex-1 min-w-0"
                  title="Double-click to rename"
                >
                  <span
                    className={cn(
                      "text-[13px] leading-snug break-words",
                      t.status === "completed"
                        ? "line-through text-[#8e918f]"
                        : "text-[#e3e3e3]",
                    )}
                  >
                    {t.title}
                  </span>
                </button>
              )}

              <button
                type="button"
                onClick={() => void remove(t)}
                title="Delete task"
                className="opacity-0 group-hover/row:opacity-100 transition-opacity p-1 rounded hover:bg-white/5 text-[#8e918f] hover:text-red-400"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>
    </>
  );
}

function QuickNotes() {
  const { data: notes, isLoading } = useSWR<Note[]>("/notes", (k: string) => api(k));
  useRealtimeRevalidate("notes", "/notes");
  const { mutate } = useSWRConfig();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const recent = (notes || [])
    .filter((n) => !n.archived)
    .sort((a, b) => {
      if ((a.pinned ? 1 : 0) !== (b.pinned ? 1 : 0)) {
        return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
      }
      return (b.updated_at || "").localeCompare(a.updated_at || "");
    })
    .slice(0, 8);

  const add = async () => {
    const body = draft.trim();
    if (!body) return;
    setBusy(true);
    try {
      await api("/notes", {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      setDraft("");
      mutate("/notes");
    } finally {
      setBusy(false);
    }
  };

  const patch = async (id: string, patchBody: Partial<Note>) => {
    // Optimistic update so the UI reflects pin/archive/edit immediately.
    mutate(
      "/notes",
      (cur: Note[] = []) =>
        cur.map((n) => (n.id === id ? { ...n, ...patchBody } : n)),
      false,
    );
    try {
      await api(`/notes/${id}`, {
        method: "PATCH",
        body: JSON.stringify(patchBody),
      });
    } finally {
      mutate("/notes");
    }
  };

  const remove = async (id: string) => {
    setEditingId(null);
    mutate(
      "/notes",
      (cur: Note[] = []) => cur.filter((n) => n.id !== id),
      false,
    );
    try {
      await api(`/notes/${id}`, { method: "DELETE" });
    } finally {
      mutate("/notes");
    }
  };

  return (
    <>
      <div className="px-3 pt-3 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-gradient-to-tr from-[#ec4899] to-[#8b5cf6] flex items-center justify-center">
            <StickyNote size={13} className="text-white" />
          </div>
          <span className="text-[12px] font-semibold uppercase tracking-wider text-[#8e918f]">
            Notes
          </span>
          {recent.length > 0 && (
            <span className="text-[10px] text-[#8e918f] font-mono">{recent.length}</span>
          )}
        </div>
        <Link
          href="/notes"
          className="text-[11px] text-[#8e918f] hover:text-white flex items-center gap-0.5"
          title="Open notes"
        >
          All <ChevronRight size={11} />
        </Link>
      </div>

      <div className="px-3 pb-2">
        <div className="flex items-center gap-2 rounded-lg bg-[#1f2021] border border-[#2d2f31] px-2 focus-within:border-[var(--accent)] transition-colors">
          <Plus size={14} className="text-[#8e918f] shrink-0" />
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void add();
            }}
            placeholder="Quick note…"
            className="flex-1 bg-transparent outline-none py-2 text-[13px] placeholder-[#8e918f] text-white"
          />
          {busy && <Loader2 size={13} className="text-[#8e918f] animate-spin" />}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-1">
        {isLoading ? (
          <Empty>Loading…</Empty>
        ) : recent.length === 0 ? (
          <Empty>No notes yet.</Empty>
        ) : (
          recent.map((n) =>
            editingId === n.id ? (
              <NoteEditor
                key={n.id}
                note={n}
                onClose={() => setEditingId(null)}
                onPatch={(body) => patch(n.id, body)}
                onDelete={() => remove(n.id)}
              />
            ) : (
              <NoteRow
                key={n.id}
                note={n}
                onOpen={() => setEditingId(n.id)}
                onTogglePin={() => patch(n.id, { pinned: !n.pinned })}
                onArchive={() => patch(n.id, { archived: true })}
                onDelete={() => remove(n.id)}
              />
            ),
          )
        )}
      </div>
    </>
  );
}

function NoteRow({
  note,
  onOpen,
  onTogglePin,
  onArchive,
  onDelete,
}: {
  note: Note;
  onOpen: () => void;
  onTogglePin: () => void;
  onArchive: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="group/note relative rounded-md hover:bg-white/5">
      <button
        type="button"
        onClick={onOpen}
        className="w-full text-left px-2 py-1.5 block"
      >
        {note.title && (
          <div className="text-[13px] font-medium text-white truncate flex items-center gap-1 pr-16">
            {note.pinned && <span className="text-amber-400 text-[10px]">●</span>}
            {note.title}
          </div>
        )}
        {note.body && (
          <div className="text-[11.5px] text-[#8e918f] line-clamp-2 leading-snug mt-0.5 pr-16">
            {note.body}
          </div>
        )}
        {!note.title && !note.body && (
          <div className="text-[11.5px] text-[#5a5d61] italic">Empty note</div>
        )}
      </button>
      <div className="absolute right-1 top-1 flex items-center gap-0.5 opacity-0 group-hover/note:opacity-100 transition-opacity bg-[#181818]/80 backdrop-blur-sm rounded-md">
        <IconBtn
          icon={note.pinned ? PinOff : Pin}
          title={note.pinned ? "Unpin" : "Pin"}
          onClick={(e) => {
            e.stopPropagation();
            onTogglePin();
          }}
          highlight={note.pinned}
        />
        <IconBtn
          icon={Archive}
          title="Archive"
          onClick={(e) => {
            e.stopPropagation();
            onArchive();
          }}
        />
        <IconBtn
          icon={Trash2}
          title="Delete"
          danger
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        />
      </div>
    </div>
  );
}

function NoteEditor({
  note,
  onClose,
  onPatch,
  onDelete,
}: {
  note: Note;
  onClose: () => void;
  onPatch: (body: Partial<Note>) => Promise<void> | void;
  onDelete: () => void;
}) {
  const [title, setTitle] = useState(note.title || "");
  const [body, setBody] = useState(note.body || "");
  const [pinned, setPinned] = useState(!!note.pinned);
  const containerRef = useRef<HTMLDivElement>(null);
  const dirtyRef = useRef(false);
  const savingRef = useRef<NodeJS.Timeout | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the body textarea so the user sees the full note while
  // typing, mirroring Keep's behaviour.
  useEffect(() => {
    const ta = bodyRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = `${Math.min(ta.scrollHeight, 320)}px`;
  }, [body]);

  // Click outside collapses the editor (and flushes a save if dirty).
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        flush();
        onClose();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const queueSave = (next: Partial<Note>) => {
    dirtyRef.current = true;
    if (savingRef.current) clearTimeout(savingRef.current);
    savingRef.current = setTimeout(() => {
      void onPatch(next);
      dirtyRef.current = false;
    }, 600);
  };

  const flush = () => {
    if (!dirtyRef.current) return;
    if (savingRef.current) clearTimeout(savingRef.current);
    void onPatch({ title: title || null, body: body || null });
    dirtyRef.current = false;
  };

  const togglePin = () => {
    const next = !pinned;
    setPinned(next);
    void onPatch({ pinned: next });
  };

  return (
    <div
      ref={containerRef}
      className="rounded-lg bg-[#1f2021] border border-[#3b3d3f] shadow-lg shadow-black/30 p-2"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          flush();
          onClose();
        }
      }}
    >
      <input
        value={title}
        onChange={(e) => {
          setTitle(e.target.value);
          queueSave({ title: e.target.value || null, body: body || null });
        }}
        placeholder="Title"
        className="w-full bg-transparent outline-none text-[13px] font-medium text-white placeholder-[#5a5d61] pb-1"
      />
      <textarea
        ref={bodyRef}
        value={body}
        autoFocus={!title}
        onChange={(e) => {
          setBody(e.target.value);
          queueSave({ title: title || null, body: e.target.value || null });
        }}
        placeholder="Take a note…"
        rows={3}
        className="w-full bg-transparent outline-none text-[12.5px] text-[#e3e3e3] placeholder-[#5a5d61] resize-none leading-snug"
      />
      <div className="flex items-center gap-0.5 pt-1 -mx-1">
        <IconBtn
          icon={pinned ? PinOff : Pin}
          title={pinned ? "Unpin" : "Pin"}
          onClick={togglePin}
          highlight={pinned}
        />
        <IconBtn
          icon={Archive}
          title="Archive"
          onClick={() => {
            flush();
            void onPatch({ archived: true });
            onClose();
          }}
        />
        <IconBtn
          icon={Trash2}
          title="Delete"
          danger
          onClick={onDelete}
        />
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => {
            flush();
            onClose();
          }}
          className="text-[11.5px] px-2 py-1 rounded text-[#8e918f] hover:text-white hover:bg-white/5 inline-flex items-center gap-1"
          title="Close (esc)"
        >
          <X size={11} /> Close
        </button>
      </div>
    </div>
  );
}

function IconBtn({
  icon: Icon,
  title,
  onClick,
  highlight,
  danger,
}: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  onClick: (e: React.MouseEvent) => void;
  highlight?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "p-1.5 rounded transition-colors",
        highlight
          ? "text-amber-300 hover:bg-amber-400/10"
          : danger
          ? "text-[#8e918f] hover:text-red-400 hover:bg-red-500/10"
          : "text-[#8e918f] hover:text-white hover:bg-white/5",
      )}
    >
      <Icon size={13} />
    </button>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-6 text-center text-[11px] text-[#5a5d61]">{children}</div>
  );
}
