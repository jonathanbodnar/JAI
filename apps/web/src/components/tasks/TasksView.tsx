"use client";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Check, Plus, ChevronDown, MoreVertical } from "lucide-react";
import { cn } from "@/lib/cn";
import { useRealtimeRevalidate } from "@/lib/realtime";

type TaskList = { id: string; title: string };
type Task = {
  id: string;
  title: string;
  notes?: string | null;
  status: "needsAction" | "completed";
  due?: string | null;
};

export function TasksView() {
  const { data: lists } = useSWR<TaskList[]>("/tasks/lists", (k: string) => api(k));
  const [listId, setListId] = useState<string | null>(null);
  const { mutate } = useSWRConfig();

  useRealtimeRevalidate("tasks", "/tasks");
  useRealtimeRevalidate("task_lists", "/tasks/lists");

  useEffect(() => {
    if (!listId && lists && lists.length) setListId(lists[0].id);
  }, [lists, listId]);

  const { data: tasks } = useSWR<Task[]>(
    listId ? `/tasks?list_id=${listId}` : null,
    (k: string) => api(k),
  );

  const active = (tasks || []).filter((t) => t.status !== "completed");
  const done = (tasks || []).filter((t) => t.status === "completed");
  const current = lists?.find((l) => l.id === listId);

  return (
    <div className="flex flex-col h-full">
      <header className="safe-top px-4 py-3 flex items-center justify-between border-b border-[var(--line)]">
        <button className="flex items-center gap-2 text-base font-semibold tracking-tight">
          {current?.title || "My Tasks"} <ChevronDown size={16} className="text-[var(--fg-mute)]" />
        </button>
        <button className="p-2 text-[var(--fg-mute)]" aria-label="More">
          <MoreVertical size={18} />
        </button>
      </header>

      {listId && (
        <NewTaskInput listId={listId} onCreated={() => mutate(`/tasks?list_id=${listId}`)} />
      )}

      <div className="flex-1 overflow-y-auto">
        <ul>
          {active.map((t) => (
            <TaskItem
              key={t.id}
              t={t}
              onChange={() => mutate(`/tasks?list_id=${listId}`)}
            />
          ))}
        </ul>

        {done.length > 0 && (
          <div className="mt-4">
            <div className="px-4 py-2 text-xs uppercase tracking-wider text-[var(--fg-mute)]">
              Completed ({done.length})
            </div>
            <ul>
              {done.map((t) => (
                <TaskItem
                  key={t.id}
                  t={t}
                  onChange={() => mutate(`/tasks?list_id=${listId}`)}
                />
              ))}
            </ul>
          </div>
        )}

        {(!tasks || tasks.length === 0) && (
          <div className="px-6 py-16 text-center text-sm text-[var(--fg-mute)]">
            No tasks yet. Tell JAI: &ldquo;remind me to ship the new pricing page tomorrow.&rdquo;
          </div>
        )}
      </div>
    </div>
  );
}

function NewTaskInput({ listId, onCreated }: { listId: string; onCreated: () => void }) {
  const [v, setV] = useState("");
  const [open, setOpen] = useState(false);
  const submit = async () => {
    const t = v.trim();
    if (!t) return;
    setV("");
    setOpen(false);
    await api("/tasks", {
      method: "POST",
      body: JSON.stringify({ list_id: listId, title: t }),
    });
    onCreated();
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="m-3 flex items-center gap-3 text-[var(--accent)] text-sm"
      >
        <span className="h-7 w-7 rounded-full bg-[var(--accent)]/15 flex items-center justify-center">
          <Plus size={16} />
        </span>
        Add a task
      </button>
    );
  }
  return (
    <div className="px-4 py-3 border-b border-[var(--line)] flex items-center gap-3">
      <span className="h-5 w-5 rounded-full border-2 border-[var(--fg-mute)]" />
      <input
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        onBlur={() => v.trim() ? submit() : setOpen(false)}
        placeholder="New task"
        className="flex-1 bg-transparent outline-none text-[15px]"
      />
    </div>
  );
}

function TaskItem({ t, onChange }: { t: Task; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const toggle = async () => {
    setBusy(true);
    await api(`/tasks/${t.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        status: t.status === "completed" ? "needsAction" : "completed",
      }),
    });
    setBusy(false);
    onChange();
  };
  const isDone = t.status === "completed";
  return (
    <li className="border-b border-[var(--line)]/70">
      <div className="px-4 py-3 flex items-start gap-3">
        <button
          onClick={toggle}
          disabled={busy}
          className={cn(
            "mt-0.5 h-5 w-5 rounded-full border-2 flex items-center justify-center shrink-0",
            isDone
              ? "bg-[var(--accent)] border-[var(--accent)] text-white"
              : "border-[var(--fg-mute)]"
          )}
        >
          {isDone && <Check size={12} strokeWidth={3} />}
        </button>
        <button
          onClick={() => setExpanded((v) => !v)}
          className={cn(
            "flex-1 text-left text-[15px]",
            isDone && "line-through text-[var(--fg-mute)]"
          )}
        >
          {t.title}
          {t.due && (
            <div className="text-xs text-[var(--fg-mute)] mt-0.5">
              {new Date(t.due).toLocaleString(undefined, {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}
            </div>
          )}
        </button>
      </div>
      {expanded && (t.notes || true) && (
        <div className="px-12 pb-3 text-sm text-[var(--fg-mute)] whitespace-pre-wrap">
          {t.notes || <span className="italic opacity-60">No notes</span>}
        </div>
      )}
    </li>
  );
}
