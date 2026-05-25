"use client";
import useSWR from "swr";
import { useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  CheckCircle2,
  XCircle,
  ExternalLink,
  CircleAlert,
  Plus,
} from "lucide-react";
import { format, parseISO, differenceInDays } from "date-fns";

type Service = {
  service: string;
  display_name: string;
  category: string;
  healthy: boolean;
  configured: boolean;
  dashboard_url?: string | null;
  balance_usd?: number | null;
  used_usd?: number | null;
  usage?: Record<string, unknown> | null;
  limit?: Record<string, unknown> | null;
  period_end?: string | null;
  notes?: string | null;
  error?: string | null;
  fetched_at: string;
  monthly_cost_usd?: number | null;
  renews_at?: string | null;
};

type StatusResponse = {
  services: Service[];
  monthly_run_rate_usd: number;
};

const CATEGORY_ORDER = ["llm", "voice", "memory", "infra", "platform", "billing"];
const CATEGORY_LABEL: Record<string, string> = {
  llm: "Language models",
  voice: "Voice",
  memory: "Memory",
  infra: "Infrastructure",
  platform: "Other platforms",
  billing: "Billing",
};

export function Status() {
  const { data, isLoading, mutate } = useSWR<StatusResponse>(
    "/status",
    (k: string) => api(k),
    { refreshInterval: 60_000 },
  );

  if (isLoading) {
    return <div className="p-6 text-sm text-[var(--fg-mute)]">Probing services…</div>;
  }
  if (!data) {
    return <div className="p-6 text-sm text-[var(--danger)]">Failed to load status.</div>;
  }

  const grouped = new Map<string, Service[]>();
  for (const s of data.services) {
    (grouped.get(s.category) ?? grouped.set(s.category, []).get(s.category)!).push(s);
  }

  return (
    <div className="p-4 space-y-6">
      <RunRateBanner total={data.monthly_run_rate_usd} services={data.services} />

      {CATEGORY_ORDER.filter((c) => grouped.has(c)).map((cat) => (
        <section key={cat}>
          <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--fg-dim)] mb-2 px-1">
            {CATEGORY_LABEL[cat] ?? cat}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {grouped.get(cat)!.map((s) => (
              <ServiceCard key={s.service} s={s} onChange={mutate} />
            ))}
          </div>
        </section>
      ))}

      <AddRenewal onSaved={mutate} />
    </div>
  );
}

