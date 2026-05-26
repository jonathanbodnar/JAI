"use client";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Database, Trash2, Plus, CheckCircle2, AlertTriangle, RefreshCw } from "lucide-react";

type DataSource = {
  id: string;
  kind: "supabase";
  slug: string;
  label: string;
  url: string;
  is_active: boolean;
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  created_at: string;
};

type Draft = {
  label: string;
  url: string;
  key: string;
};

export function DataSources() {
  const { mutate } = useSWRConfig();
  const { data: sources } = useSWR<DataSource[]>("/datasources/", (k: string) =>
    api(k),
  );
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const save = async () => {
    if (!draft || !draft.label.trim() || !draft.url.trim() || !draft.key.trim()) return;
    setSaving(true);
    try {
      const out = (await api("/datasources/", {
        method: "POST",
        body: JSON.stringify({
          kind: "supabase",
          label: draft.label.trim(),
          url: draft.url.trim(),
          key: draft.key.trim(),
        }),
      })) as DataSource & { test_detail?: string };
      mutate("/datasources/");
      setDraft(null);
      setFlash(
        out.last_test_ok
          ? `Connected ${out.label} — credentials verified.`
          : `Saved ${out.label} but the test call failed: ${out.test_detail ?? "?"}`,
      );
      setTimeout(() => setFlash(null), 6000);
    } catch (e) {
      setFlash(`Failed to save: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (s: DataSource) => {
    if (!confirm(`Disconnect ${s.label}? Skills won't be able to query it.`)) return;
    await api(`/datasources/${s.id}`, { method: "DELETE" });
    mutate("/datasources/");
  };

  const retest = async (s: DataSource) => {
    setFlash(`Testing ${s.label}…`);
    try {
      const r = (await api(`/datasources/${s.id}/test`, { method: "POST" })) as {
        ok: boolean;
        detail: string;
      };
      setFlash(r.ok ? `${s.label} responded OK.` : `${s.label}: ${r.detail}`);
      mutate("/datasources/");
    } catch (e) {
      setFlash(`Test failed: ${(e as Error).message}`);
    } finally {
      setTimeout(() => setFlash(null), 5000);
    }
  };

  return (
    <div className="p-3 space-y-4">
      {flash && (
        <div className="px-3 py-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] text-sm">
          {flash}
        </div>
      )}

      <section className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)]">
            Data sources
          </h2>
          {!draft && (
            <button
              onClick={() =>
                setDraft({ label: "", url: "", key: "" })
              }
              className="px-3 py-1.5 rounded-full text-[12px] font-medium bg-[var(--accent)] text-white hover:opacity-90 transition flex items-center gap-1.5"
            >
              <Plus size={13} /> Add Supabase project
            </button>
          )}
        </div>

        {(!sources || sources.length === 0) && !draft ? (
          <div className="px-3 py-8 text-center text-sm text-[var(--fg-mute)] rounded-lg border border-dashed border-[var(--line)]">
            No external data sources connected yet.
            <br />
            <span className="text-[11px]">
              Connect a Supabase project (Shoutout, etc.) and skills can query it for stats, progress, anything.
            </span>
          </div>
        ) : (
          <ul className="space-y-1.5">
            {(sources || []).map((s) => (
              <li
                key={s.id}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]"
              >
                <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-emerald-500 to-teal-500 flex items-center justify-center text-white shrink-0">
                  <Database size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate flex items-center gap-2">
                    {s.label}
                    <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--bg-elev2)] text-[var(--fg-mute)] font-mono">
                      {s.slug}
                    </span>
                  </div>
                  <div className="text-[11px] text-[var(--fg-mute)] truncate flex items-center gap-1.5 mt-0.5">
                    {s.last_test_ok === false ? (
                      <span className="inline-flex items-center gap-1 text-amber-500">
                        <AlertTriangle size={11} /> credentials failed last test
                      </span>
                    ) : s.last_test_ok ? (
                      <span className="inline-flex items-center gap-1 text-emerald-500">
                        <CheckCircle2 size={11} /> verified
                      </span>
                    ) : (
                      <span>not tested</span>
                    )}
                    <span>·</span>
                    <span className="truncate">{s.url}</span>
                  </div>
                </div>
                <button
                  onClick={() => retest(s)}
                  className="p-1.5 text-[var(--fg-mute)] hover:text-[var(--accent)]"
                  aria-label="Re-test"
                  title="Re-test credentials"
                >
                  <RefreshCw size={14} />
                </button>
                <button
                  onClick={() => remove(s)}
                  className="p-1.5 text-[var(--fg-mute)] hover:text-[var(--danger)]"
                  aria-label="Disconnect"
                  title="Disconnect"
                >
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {draft && (
        <section className="rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-4 space-y-3">
          <div className="text-sm font-semibold">Connect a Supabase project</div>
          <div className="text-[11px] text-[var(--fg-mute)]">
            Use the project&apos;s <span className="font-mono">service role</span> key (Project Settings → API). JAI encrypts it before storing.
          </div>
          <Field label="Project name">
            <input
              autoFocus
              value={draft.label}
              onChange={(e) => setDraft({ ...draft, label: e.target.value })}
              placeholder="Shoutout"
              className="w-full bg-[var(--bg)] px-3 py-2 rounded-md border border-[var(--line)] outline-none text-sm focus:border-[var(--accent)]"
            />
          </Field>
          <Field label="Project URL">
            <input
              value={draft.url}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
              placeholder="https://abcxyz.supabase.co"
              className="w-full bg-[var(--bg)] px-3 py-2 rounded-md border border-[var(--line)] outline-none text-sm focus:border-[var(--accent)] font-mono"
            />
          </Field>
          <Field label="Service role key">
            <input
              type="password"
              value={draft.key}
              onChange={(e) => setDraft({ ...draft, key: e.target.value })}
              placeholder="eyJhbGciOiJIUzI1NiI…"
              className="w-full bg-[var(--bg)] px-3 py-2 rounded-md border border-[var(--line)] outline-none text-sm focus:border-[var(--accent)] font-mono"
            />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={() => setDraft(null)}
              className="px-3 py-1.5 text-sm text-[var(--fg-mute)]"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={save}
              disabled={saving || !draft.label.trim() || !draft.url.trim() || !draft.key.trim()}
              className="px-4 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white disabled:opacity-50"
            >
              {saving ? "Testing…" : "Save & test"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="text-[11px] uppercase tracking-wider text-[var(--fg-mute)] mb-1">
        {label}
      </div>
      {children}
    </label>
  );
}
