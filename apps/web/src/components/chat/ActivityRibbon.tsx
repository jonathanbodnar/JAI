"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import {
  Sparkles,
  CheckCircle2,
  ListTodo,
  StickyNote,
  TrendingUp,
  AlertCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { useRealtimeRevalidate } from "@/lib/realtime";
import { cn } from "@/lib/cn";

/**
 * Bottom-left chat overlay that surfaces the last few things JAI did.
 *
 * Why this lives in the chat panel and not the sidebar:
 *  - It's transient context for the current conversation. The user
 *    glances at it ("oh yeah, JAI just drafted that email") without
 *    leaving the keyboard / chat focus.
 *  - Desktop-only by design. On mobile the chat is the whole screen
 *    and an overlay would fight the composer for vertical space.
 *
 * Newest item is at the BOTTOM, brightest. Older items are stacked
 * above with progressively lower opacity. That mirrors the chat
 * reading direction (eyes settle near the composer at the bottom).
 *
 * The ribbon pulls from /activity/recent which blends skill_runs +
 * tasks + notes + kpis into one time-ordered stream. Realtime
 * revalidation on any of those tables keeps it flowing without
 * polling.
 */
type Item = {
  id: string;
  kind: "skill" | "task" | "note" | "kpi" | "canvas";
  title: string;
  detail?: string | null;
  status?: "ok" | "error" | null;
  at: string;
  skill_id?: string;
};

const LIMIT = 5;

export function ActivityRibbon() {
  const { data } = useSWR<Item[]>(
    `/activity/recent?limit=${LIMIT}`,
    (k: string) => api(k),
    {
      // Faster refresh than default; the rail is meant to feel "live"
      // while the user is in a session, even if Realtime misses a beat.
      refreshInterval: 30_000,
      revalidateOnFocus: true,
    },
  );
  useRealtimeRevalidate("skill_runs", "/activity/recent");
  useRealtimeRevalidate("tasks", "/activity/recent");
  useRealtimeRevalidate("notes", "/activity/recent");
  useRealtimeRevalidate("kpis", "/activity/recent");

  // Tick relative timestamps every 30s so "just now" → "1m ago"
  // actually updates while the tab is open.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  const items = (data || []).slice(0, LIMIT);

  // Don't render anything until there's at least one item — empty
  // brand-new accounts shouldn't see a "ghost" ribbon header.
  if (items.length === 0) return null;

  return (
    <aside
      aria-label="Recent activity"
      // Hidden below md (mobile uses the bottom nav + composer area).
      // Absolute so it lives inside the chat panel — no sidebar-width
      // arithmetic, automatically gets the right inset regardless of
      // sidebar expand/collapse state. Sits below the composer's
      // bottom gradient (z-10) and above the message list.
      className="hidden md:block absolute left-4 bottom-36 z-[6] w-[300px] pointer-events-none select-none"
    >
      <div className="text-[10px] uppercase tracking-[0.18em] font-semibold text-[#5a5d61] mb-2 pl-1">
        Recent
      </div>

      {/* Reverse so the freshest item lands at the bottom. We then fade
          upward via the per-row opacity gradient. */}
      <ul className="flex flex-col gap-1.5">
        {[...items].reverse().map((it, idxFromTop) => {
          const fromBottom = items.length - 1 - idxFromTop;
          const opacity = activityOpacity(fromBottom);
          return (
            <li
              // React keys by `id` so only the genuinely-new row is
              // mounted fresh and runs the slide-in keyframes. Existing
              // rows just transition opacity to their new slot.
              key={it.id}
              className={cn(
                "activity-row flex items-start gap-2 text-[12px] leading-snug pl-1 transition-opacity duration-300",
                fromBottom === 0 && "text-zinc-100",
                fromBottom > 0 && "text-[#8e918f]",
              )}
              // CSS variable feeds the @keyframes "to" opacity so the
              // entrance animation lands at exactly the right faded
              // alpha for that row's slot.
              style={{ opacity, ["--row-opacity" as string]: opacity }}
            >
              <span className="shrink-0 mt-[2px]">
                <ItemIcon kind={it.kind} status={it.status} />
              </span>
              <div className="flex-1 min-w-0">
                <div className="truncate font-medium">{it.title}</div>
                {it.detail && (
                  <div className="truncate text-[11px] text-[#5a5d61]">
                    {it.detail}
                  </div>
                )}
              </div>
              <span className="shrink-0 text-[10px] text-[#5a5d61] tabular-nums pt-[2px]">
                {relativeTime(it.at, now)}
              </span>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

function ItemIcon({
  kind,
  status,
}: {
  kind: Item["kind"];
  status?: Item["status"];
}) {
  // Errors always get the warning icon regardless of kind so failures
  // stand out at a glance.
  if (status === "error") {
    return <AlertCircle size={12} className="text-rose-400" />;
  }
  switch (kind) {
    case "skill":
      return <Sparkles size={12} className="text-[var(--accent)]" />;
    case "task":
      // Tasks emitted as "Completed: …" carry status=ok; new tasks have
      // no status. The list-todo icon reads naturally for both.
      return status === "ok" ? (
        <CheckCircle2 size={12} className="text-emerald-400" />
      ) : (
        <ListTodo size={12} className="text-blue-400" />
      );
    case "note":
      return <StickyNote size={12} className="text-purple-400" />;
    case "kpi":
      return <TrendingUp size={12} className="text-amber-400" />;
    default:
      return <Sparkles size={12} className="text-[var(--accent)]" />;
  }
}

/**
 * Linear-ish fade: brightest at index 0 (newest, bottom), fully muted
 * by the top of the list. Caps the floor at ~30% so the oldest row
 * is still legible if the user looks at it.
 */
function activityOpacity(idxFromBottom: number): number {
  const steps = [1, 0.78, 0.55, 0.4, 0.3];
  return steps[Math.min(idxFromBottom, steps.length - 1)];
}

function relativeTime(iso: string, now: number): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const seconds = Math.max(0, Math.floor((now - t) / 1000));
  if (seconds < 45) return "just now";
  if (seconds < 90) return "1m";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 5400) return "1h";
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  const days = Math.round(seconds / 86400);
  if (days < 14) return `${days}d`;
  return new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
