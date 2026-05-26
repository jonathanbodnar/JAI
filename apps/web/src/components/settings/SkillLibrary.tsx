"use client";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Sparkles, Package, CheckCircle2, Loader2 } from "lucide-react";

type LibrarySkill = {
  key: string;
  title: string;
  description: string;
  language: string;
  required_tools: string[];
};

type InstalledSkill = {
  id: string;
  title: string;
  is_active: boolean;
};

type SeedResult = {
  installed: number;
  updated: number;
  skipped: number;
  total: number;
};

const TOOL_BADGE: Record<string, string> = {
  gmail: "bg-red-500/15 text-red-300",
  calendar: "bg-blue-500/15 text-blue-300",
  drive: "bg-emerald-500/15 text-emerald-300",
  web: "bg-purple-500/15 text-purple-300",
};

export function SkillLibrary() {
  const { mutate } = useSWRConfig();
  const { data: library } = useSWR<LibrarySkill[]>("/skills/library", (k: string) => api(k));
  const { data: installed } = useSWR<InstalledSkill[]>("/skills", (k: string) => api(k));
  const [busy, setBusy] = useState<string | "all" | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const installedTitles = new Set((installed || []).map((s) => s.title));

  const installAll = async () => {
    setBusy("all");
    try {
      const r = (await api("/skills/library/seed", {
        method: "POST",
        body: JSON.stringify({}),
      })) as SeedResult;
      mutate("/skills");
      setFlash(
        `Installed ${r.installed}, updated ${r.updated}, skipped ${r.skipped} (already up-to-date). Total: ${r.total}.`,
      );
      setTimeout(() => setFlash(null), 6000);
    } catch (e) {
      setFlash(`Install failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const installOne = async (key: string) => {
    setBusy(key);
    try {
      const r = (await api("/skills/library/seed", {
        method: "POST",
        body: JSON.stringify({ only: [key] }),
      })) as SeedResult;
      mutate("/skills");
      setFlash(
        r.installed
          ? "Installed."
          : r.updated
            ? "Updated."
            : "Already installed and up-to-date.",
      );
      setTimeout(() => setFlash(null), 3000);
    } catch (e) {
      setFlash(`Install failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const groups = (library || []).reduce<Record<string, LibrarySkill[]>>(
    (acc, s) => {
      const cat = s.key.split(".")[0];
      (acc[cat] = acc[cat] || []).push(s);
      return acc;
    },
    {},
  );

  return (
    <div className="p-3 space-y-5">
      {flash && (
        <div className="px-3 py-2 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] text-sm">
          {flash}
        </div>
      )}

      <section className="rounded-2xl border border-[var(--line)] bg-[var(--bg-elev)] p-4 flex items-start gap-4">
        <div className="w-10 h-10 rounded-lg bg-gradient-to-tr from-violet-500 to-fuchsia-500 flex items-center justify-center text-white shrink-0">
          <Package size={20} />
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold">Starter skill library</div>
          <div className="text-[12px] text-[var(--fg-mute)] mt-0.5">
            Pre-built scripts for Gmail, Calendar, Drive, and the web —
            so JAI doesn&apos;t have to invent them from scratch every time.
            Updates are pushed alongside JAI itself; click again to refresh.
          </div>
        </div>
        <button
          onClick={installAll}
          disabled={!library || busy === "all"}
          className="px-4 py-2 rounded-full text-[12px] font-medium bg-[var(--accent)] text-white hover:opacity-90 transition flex items-center gap-1.5 shrink-0 disabled:opacity-50"
        >
          {busy === "all" ? (
            <>
              <Loader2 size={13} className="animate-spin" /> Installing…
            </>
          ) : (
            <>
              <Sparkles size={13} /> Install all
            </>
          )}
        </button>
      </section>

      {Object.entries(groups).map(([cat, list]) => (
        <section key={cat}>
          <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2 px-1">
            {cat}
          </h2>
          <ul className="space-y-1.5">
            {list.map((s) => {
              const isInstalled = installedTitles.has(s.title);
              const isBusy = busy === s.key;
              return (
                <li
                  key={s.key}
                  className="flex items-start gap-3 px-3 py-2.5 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium flex items-center gap-2 flex-wrap">
                      {s.title}
                      <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--bg-elev2)] text-[var(--fg-mute)] font-mono">
                        {s.key}
                      </span>
                      {s.required_tools.map((t) => (
                        <span
                          key={t}
                          className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded font-semibold ${TOOL_BADGE[t] || "bg-[var(--bg-elev2)] text-[var(--fg-mute)]"}`}
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                    <div className="text-[11px] text-[var(--fg-mute)] mt-1 leading-relaxed">
                      {s.description}
                    </div>
                  </div>
                  {isInstalled ? (
                    <button
                      onClick={() => installOne(s.key)}
                      disabled={isBusy}
                      className="text-[11px] text-[var(--fg-mute)] hover:text-[var(--accent)] flex items-center gap-1 shrink-0 px-2 py-1 rounded disabled:opacity-50"
                      title="Re-install / refresh this skill"
                    >
                      {isBusy ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <CheckCircle2 size={12} className="text-emerald-500" />
                      )}
                      Installed
                    </button>
                  ) : (
                    <button
                      onClick={() => installOne(s.key)}
                      disabled={isBusy}
                      className="text-[11px] px-3 py-1 rounded-full bg-[var(--accent)] text-white hover:opacity-90 transition shrink-0 disabled:opacity-50 flex items-center gap-1"
                    >
                      {isBusy ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : null}
                      Install
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
