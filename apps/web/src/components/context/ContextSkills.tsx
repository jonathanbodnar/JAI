"use client";
import useSWR, { useSWRConfig } from "swr";
import { useRef, useState } from "react";
import { api, apiBase } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { Download, Upload, ExternalLink, MoreVertical } from "lucide-react";

type Skill = {
  id: string;
  title: string;
  description: string;
  language: "python" | "typescript" | "bash";
  required_credentials: string[];
  run_count: number;
  last_run_at?: string;
  last_run_status?: string;
};

export function ContextSkills() {
  const { mutate } = useSWRConfig();
  const { data } = useSWR<Skill[]>("/skills", (k: string) => api(k));
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function exportAll() {
    setBusy(true);
    try {
      const { data } = await supabase().auth.getSession();
      const t = data.session?.access_token;
      const res = await fetch(`${apiBase}/skills/_export/all`, {
        headers: t ? { Authorization: `Bearer ${t}` } : {},
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `jai-skills-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(false);
    }
  }

  async function exportOne(skill: Skill) {
    const result = await api<unknown>(`/skills/${skill.id}/export`);
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${skill.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.skill.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true);
    try {
      const text = await f.text();
      const parsed = JSON.parse(text);
      const skills = Array.isArray(parsed?.skills) ? parsed.skills : [parsed];
      const res = await api<{ saved: { title: string }[]; skipped: string[] }>(
        "/skills/_import",
        { method: "POST", body: JSON.stringify({ skills }) },
      );
      setFlash(
        `Imported ${res.saved.length} skill${res.saved.length === 1 ? "" : "s"}${
          res.skipped.length ? `, skipped ${res.skipped.length}` : ""
        }`,
      );
      mutate("/skills");
    } catch (err) {
      setFlash(`Import failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
      e.target.value = "";
      setTimeout(() => setFlash(null), 4000);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--line)] text-xs">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-[var(--line)] hover:bg-[var(--bg-elev)] disabled:opacity-50"
        >
          <Upload size={12} /> Import
        </button>
        <button
          onClick={exportAll}
          disabled={busy || !data || data.length === 0}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-[var(--line)] hover:bg-[var(--bg-elev)] disabled:opacity-50"
        >
          <Download size={12} /> Export all
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json"
          className="hidden"
          onChange={onFile}
        />
        {flash && <div className="ml-auto text-[var(--fg-mute)]">{flash}</div>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {(!data || data.length === 0) ? (
          <div className="px-6 py-16 text-center text-sm text-[var(--fg-mute)]">
            No saved skills yet. Either ask JAI to do something multi-step (it
            will write, run, and save a skill), or import a `.skill.json` file.
          </div>
        ) : (
          <ul className="p-3 space-y-2">
            {data.map((s) => (
              <li
                key={s.id}
                className="rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium">{s.title}</div>
                    <div className="text-sm text-[var(--fg-mute)] mt-1">
                      {s.description}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] uppercase tracking-wider text-[var(--fg-mute)]">
                      {s.language}
                    </span>
                    <button
                      onClick={() => exportOne(s)}
                      title="Export as .skill.json"
                      className="p-1 text-[var(--fg-mute)] hover:text-white"
                    >
                      <Download size={13} />
                    </button>
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-3 text-xs text-[var(--fg-dim)] flex-wrap">
                  <span>{s.run_count}× run</span>
                  {s.last_run_at && (
                    <span>
                      last: {new Date(s.last_run_at).toLocaleDateString()} ({s.last_run_status})
                    </span>
                  )}
                  {s.required_credentials.length > 0 && (
                    <span className="ml-auto">
                      needs: {s.required_credentials.join(", ")}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
