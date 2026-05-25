"use client";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Trash2, Plug } from "lucide-react";

type Connection = {
  name: string;
  transport: "stdio" | "http" | "sse";
  url?: string | null;
  config?: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
};

const PRESETS: { name: string; transport: Connection["transport"]; url?: string; hint?: string }[] = [
  { name: "linear",   transport: "sse",   url: "https://mcp.linear.app/sse" },
  { name: "github",   transport: "sse",   url: "https://api.githubcopilot.com/mcp/" },
];

const GOOGLE_SERVICES: { service: "gmail" | "calendar" | "drive"; label: string; hint: string }[] = [
  { service: "gmail",    label: "Connect Gmail",    hint: "Read + send mail on your behalf" },
  { service: "calendar", label: "Connect Calendar", hint: "Read + create events"           },
  { service: "drive",    label: "Connect Drive",    hint: "Read files for context"          },
];

export function Connections() {
  const { mutate } = useSWRConfig();
  const { data } = useSWR<Connection[]>("/mcp/connections", (k: string) => api(k));
  const [draft, setDraft] = useState<Partial<Connection> | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  // ?connected=gmail&ok=true after OAuth callback redirect
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const c = url.searchParams.get("connected");
    if (c && url.searchParams.get("ok") === "true") {
      setFlash(`Connected ${c}.`);
      mutate("/mcp/connections");
      url.searchParams.delete("connected");
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

  const add = async () => {
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

  const remove = async (name: string) => {
    await api(`/mcp/connections/${name}`, { method: "DELETE" });
    mutate("/mcp/connections");
  };

  return (
    <div className="p-3 space-y-4">
      {flash && (
        <div className="px-3 py-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] text-sm">
          {flash}
        </div>
      )}

      <section>
        <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2 px-1">Google</h2>
        <ul className="grid grid-cols-1 gap-2">
          {GOOGLE_SERVICES.map((g) => {
            const connected = (data || []).some((c) => c.name === g.service && c.is_active);
            return (
              <li key={g.service}>
                <button
                  onClick={() => connectGoogle(g.service)}
                  className="w-full rounded-lg px-3 py-3 text-left bg-[var(--bg-elev)] border border-[var(--line)] hover:border-[var(--accent)] flex items-center gap-3"
                >
                  <div className="flex-1">
                    <div className="text-sm font-medium">{g.label}</div>
                    <div className="text-[11px] text-[var(--fg-mute)] mt-0.5">{g.hint}</div>
                  </div>
                  <span
                    className={
                      "text-[11px] px-2 py-0.5 rounded-full " +
                      (connected
                        ? "bg-[var(--ok)]/15 text-[var(--ok)]"
                        : "bg-[var(--bg-elev2)] text-[var(--fg-mute)]")
                    }
                  >
                    {connected ? "connected" : "connect"}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2 px-1">Active</h2>
        {!data || data.length === 0 ? (
          <Empty>No external integrations connected yet.</Empty>
        ) : (
          <ul className="space-y-1.5">
            {data.map((c) => (
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
                  onClick={() => remove(c.name)}
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
            <button onClick={add} className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white">Save</button>
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
