"use client";
import { useState } from "react";
import useSWR from "swr";
import {
  Plus, Trash2, Play, Power, Clock, ChevronDown, ChevronUp, CheckCircle2,
  XCircle, AlertCircle, Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";

interface ScheduledAction {
  id: string;
  description: string;
  frequency: string;
  hour_utc: number;
  day_of_week: number | null;
  skill_id: string | null;
  builtin_name: string | null;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string;
  last_result: string | null;
  last_status: string | null;
  run_count: number;
  created_at: string;
}

const FREQ_LABELS: Record<string, string> = {
  hourly: "Every hour",
  daily: "Every day",
  weekdays: "Weekdays",
  weekly: "Every week",
  monthly: "Every month",
};

const DOW_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function formatHourUtc(h: number): string {
  // Show as approximate local time (CST = UTC-5 in winter, UTC-6 in summer)
  const localH = ((h - 5) + 24) % 24;
  const suffix = localH >= 12 ? "pm" : "am";
  const disp = localH % 12 || 12;
  return `~${disp}${suffix} local`;
}

function FreqBadge({ action }: { action: ScheduledAction }) {
  const label = FREQ_LABELS[action.frequency] ?? action.frequency;
  const dow = action.day_of_week !== null ? DOW_LABELS[action.day_of_week] : null;
  const time = formatHourUtc(action.hour_utc);
  return (
    <span className="text-xs text-[var(--fg-mute)] tabular-nums">
      {label}
      {dow ? ` · ${dow}s` : ""}
      {action.frequency !== "hourly" ? ` · ${time}` : ""}
    </span>
  );
}

function StatusDot({ status }: { status: string | null }) {
  if (!status) return <span className="w-2 h-2 rounded-full bg-[var(--fg-mute)/40] inline-block" />;
  if (status === "ok") return <CheckCircle2 size={14} className="text-emerald-400" />;
  if (status === "error") return <XCircle size={14} className="text-red-400" />;
  return <AlertCircle size={14} className="text-yellow-400" />;
}

// ---------------------------------------------------------------------------
// Create form
// ---------------------------------------------------------------------------
function CreateForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [desc, setDesc] = useState("");
  const [freq, setFreq] = useState("daily");
  const [hourUtc, setHourUtc] = useState(13);
  const [dow, setDow] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!desc.trim()) return;
    setSaving(true);
    setErr("");
    try {
      await api("/schedule", {
        method: "POST",
        body: JSON.stringify({
          description: desc.trim(),
          frequency: freq,
          hour_utc: hourUtc,
          day_of_week: freq === "weekly" ? (dow ?? 1) : null,
        }),
      });
      setDesc(""); setFreq("daily"); setHourUtc(13); setDow(null);
      setOpen(false);
      onCreated();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to create");
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-dashed border-[var(--line)] text-[var(--fg-mute)] hover:border-[var(--accent)] hover:text-white transition-colors w-full"
      >
        <Plus size={14} /> New automation
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="border border-[var(--accent)/40] rounded-xl p-4 space-y-3 bg-[var(--surface-raised)]">
      <input
        className="w-full bg-transparent text-sm border-b border-[var(--line)] pb-2 focus:outline-none focus:border-[var(--accent)] placeholder:text-[var(--fg-mute)]"
        placeholder="What should JAI do? e.g. 'Check Stripe payouts and summarize'"
        value={desc}
        onChange={e => setDesc(e.target.value)}
        autoFocus
      />
      <div className="flex flex-wrap gap-3 text-sm">
        <label className="flex items-center gap-1.5 text-[var(--fg-mute)]">
          <Clock size={12} /> Frequency
          <select
            value={freq}
            onChange={e => { setFreq(e.target.value); setDow(null); }}
            className="ml-1 bg-[var(--surface)] border border-[var(--line)] rounded px-2 py-0.5 text-white text-xs focus:outline-none"
          >
            {Object.entries(FREQ_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
        {freq === "weekly" && (
          <label className="flex items-center gap-1.5 text-[var(--fg-mute)]">
            Day
            <select
              value={dow ?? 1}
              onChange={e => setDow(Number(e.target.value))}
              className="ml-1 bg-[var(--surface)] border border-[var(--line)] rounded px-2 py-0.5 text-white text-xs focus:outline-none"
            >
              {DOW_LABELS.map((d, i) => <option key={i} value={i}>{d}</option>)}
            </select>
          </label>
        )}
        {freq !== "hourly" && (
          <label className="flex items-center gap-1.5 text-[var(--fg-mute)]">
            Time (UTC hour)
            <input
              type="number" min={0} max={23} value={hourUtc}
              onChange={e => setHourUtc(Number(e.target.value))}
              className="ml-1 w-14 bg-[var(--surface)] border border-[var(--line)] rounded px-2 py-0.5 text-white text-xs focus:outline-none"
            />
            <span className="text-[10px]">{formatHourUtc(hourUtc)}</span>
          </label>
        )}
      </div>
      {err && <p className="text-xs text-red-400">{err}</p>}
      <div className="flex gap-2 justify-end">
        <button type="button" onClick={() => setOpen(false)}
          className="px-3 py-1.5 text-xs text-[var(--fg-mute)] hover:text-white rounded-lg">
          Cancel
        </button>
        <button type="submit" disabled={saving || !desc.trim()}
          className="px-3 py-1.5 text-xs bg-[var(--accent)] text-black rounded-lg font-medium disabled:opacity-50 flex items-center gap-1">
          {saving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          {saving ? "Saving…" : "Create"}
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Single action row
// ---------------------------------------------------------------------------
function ActionRow({ action, onMutate }: { action: ScheduledAction; onMutate: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [running, setRunning] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function toggle() {
    setToggling(true);
    try {
      await api(`/schedule/${action.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !action.enabled }),
      });
      onMutate();
    } finally { setToggling(false); }
  }

  async function runNow() {
    setRunning(true);
    try {
      await api(`/schedule/${action.id}/run`, { method: "POST" });
      onMutate();
    } finally { setRunning(false); }
  }

  async function del() {
    if (!confirm(`Delete automation "${action.description}"?`)) return;
    setDeleting(true);
    try {
      await api(`/schedule/${action.id}`, { method: "DELETE" });
      onMutate();
    } finally { setDeleting(false); }
  }

  const nextRun = new Date(action.next_run_at);
  const lastRun = action.last_run_at ? new Date(action.last_run_at) : null;

  return (
    <div className={cn(
      "border border-[var(--line)] rounded-xl transition-all",
      !action.enabled && "opacity-50",
    )}>
      <div className="flex items-start gap-3 p-3">
        {/* Status icon */}
        <div className="mt-0.5 shrink-0">
          <StatusDot status={action.last_status} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className={cn("text-sm font-medium truncate", !action.enabled && "line-through")}>{action.description}</p>
          <FreqBadge action={action} />
          {action.run_count > 0 && (
            <span className="text-xs text-[var(--fg-mute)] ml-2">
              · ran {action.run_count}x
            </span>
          )}
          {lastRun && (
            <span className="text-xs text-[var(--fg-mute)] ml-2">
              · last {lastRun.toLocaleDateString()}
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={runNow} disabled={running} title="Run now"
            className="p-1.5 rounded hover:bg-white/5 text-[var(--fg-mute)] hover:text-white transition-colors disabled:opacity-50">
            {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          </button>
          <button onClick={toggle} disabled={toggling} title={action.enabled ? "Disable" : "Enable"}
            className={cn("p-1.5 rounded hover:bg-white/5 transition-colors disabled:opacity-50",
              action.enabled ? "text-emerald-400 hover:text-white" : "text-[var(--fg-mute)] hover:text-emerald-400")}>
            {toggling ? <Loader2 size={13} className="animate-spin" /> : <Power size={13} />}
          </button>
          <button onClick={del} disabled={deleting} title="Delete"
            className="p-1.5 rounded hover:bg-white/5 text-[var(--fg-mute)] hover:text-red-400 transition-colors disabled:opacity-50">
            {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
          </button>
          <button onClick={() => setExpanded(!expanded)} title="Details"
            className="p-1.5 rounded hover:bg-white/5 text-[var(--fg-mute)] hover:text-white transition-colors">
            {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 pb-3 text-xs text-[var(--fg-mute)] space-y-1 border-t border-[var(--line)] pt-2 mt-1">
          <p>Next run: <span className="text-white">{nextRun.toLocaleString()}</span></p>
          {lastRun && <p>Last run: <span className="text-white">{lastRun.toLocaleString()}</span></p>}
          {action.last_result && (
            <div>
              <p className="mb-1">Last result:</p>
              <pre className="whitespace-pre-wrap text-[10px] bg-[var(--surface)] rounded p-2 max-h-40 overflow-y-auto">
                {action.last_result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------
export function Automations() {
  const { data, isLoading, mutate } = useSWR<ScheduledAction[]>(
    "/schedule",
    async (url: string) => api(url),
    { revalidateOnFocus: false },
  );

  const actions = data ?? [];
  const active = actions.filter(a => a.enabled);
  const inactive = actions.filter(a => !a.enabled);

  return (
    <div className="p-4 space-y-4 max-w-2xl mx-auto">
      <div>
        <h2 className="text-sm font-semibold">Automations</h2>
        <p className="text-xs text-[var(--fg-mute)] mt-0.5">
          Recurring actions JAI runs for you on a schedule. The nightly
          consolidation job executes due automations and surfaces results
          in your morning briefing.
        </p>
      </div>

      <CreateForm onCreated={() => mutate()} />

      {isLoading && (
        <div className="flex justify-center py-8">
          <Loader2 size={20} className="animate-spin text-[var(--fg-mute)]" />
        </div>
      )}

      {!isLoading && actions.length === 0 && (
        <div className="text-center py-8 text-sm text-[var(--fg-mute)]">
          No automations yet. Create one above or ask JAI to
          &ldquo;remind me daily about…&rdquo;
        </div>
      )}

      {active.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xs text-[var(--fg-mute)] uppercase tracking-wider">Active</h3>
          {active.map(a => <ActionRow key={a.id} action={a} onMutate={() => mutate()} />)}
        </section>
      )}

      {inactive.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xs text-[var(--fg-mute)] uppercase tracking-wider">Paused</h3>
          {inactive.map(a => <ActionRow key={a.id} action={a} onMutate={() => mutate()} />)}
        </section>
      )}
    </div>
  );
}
