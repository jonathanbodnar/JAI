"use client";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Trash2, Plug, Mail, CalendarDays, HardDrive, Star, Plus } from "lucide-react";

type Connection = {
  name: string;
  transport: "stdio" | "http" | "sse";
  url?: string | null;
  config?: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
};

type ConnectedAccount = {
  id: string;
  provider: string;
  service: "gmail" | "calendar" | "drive";
  account_email: string;
  label?: string | null;
  scopes: string[];
  metadata?: { name?: string; picture?: string } | null;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

const PRESETS: { name: string; transport: Connection["transport"]; url?: string; hint?: string }[] = [
  { name: "linear",   transport: "sse",   url: "https://mcp.linear.app/sse" },
  { name: "github",   transport: "sse",   url: "https://api.githubcopilot.com/mcp/" },
];

const GOOGLE_SERVICES: {
  service: "gmail" | "calendar" | "drive";
  label: string;
  hint: string;
  Icon: typeof Mail;
  brand: string;
}[] = [
  { service: "gmail",    label: "Gmail",    hint: "Read + send mail on your behalf", Icon: Mail,         brand: "from-red-500 to-orange-500" },
  { service: "calendar", label: "Calendar", hint: "Read + create events",            Icon: CalendarDays, brand: "from-blue-500 to-sky-500"   },
  { service: "drive",    label: "Drive",    hint: "Read files for context",          Icon: HardDrive,    brand: "from-emerald-500 to-teal-500" },
];

export function Connections() {
  const { mutate } = useSWRConfig();
  const { data: conns } = useSWR<Connection[]>("/mcp/connections", (k: string) => api(k));
  const { data: accounts } = useSWR<ConnectedAccount[]>("/auth/accounts", (k: string) => api(k));
  const [draft, setDraft] = useState<Partial<Connection> | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  // ?connected=gmail&account=foo@bar.com&ok=true after OAuth callback redirect
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const c = url.searchParams.get("connected");
    if (c && url.searchParams.get("ok") === "true") {
      const acct = url.searchParams.get("account");
      setFlash(acct ? `Connected ${c} (${acct}).` : `Connected ${c}.`);
      mutate("/mcp/connections");
      mutate("/auth/accounts");
      url.searchParams.delete("connected");
      url.searchParams.delete("account");
      url.searchParams.delete("ok");
      window.history.replaceState({}, "", url.toString());
      const t = setTimeout(() => setFlash(null), 4000);
      return () => clearTimeout(t);
    }
  }, [mutate]);

  const connectGoogle = async (service: "gmail" | "calendar" | "drive") => {
    const res = await api<{ auth_url: string }>(
      `/auth/google/start?service=${service}&return_to=${encodeURIComponent(
        window.location.origin + "/settings"
      )}`
    );
    window.location.href = res.auth_url;
  };

  const removeAccount = async (account: ConnectedAccount) => {
    if (!confirm(`Disconnect ${account.account_email} (${account.service})?`)) return;
    await api(`/auth/accounts/${account.id}`, { method: "DELETE" });
    mutate("/auth/accounts");
    mutate("/mcp/connections");
  };

  const makeDefault = async (account: ConnectedAccount) => {
    await api(`/auth/accounts/${account.id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_default: true }),
    });
    mutate("/auth/accounts");
  };

  const addCustom = async () => {
    if (!draft?.name || !draft?.transport) return;
    await api("/mcp/connections", {
      method: "POST",
      body: JSON.stringify({
        name: draft.name,
        transport: draft.transport,
        url: draft.url ?? null,
        config: draft.config ?? {},
      }),
    });
    setDraft(null);
    mutate("/mcp/connections");
  };

  const removeConn = async (name: string) => {
    await api(`/mcp/connections/${name}`, { method: "DELETE" });
    mutate("/mcp/connections");
  };

  // Group accounts by service.
  const accountsByService = (accounts || []).reduce<
    Record<string, ConnectedAccount[]>
  >((acc, a) => {
    (acc[a.service] = acc[a.service] || []).push(a);
    return acc;
  }, {});

  // Non-Google MCP connections only — Google services are now represented by
  // `connected_accounts` instead.
  const customConns = (conns || []).filter(
    (c) => !["gmail", "calendar", "drive"].includes(c.name) && c.is_active,
  );

  return (
    <div className="p-3 space-y-5">
      {flash && (
        <div className="px-3 py-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] text-sm">
          {flash}
        </div>
      )}

      <section className="space-y-3">
        <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] px-1">Google accounts</h2>

        {GOOGLE_SERVICES.map((g) => {
          const list = accountsByService[g.service] || [];
          return (
            <div
              key={g.service}
              className="rounded-2xl border border-[var(--line)] bg-[var(--bg-elev)] overflow-hidden"
            >
              <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--line)]">
                <div
                  className={`w-9 h-9 rounded-lg bg-gradient-to-tr ${g.brand} flex items-center justify-center text-white shrink-0`}
                >
                  <g.Icon size={18} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold">{g.label}</div>
                  <div className="text-[11px] text-[var(--fg-mute)] mt-0.5">{g.hint}</div>
                </div>
                <button
                  onClick={() => connectGoogle(g.service)}
                  className="px-3 py-1.5 rounded-full text-[12px] font-medium bg-[var(--accent)] text-white hover:opacity-90 transition flex items-center gap-1.5"
                  title={list.length ? `Add another ${g.label} account` : `Connect ${g.label}`}
                >
                  <Plus size={13} />
                  {list.length ? "Add another" : "Connect"}
                </button>
              </div>

              {list.length === 0 ? (
                <div className="px-4 py-4 text-[12px] text-[var(--fg-mute)]">
                  No {g.label.toLowerCase()} accounts connected yet.
                </div>
              ) : (
                <ul className="divide-y divide-[var(--line)]">
                  {list.map((a) => (
                    <li
                      key={a.id}
                      className="flex items-center gap-3 px-4 py-2.5"
                    >
                      <div className="w-7 h-7 rounded-full bg-[var(--bg-elev2)] flex items-center justify-center text-[11px] font-semibold text-[var(--accent)] shrink-0 border border-[var(--line)] overflow-hidden">
                        {a.metadata?.picture ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={a.metadata.picture} alt="" className="w-full h-full object-cover" />
                        ) : (
                          (a.account_email[0] || "?").toUpperCase()
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13px] font-medium truncate">{a.account_email}</div>
                        {a.metadata?.name && (
                          <div className="text-[11px] text-[var(--fg-mute)] truncate">
                            {a.metadata.name}
                          </div>
                        )}
                      </div>
                      {a.is_default ? (
                        <span className="text-[10px] uppercase tracking-wide font-bold text-[var(--accent)] flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--accent-soft)]">
                          <Star size={10} className="fill-current" /> Default
                        </span>
                      ) : (
                        <button
                          onClick={() => makeDefault(a)}
                          className="text-[10px] uppercase tracking-wide font-semibold text-[var(--fg-mute)] hover:text-[var(--accent)] px-2 py-0.5 rounded-full hover:bg-[var(--accent-soft)] transition flex items-center gap-1"
                          title="Make this the default account skills use"
                        >
                          <Star size={10} /> Set default
                        </button>
                      )}
                      <button
                        onClick={() => removeAccount(a)}
                        className="p-1.5 text-[var(--fg-mute)] hover:text-[var(--danger)]"
                        aria-label="Disconnect"
                        title="Disconnect this account"
                      >
                        <Trash2 size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2 px-1">Other integrations</h2>
        {customConns.length === 0 ? (
          <Empty>No external MCP integrations connected yet.</Empty>
        ) : (
          <ul className="space-y-1.5">
            {customConns.map((c) => (
              <li
                key={c.name}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]"
              >
                <Plug size={16} className="text-[var(--accent)]" />
                <div className="flex-1">
                  <div className="text-sm font-medium">{c.name}</div>
                  <div className="text-xs text-[var(--fg-mute)]">{c.transport}{c.url ? ` · ${c.url}` : ""}</div>
                </div>
                <button
                  onClick={() => removeConn(c.name)}
                  className="p-2 text-[var(--fg-mute)] hover:text-[var(--danger)]"
                  aria-label="Disconnect"
                >
                  <Trash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2 px-1">Quick add</h2>
        <ul className="grid grid-cols-2 gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.name}
              onClick={() => setDraft({ name: p.name, transport: p.transport, url: p.url })}
              className="rounded-lg px-3 py-3 text-left bg-[var(--bg-elev)] border border-[var(--line)] hover:border-[var(--accent)]"
            >
              <div className="text-sm font-medium">{p.name}</div>
              {p.hint && <div className="text-[11px] text-[var(--fg-mute)] mt-0.5">{p.hint}</div>}
            </button>
          ))}
        </ul>
      </section>

      {draft && (
        <section className="rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-3 space-y-2">
          <div className="text-sm font-medium mb-1">Add connection</div>
          <Field label="Name">
            <input
              value={draft.name ?? ""}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className="w-full bg-[var(--bg)] px-2 py-1.5 rounded-md border border-[var(--line)] outline-none text-sm"
            />
          </Field>
          <Field label="Transport">
            <select
              value={draft.transport ?? "sse"}
              onChange={(e) => setDraft({ ...draft, transport: e.target.value as Connection["transport"] })}
              className="w-full bg-[var(--bg)] px-2 py-1.5 rounded-md border border-[var(--line)] outline-none text-sm"
            >
              <option value="sse">sse</option>
              <option value="http">http</option>
              <option value="stdio">stdio (local)</option>
            </select>
          </Field>
          {(draft.transport === "sse" || draft.transport === "http") && (
            <Field label="URL">
              <input
                value={draft.url ?? ""}
                onChange={(e) => setDraft({ ...draft, url: e.target.value })}
                placeholder="https://…"
                className="w-full bg-[var(--bg)] px-2 py-1.5 rounded-md border border-[var(--line)] outline-none text-sm"
              />
            </Field>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setDraft(null)} className="px-3 py-1.5 text-sm text-[var(--fg-mute)]">Cancel</button>
            <button onClick={addCustom} className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white">Save</button>
          </div>
        </section>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-mute)] mb-1">{label}</div>
      {children}
    </label>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="px-3 py-8 text-center text-sm text-[var(--fg-mute)] rounded-lg border border-dashed border-[var(--line)]">{children}</div>;
}
