"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import { CheckCircle2, XCircle } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

type Entry = {
  id: string;
  actor: string;
  action: string;
  target?: string | null;
  payload?: Record<string, unknown>;
  ok: boolean;
  error?: string | null;
  created_at: string;
};

export function Audit() {
  const { data, isLoading } = useSWR<Entry[]>("/audit?limit=200", (k: string) => api(k), {
    refreshInterval: 5000,
  });
  if (isLoading) return <div className="p-6 text-sm text-[var(--fg-mute)]">Loading…</div>;
  if (!data || data.length === 0) {
    return (
      <div className="px-6 py-12 text-center text-sm text-[var(--fg-mute)]">
        Nothing in the audit log yet. Every agent action that touches the
        outside world (skills, MCP tool calls, OAuth) shows up here.
      </div>
    );
  }
  return (
    <ul className="p-3 space-y-1.5">
      {data.map((e) => (
        <li
          key={e.id}
          className="rounded-lg border border-[var(--line)] bg-[var(--bg-elev)] p-3 flex items-start gap-3"
        >
          {e.ok ? (
            <CheckCircle2 size={16} className="mt-0.5 text-[var(--ok)] shrink-0" />
          ) : (
            <XCircle size={16} className="mt-0.5 text-[var(--danger)] shrink-0" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline justify-between gap-2">
              <code className="text-sm">{e.action}</code>
              <span className="text-[11px] text-[var(--fg-mute)]">
                {formatDistanceToNow(new Date(e.created_at), { addSuffix: true })}
              </span>
            </div>
            <div className="text-xs text-[var(--fg-mute)] mt-0.5 truncate">
              {e.actor}
              {e.target ? ` → ${e.target}` : ""}
            </div>
            {e.error && (
              <div className="text-xs text-[var(--danger)] mt-1 break-words">{e.error}</div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
