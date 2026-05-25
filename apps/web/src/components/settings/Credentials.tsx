"use client";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Trash2, KeyRound } from "lucide-react";

export function Credentials() {
  const { data } = useSWR<string[]>("/skills/credentials/keys", (k: string) => api(k));
  const { mutate } = useSWRConfig();
  const [k, setK] = useState("");
  const [v, setV] = useState("");

  const add = async () => {
    if (!k.trim() || !v) return;
    await api("/skills/credentials", { method: "POST", body: JSON.stringify({ key: k.trim(), value: v }) });
    setK("");
    setV("");
    mutate("/skills/credentials/keys");
  };

  const remove = async (key: string) => {
    await api(`/skills/credentials/${encodeURIComponent(key)}`, { method: "DELETE" });
    mutate("/skills/credentials/keys");
  };

  return (
    <div className="p-3 space-y-4">
      <p className="text-xs text-[var(--fg-mute)] px-1">
        Credentials are encrypted at rest and only injected into the sandbox at runtime
        for skills that declare them.
      </p>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-3">
        <div className="text-sm font-medium mb-2">Add credential</div>
        <div className="flex gap-2">
          <input
            value={k}
            onChange={(e) => setK(e.target.value)}
            placeholder="KEY (e.g. GMAIL_OAUTH_TOKEN)"
            className="flex-1 bg-[var(--bg)] px-2 py-1.5 rounded-md border border-[var(--line)] outline-none text-sm"
          />
          <input
            value={v}
            onChange={(e) => setV(e.target.value)}
            type="password"
            placeholder="value"
            className="flex-1 bg-[var(--bg)] px-2 py-1.5 rounded-md border border-[var(--line)] outline-none text-sm"
          />
          <button
            onClick={add}
            className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white disabled:opacity-50"
            disabled={!k.trim() || !v}
          >
            Save
          </button>
        </div>
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2 px-1">Stored</h2>
        {!data || data.length === 0 ? (
          <div className="px-3 py-8 text-center text-sm text-[var(--fg-mute)] rounded-lg border border-dashed border-[var(--line)]">
            None yet. Add one above, or just reply in chat with <code>KEY=value</code> when JAI asks.
          </div>
        ) : (
          <ul className="space-y-1.5">
            {data.map((key) => (
              <li
                key={key}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]"
              >
                <KeyRound size={16} className="text-[var(--accent)]" />
                <code className="flex-1 text-sm">{key}</code>
                <span className="text-xs text-[var(--fg-mute)]">••••••</span>
                <button
                  onClick={() => remove(key)}
                  className="p-2 text-[var(--fg-mute)] hover:text-[var(--danger)]"
                  aria-label="Remove"
                >
                  <Trash2 size={16} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