function RunRateBanner({ total, services }: { total: number; services: Service[] }) {
  const dueSoon = services
    .filter((s) => s.renews_at)
    .map((s) => ({ s, days: differenceInDays(parseISO(s.renews_at!), new Date()) }))
    .filter(({ days }) => days <= 14)
    .sort((a, b) => a.days - b.days);

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className="text-xs text-[var(--fg-mute)]">Tracked monthly run-rate</div>
          <div className="text-2xl font-semibold tracking-tight">
            ${total.toFixed(2)}
            <span className="text-sm font-normal text-[var(--fg-mute)] ml-1">/mo</span>
          </div>
        </div>
        {dueSoon.length > 0 && (
          <div className="text-xs text-amber-400 flex items-center gap-1.5">
            <CircleAlert size={14} />
            <span>
              {dueSoon.length} renewal{dueSoon.length > 1 ? "s" : ""} in ≤14d
            </span>
          </div>
        )}
      </div>
      {dueSoon.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {dueSoon.slice(0, 4).map(({ s, days }) => (
            <span
              key={s.service}
              className="text-[11px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20"
            >
              {s.display_name} · {days <= 0 ? "today" : `${days}d`}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ServiceCard({ s, onChange }: { s: Service; onChange: () => void }) {
  const [editing, setEditing] = useState(false);

  return (
    <div
      className={cn(
        "rounded-xl border bg-[var(--bg-elev)] p-3.5 flex flex-col gap-2",
        s.configured
          ? s.healthy
            ? "border-[var(--line)]"
            : "border-[var(--danger)]/40"
          : "border-[var(--line)] opacity-70",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            {s.configured ? (
              s.healthy ? (
                <CheckCircle2 size={14} className="text-[var(--ok)]" />
              ) : (
                <XCircle size={14} className="text-[var(--danger)]" />
              )
            ) : (
              <CircleAlert size={14} className="text-[var(--fg-dim)]" />
            )}
            <div className="font-medium text-sm">{s.display_name}</div>
          </div>
          <div className="text-[11px] text-[var(--fg-dim)] mt-0.5">
            {s.configured ? (s.healthy ? "Connected" : "Error") : "Not configured"}
          </div>
        </div>
        {s.dashboard_url && (
          <a
            href={s.dashboard_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--fg-mute)] hover:text-white"
            aria-label={`Open ${s.display_name} dashboard`}
          >
            <ExternalLink size={14} />
          </a>
        )}
      </div>

      <div className="text-xs space-y-1">
        {typeof s.balance_usd === "number" && (
          <Row label="Balance" value={`$${s.balance_usd.toFixed(2)}`} highlight={s.balance_usd < 5} />
        )}
        {typeof s.used_usd === "number" && (
          <Row label="Used" value={`$${s.used_usd.toFixed(2)}`} />
        )}
        {s.usage && (
          <>
            {Object.entries(s.usage).slice(0, 3).map(([k, v]) => (
              <Row key={k} label={k.replace(/_/g, " ")} value={String(v)} mono />
            ))}
          </>
        )}
        {s.monthly_cost_usd != null && (
          <Row label="Cost" value={`$${Number(s.monthly_cost_usd).toFixed(2)}/mo`} />
        )}
        {s.renews_at && (
          <Row label="Renews" value={format(parseISO(s.renews_at), "MMM d, yyyy")} />
        )}
      </div>

      {s.error && (
        <div className="text-[11px] text-[var(--danger)] mt-1 truncate" title={s.error}>
          {s.error}
        </div>
      )}
      {s.notes && !s.error && (
        <div className="text-[11px] text-[var(--fg-dim)] mt-1">{s.notes}</div>
      )}

      <div className="flex justify-end pt-1">
        <button
          onClick={() => setEditing((v) => !v)}
          className="text-[11px] text-[var(--fg-mute)] hover:text-white"
        >
          {editing ? "Close" : s.monthly_cost_usd != null ? "Edit billing" : "Add billing info"}
        </button>
      </div>

      {editing && (
        <RenewalForm
          service={s.service}
          displayName={s.display_name}
          initialCost={s.monthly_cost_usd ?? undefined}
          initialRenewsAt={s.renews_at ?? undefined}
          initialDashboard={s.dashboard_url ?? undefined}
          onSaved={() => {
            setEditing(false);
            onChange();
          }}
        />
      )}
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[var(--fg-dim)]">{label}</span>
      <span className={cn(mono && "font-mono text-[11px]", highlight && "text-amber-400")}>
        {value}
      </span>
    </div>
  );
}

function RenewalForm({
  service,
  displayName,
  initialCost,
  initialRenewsAt,
  initialDashboard,
  onSaved,
}: {
  service: string;
  displayName: string;
  initialCost?: number;
  initialRenewsAt?: string;
  initialDashboard?: string;
  onSaved: () => void;
}) {
  const [cost, setCost] = useState(initialCost?.toString() ?? "");
  const [renewsAt, setRenewsAt] = useState(initialRenewsAt ?? "");
  const [dashboard, setDashboard] = useState(initialDashboard ?? "");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/status/renewals", {
        method: "POST",
        body: JSON.stringify({
          service,
          display_name: displayName,
          monthly_cost_usd: cost ? parseFloat(cost) : null,
          renews_at: renewsAt || null,
          dashboard_url: dashboard || null,
          notes: notes || null,
        }),
      });
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="grid grid-cols-2 gap-2 pt-2 border-t border-[var(--line)]">
      <input
        type="number"
        step="0.01"
        placeholder="$/mo"
        value={cost}
        onChange={(e) => setCost(e.target.value)}
        className="bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-xs border border-[var(--line)] focus:border-[var(--accent)] outline-none"
      />
      <input
        type="date"
        value={renewsAt}
        onChange={(e) => setRenewsAt(e.target.value)}
        className="bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-xs border border-[var(--line)] focus:border-[var(--accent)] outline-none"
      />
      <input
        type="url"
        placeholder="dashboard URL"
        value={dashboard}
        onChange={(e) => setDashboard(e.target.value)}
        className="col-span-2 bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-xs border border-[var(--line)] focus:border-[var(--accent)] outline-none"
      />
      <input
        type="text"
        placeholder="notes"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        className="col-span-2 bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-xs border border-[var(--line)] focus:border-[var(--accent)] outline-none"
      />
      <button
        type="submit"
        disabled={busy}
        className="col-span-2 bg-[var(--accent)] text-white text-xs font-medium rounded-md py-1.5 disabled:opacity-50"
      >
        {busy ? "Saving…" : "Save"}
      </button>
    </form>
  );
}

function AddRenewal({ onSaved }: { onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [service, setService] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [cost, setCost] = useState("");
  const [renewsAt, setRenewsAt] = useState("");
  const [dashboard, setDashboard] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!service || !displayName) return;
    setBusy(true);
    try {
      await api("/status/renewals", {
        method: "POST",
        body: JSON.stringify({
          service: service.toLowerCase().replace(/[^a-z0-9_]+/g, "_"),
          display_name: displayName,
          monthly_cost_usd: cost ? parseFloat(cost) : null,
          renews_at: renewsAt || null,
          dashboard_url: dashboard || null,
        }),
      });
      setService("");
      setDisplayName("");
      setCost("");
      setRenewsAt("");
      setDashboard("");
      setOpen(false);
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--fg-dim)] mb-2 px-1">
        Track another service
      </h3>
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className="rounded-xl border border-dashed border-[var(--line)] w-full p-4 text-sm text-[var(--fg-mute)] hover:border-[var(--accent)] hover:text-white flex items-center justify-center gap-2"
        >
          <Plus size={16} /> Add subscription
        </button>
      ) : (
        <form
          onSubmit={save}
          className="rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-4 grid grid-cols-2 gap-2"
        >
          <input
            placeholder="ID (e.g. vercel)"
            value={service}
            onChange={(e) => setService(e.target.value)}
            className="bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none"
          />
          <input
            placeholder="Display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none"
          />
          <input
            type="number"
            step="0.01"
            placeholder="$/mo"
            value={cost}
            onChange={(e) => setCost(e.target.value)}
            className="bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none"
          />
          <input
            type="date"
            value={renewsAt}
            onChange={(e) => setRenewsAt(e.target.value)}
            className="bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none"
          />
          <input
            type="url"
            placeholder="dashboard URL"
            value={dashboard}
            onChange={(e) => setDashboard(e.target.value)}
            className="col-span-2 bg-[var(--bg-elev2)] rounded-md px-2 py-1.5 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none"
          />
          <button
            type="submit"
            disabled={busy}
            className="bg-[var(--accent)] text-white text-sm font-medium rounded-md py-1.5 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Add"}
          </button>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="text-sm rounded-md py-1.5 border border-[var(--line)]"
          >
            Cancel
          </button>
        </form>
      )}
    </section>
  );
}
