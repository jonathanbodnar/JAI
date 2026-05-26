"use client";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Check, Plus, ChevronDown, CheckCircle2, ListTodo, ClipboardList, Loader2, Trash2 } from "lucide-react";
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

  const { data: tasks, isLoading } = useSWR<Task[]>(
    listId ? `/tasks?list_id=${listId}` : null,
    (k: string) => api(k),
  );

  const active = (tasks || []).filter((t) => t.status !== "completed");
  const done = (tasks || []).filter((t) => t.status === "completed");
  const current = lists?.find((l) => l.id === listId);

  return (
    <div className="flex flex-col h-full bg-[#131314] select-none text-[#ececef]">
      {/* Header */}
      <header className="header-safe-pt px-6 pb-4 flex items-center justify-between border-b border-[#2d2f31] bg-[#131314]/80 backdrop-blur-xl z-20 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-tr from-[#3b82f6] to-[#10b981] shadow-[0_0_15px_rgba(59,130,246,0.3)]">
            <ListTodo size={18} className="text-white" />
          </div>
          <button className="flex items-center gap-1.5 text-base font-bold tracking-tight text-white hover:text-zinc-200 transition-colors">
            {current?.title || "My Tasks"}
            <ChevronDown size={14} className="text-[#8e918f]" />
          </button>
        </div>
        <div className="text-xs text-[#8e918f] font-medium bg-[#1e1f20] px-2.5 py-1 rounded-full border border-[#2d2f31]">
          {active.length} open
        </div>
      </header>

      {/* Task Content */}
      <div className="flex-1 overflow-y-auto pb-28">
        <div className="max-w-2xl mx-auto px-4 py-4 space-y-5">
          {listId && (
            <NewTaskInput listId={listId} onCreated={() => mutate(`/tasks?list_id=${listId}`)} />
          )}

          {isLoading && (
            <div className="flex justify-center py-12">
              <Loader2 size={24} className="animate-spin text-[#8e918f]" />
            </div>
          )}

          {!isLoading && (
            <div className="space-y-4">
              {active.length > 0 && (
                <div className="bg-[#1e1f20] border border-[#2d2f31] rounded-2xl p-1 shadow-sm space-y-0.5">
                  {active.map((t) => (
                    <TaskItem
                      key={t.id}
                      t={t}
                      onChange={() => mutate(`/tasks?list_id=${listId}`)}
                    />
                  ))}
                </div>
              )}

              {done.length > 0 && (
                <div className="space-y-2">
                  <div className="px-1 text-xs font-bold uppercase tracking-wider text-[#8e918f] flex items-center gap-1.5">
                    <CheckCircle2 size={12} className="text-emerald-400" />
                    Completed ({done.length})
                  </div>
                  <div className="bg-[#1e1f20]/50 border border-[#2d2f31]/60 rounded-2xl p-1 shadow-sm space-y-0.5 opacity-75">
                    {done.map((t) => (
                      <TaskItem
                        key={t.id}
                        t={t}
                        onChange={() => mutate(`/tasks?list_id=${listId}`)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {!tasks || tasks.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 py-16 text-center text-sm text-[#8e918f] max-w-sm mx-auto">
                  <ClipboardList size={36} className="text-[#3c3d3f]" />
                  <p className="font-semibold text-zinc-300">All caught up!</p>
                  <p className="text-xs leading-normal">
                    Tell JAI: &ldquo;remind me to ship the new pricing page tomorrow.&rdquo; to capture it instantly.
                  </p>
                </div>
              ) : null}
            </div>
          )}
        </div>
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
        className="flex items-center gap-2.5 px-5 py-3.5 rounded-2xl border border-dashed border-[#2d2f31] text-[var(--accent)] text-sm font-semibold hover:border-[var(--accent)]/50 hover:bg-[#1e1f20]/30 transition-all w-full select-none"
      >
        <span className="h-6 w-6 rounded-full bg-[var(--accent)]/10 flex items-center justify-center">
          <Plus size={14} strokeWidth={2.5} />
        </span>
        Add a task
      </button>
    );
  }
  return (
    <div className="px-5 py-3.5 rounded-2xl bg-[#1e1f20] border border-[var(--accent)]/30 flex items-center gap-3 shadow-inner">
      <span className="h-5 w-5 rounded-full border border-[#8e918f]/50 shrink-0" />
      <input
        autoFocus
        value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        onBlur={() => v.trim() ? submit() : setOpen(false)}
        placeholder="e.g. Ship pricing page tomorrow"
        className="flex-1 bg-transparent outline-none text-[15px] text-[#e3e3e3] placeholder-[#8e918f]"
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

  const removeTask = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete task "${t.title}"?`)) return;
    setBusy(true);
    await api(`/tasks/${t.id}`, { method: "DELETE" });
    setBusy(false);
    onChange();
  };

  const isDone = t.status === "completed";

  return (
    <div className="group rounded-xl hover:bg-[#2d2f31]/30 transition-colors duration-150">
      <div className="px-4 py-3 flex items-start gap-3.5 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <button
          onClick={(e) => { e.stopPropagation(); void toggle(); }}
          disabled={busy}
          className={cn(
            "mt-0.5 h-5 w-5 rounded-full border-1.5 flex items-center justify-center shrink-0 transition-all duration-150",
            isDone
              ? "bg-[#34d399] border-[#34d399] text-black scale-105"
              : "border-[#8e918f] hover:border-[var(--accent)]"
          )}
          aria-label={isDone ? "Mark incomplete" : "Mark complete"}
        >
          {isDone && <Check size={11} strokeWidth={4} className="text-[#0e0e11]" />}
        </button>
        <div className="flex-1 min-w-0">
          <p
            className={cn(
              "text-[14.5px] font-medium truncate tracking-tight transition-all duration-150",
              isDone ? "line-through text-[#8e918f]" : "text-[#e3e3e3]"
            )}
          >
            {t.title}
          </p>
          {t.due && (
            <div className="text-xs text-[#8e918f] mt-0.5 font-medium flex items-center gap-1">
              {new Date(t.due).toLocaleString(undefined, {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}
            </div>
          )}
        </div>

        {/* Delete task button shown on hover */}
        <button
          onClick={removeTask}
          disabled={busy}
          className="p-1 rounded text-[#8e918f] hover:text-[#f2b8b5] opacity-0 group-hover:opacity-100 transition-opacity"
          title="Delete task"
        >
          <Trash2 size={13} />
        </button>
      </div>

      {expanded && (t.notes || true) && (
        <div className="px-12 pb-3.5 text-xs font-medium text-[#8e918f] whitespace-pre-wrap leading-relaxed">
          {t.notes || <span className="italic opacity-50">No notes attached</span>}
        </div>
      )}
    </div>
  );
}
