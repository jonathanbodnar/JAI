"use client";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check, Plus, Loader2, ListTodo, StickyNote, ChevronRight } from "lucide-react";
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
      // surface the error via SWR revalidation
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (t: Task) => {
    const next: Task["status"] = t.status === "completed" ? "needsAction" : "completed";
    // Optimistic update
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
            <button
              key={t.id}
              onClick={() => toggle(t)}
              className="w-full flex items-start gap-2 px-2 py-1.5 rounded-md hover:bg-white/5 group text-left"
            >
              <span
                className={cn(
                  "mt-0.5 w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-all",
                  t.status === "completed"
                    ? "bg-emerald-500 border-emerald-500"
                    : "border-[#5a5d61] group-hover:border-[var(--accent)]",
                )}
              >
                {t.status === "completed" && <Check size={9} className="text-white" />}
              </span>
              <span
                className={cn(
                  "text-[13px] leading-snug flex-1 min-w-0 break-words",
                  t.status === "completed"
                    ? "line-through text-[#8e918f]"
                    : "text-[#e3e3e3]",
                )}
              >
                {t.title}
              </span>
            </button>
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

  const recent = (notes || [])
    .filter((n) => !n.archived)
    .sort((a, b) => {
      // Pinned first, then by updated_at desc.
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
          recent.map((n) => (
            <Link
              key={n.id}
              href={`/notes#${n.id}`}
              className="block px-2 py-1.5 rounded-md hover:bg-white/5 group"
            >
              {n.title && (
                <div className="text-[13px] font-medium text-white truncate flex items-center gap-1">
                  {n.pinned && <span className="text-amber-400 text-[10px]">●</span>}
                  {n.title}
                </div>
              )}
              {n.body && (
                <div className="text-[11.5px] text-[#8e918f] line-clamp-2 leading-snug mt-0.5">
                  {n.body}
                </div>
              )}
            </Link>
          ))
        )}
      </div>
    </>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-6 text-center text-[11px] text-[#5a5d61]">{children}</div>
  );
}
