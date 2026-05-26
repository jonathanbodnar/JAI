"use client";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ArrowDownRight, ArrowUpRight, BrainCircuit, Pencil, Plus, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import { useRealtimeRevalidate } from "@/lib/realtime";
import { cn } from "@/lib/cn";

type Kpi = {
  id: string;
  key: string;
  label: string;
  value: string;
  previous?: string | null;
  format: "raw" | "number" | "currency" | "percent" | "duration";
  unit?: string | null;
  icon?: string | null;
  color?: string | null;
  source?: string;
  sort_order: number;
  is_visible: boolean;
  history?: { value: string; at: string }[];
  last_updated_at: string;
};

/**
 * The header strip used to be a static logo + model badge. Replaced
 * with a row of "living" KPI pills the user (or skills) can pin —
 * MRR, active users, weight, build minutes, anything numeric.
 *
 * Updates flow:
 *   - Manual edit in this UI → PATCH /kpis/{id}
 *   - Skill writes to the `kpis` table directly via the auto-injected
 *     Supabase service-role creds (see SKILL_BUILDER prompt)
 *   - Supabase Realtime pushes the change here and SWR revalidates
 */
export function LivingKPIs() {
  const { data: kpis } = useSWR<Kpi[]>("/kpis", (k: string) => api(k));
  useRealtimeRevalidate("kpis", "/kpis");
  const { mutate } = useSWRConfig();
  const [composing, setComposing] = useState(false);

  const visible = (kpis || []).slice(0, 8);

  const create = async (payload: Partial<Kpi>) => {
    setComposing(false);
    if (!payload.label || !payload.value) return;
    await api("/kpis", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    mutate("/kpis");
  };

  // Empty-state still keeps the JAI mark visible so the header doesn't
  // look broken before the user has pinned anything.
  if (!visible.length) {
    return (
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-tr from-[#7c5cff] via-[#9b76ff] to-[#f43f5e] shadow-[0_0_15px_rgba(124,92,255,0.3)] shrink-0">
          <BrainCircuit size={18} className="text-white" />
        </div>
        <button
          type="button"
          onClick={() => setComposing(true)}
          className="text-[12.5px] text-[#8e918f] hover:text-white px-2 py-1 rounded-md border border-dashed border-[#2d2f31] hover:border-[var(--accent)] inline-flex items-center gap-1.5"
        >
          <Plus size={12} /> Pin a KPI
        </button>
        {composing && (
          <KpiEditor mode="create" onSubmit={create} onCancel={() => setComposing(false)} />
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 min-w-0 flex-1">
      <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-tr from-[#7c5cff] via-[#9b76ff] to-[#f43f5e] shrink-0">
        <BrainCircuit size={18} className="text-white" />
      </div>
      <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar -mx-1 px-1 min-w-0">
        {visible.map((k) => (
          <KpiPill key={k.id} kpi={k} />
        ))}
        <button
          type="button"
          onClick={() => setComposing(true)}
          className="shrink-0 text-[#8e918f] hover:text-white p-1.5 rounded-md hover:bg-white/5 border border-dashed border-[#2d2f31] hover:border-[var(--accent)]"
          title="Pin a new KPI"
        >
          <Plus size={13} />
        </button>
      </div>
      {composing && (
        <KpiEditor mode="create" onSubmit={create} onCancel={() => setComposing(false)} />
      )}
    </div>
  );
}

function KpiPill({ kpi }: { kpi: Kpi }) {
  const { mutate } = useSWRConfig();
  const [editing, setEditing] = useState(false);

  const trend = computeTrend(kpi);

  const onUpdate = async (patch: Partial<Kpi>) => {
    setEditing(false);
    mutate(
      "/kpis",
      (cur: Kpi[] = []) => cur.map((x) => (x.id === kpi.id ? { ...x, ...patch } : x)),
      false,
    );
    try {
      await api(`/kpis/${kpi.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
    } finally {
      mutate("/kpis");
    }
  };

  const onDelete = async () => {
    setEditing(false);
    mutate("/kpis", (cur: Kpi[] = []) => cur.filter((x) => x.id !== kpi.id), false);
    try {
      await api(`/kpis/${kpi.id}`, { method: "DELETE" });
    } finally {
      mutate("/kpis");
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="shrink-0 group flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#1e1f20] border border-[#2d2f31] hover:border-[#3b3d3f] transition-colors max-w-[200px]"
        title={`${kpi.label} — last updated ${new Date(kpi.last_updated_at).toLocaleString()}${kpi.source ? `\nSource: ${kpi.source}` : ""}`}
      >
        <span className="text-[10.5px] uppercase tracking-wider font-semibold text-[#8e918f] truncate">
          {kpi.label}
        </span>
        <span className="text-[13px] font-bold text-white tabular-nums truncate">
          {formatValue(kpi)}
        </span>
        {trend && (
          <span
            className={cn(
              "inline-flex items-center text-[10px] font-medium tabular-nums shrink-0",
              trend.dir === "up" ? "text-emerald-400" : "text-rose-400",
            )}
          >
            {trend.dir === "up" ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
            {trend.label}
          </span>
        )}
      </button>
      {editing && (
        <KpiEditor
          mode="edit"
          initial={kpi}
          onSubmit={onUpdate}
          onCancel={() => setEditing(false)}
          onDelete={onDelete}
        />
      )}
    </>
  );
}

function KpiEditor({
  mode,
  initial,
  onSubmit,
  onCancel,
  onDelete,
}: {
  mode: "create" | "edit";
  initial?: Kpi;
  onSubmit: (patch: Partial<Kpi>) => void;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const [label, setLabel] = useState(initial?.label || "");
  const [value, setValue] = useState(initial?.value || "");
  const [format, setFormat] = useState<Kpi["format"]>(initial?.format || "raw");
  const [unit, setUnit] = useState(initial?.unit || "");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onCancel();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onCancel]);

  const submit = () => {
    if (!label.trim() || !value.trim()) {
      onCancel();
      return;
    }
    const payload: Partial<Kpi> = {
      label: label.trim(),
      value: value.trim(),
      format,
      unit: unit.trim() || null,
    };
    onSubmit(payload);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/40 backdrop-blur-sm" onMouseDown={(e) => e.stopPropagation()}>
      <div
        ref={ref}
        className="w-[360px] rounded-xl bg-[#1f2021] border border-[#2d2f31] shadow-2xl p-4 space-y-3"
        onKeyDown={(e) => {
          if (e.key === "Escape") onCancel();
          if (e.key === "Enter" && !e.shiftKey) submit();
        }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-white">
            {mode === "create" ? <Plus size={14} /> : <Pencil size={14} />}
            {mode === "create" ? "Pin a KPI" : "Edit KPI"}
          </div>
          <button onClick={onCancel} className="text-[#8e918f] hover:text-white" type="button">
            <X size={14} />
          </button>
        </div>

        <div className="space-y-2">
          <label className="block text-[10.5px] uppercase tracking-wider text-[#8e918f]">Label</label>
          <input
            autoFocus
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. MRR, Active users, Sleep score"
            className="w-full bg-[#131314] border border-[#2d2f31] focus:border-[var(--accent)] rounded-lg px-3 py-2 text-[13px] text-white outline-none placeholder-[#5a5d61]"
          />
        </div>

        <div className="space-y-2">
          <label className="block text-[10.5px] uppercase tracking-wider text-[#8e918f]">Value</label>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder='e.g. "$48,250", "12.4%", "324"'
            className="w-full bg-[#131314] border border-[#2d2f31] focus:border-[var(--accent)] rounded-lg px-3 py-2 text-[13px] text-white outline-none placeholder-[#5a5d61] tabular-nums"
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <label className="block text-[10.5px] uppercase tracking-wider text-[#8e918f]">Format</label>
            <select
              value={format}
              onChange={(e) => setFormat(e.target.value as Kpi["format"])}
              className="w-full bg-[#131314] border border-[#2d2f31] focus:border-[var(--accent)] rounded-lg px-2.5 py-2 text-[13px] text-white outline-none"
            >
              <option value="raw">Raw</option>
              <option value="number">Number</option>
              <option value="currency">Currency</option>
              <option value="percent">Percent</option>
              <option value="duration">Duration</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="block text-[10.5px] uppercase tracking-wider text-[#8e918f]">Unit</label>
            <input
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              placeholder="users / hrs / lbs"
              className="w-full bg-[#131314] border border-[#2d2f31] focus:border-[var(--accent)] rounded-lg px-2.5 py-2 text-[13px] text-white outline-none placeholder-[#5a5d61]"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 pt-2">
          {mode === "edit" && onDelete && (
            <button
              type="button"
              onClick={onDelete}
              className="text-[12px] text-rose-400 hover:bg-rose-500/10 px-2 py-1.5 rounded inline-flex items-center gap-1"
            >
              <Trash2 size={12} /> Delete
            </button>
          )}
          <div className="flex-1" />
          <button
            type="button"
            onClick={onCancel}
            className="text-[12px] text-[#8e918f] hover:text-white px-3 py-1.5 rounded"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            className="text-[12px] bg-[var(--accent)]/90 hover:bg-[var(--accent)] text-white px-3 py-1.5 rounded font-medium"
          >
            {mode === "create" ? "Pin" : "Save"}
          </button>
        </div>

        <p className="text-[10.5px] text-[#5a5d61] leading-snug pt-1 border-t border-[#2d2f31]/60">
          Tip: ask JAI to <span className="text-[#8e918f]">&ldquo;track MRR = $48,250&rdquo;</span>{" "}
          and a skill will keep this updated for you.
        </p>
      </div>
    </div>
  );
}

function formatValue(k: Kpi): string {
  const v = (k.value ?? "").toString().trim();
  if (!v) return "—";
  if (k.unit && !v.includes(k.unit)) return `${v} ${k.unit}`;
  return v;
}

function computeTrend(k: Kpi): { dir: "up" | "down"; label: string } | null {
  const cur = numericPart(k.value);
  const prev = numericPart(k.previous);
  if (cur === null || prev === null) return null;
  if (cur === prev) return null;
  const dir: "up" | "down" = cur > prev ? "up" : "down";
  if (prev === 0) {
    return { dir, label: dir === "up" ? "▲" : "▼" };
  }
  const pct = ((cur - prev) / Math.abs(prev)) * 100;
  const abs = Math.abs(pct);
  if (!isFinite(pct) || abs < 0.05) return null;
  return { dir, label: `${abs >= 10 ? abs.toFixed(0) : abs.toFixed(1)}%` };
}

function numericPart(v: string | null | undefined): number | null {
  if (!v) return null;
  const cleaned = v.replace(/[^0-9.\-]/g, "");
  if (!cleaned) return null;
  const n = parseFloat(cleaned);
  return Number.isFinite(n) ? n : null;
}
