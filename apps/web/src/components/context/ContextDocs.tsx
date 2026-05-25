"use client";
import useSWR from "swr";
import { api } from "@/lib/api";

type Note = { id: string; title?: string | null; body?: string | null; updated_at: string };

/**
 * Auto-organized docs view. v0.1 simply groups all notes by month; later
 * iterations will use Qdrant hits and Mem0 topics to group by theme.
 */
export function ContextDocs() {
  const { data: notes } = useSWR<Note[]>(
    "/notes?include_archived=true",
    (k: string) => api<Note[]>(k),
  );
  const groups = groupByMonth(notes || []);
  if (!notes || notes.length === 0) {
    return (
      <div className="px-6 py-16 text-center text-sm text-[var(--fg-mute)]">
        Docs will auto-organize here as you and JAI talk. Every note, transcript,
        and ingested doc becomes a searchable item.
      </div>
    );
  }
  return (
    <div className="p-3 space-y-5">
      {groups.map(([label, items]) => (
        <section key={label}>
          <h2 className="text-xs uppercase tracking-wider text-[var(--fg-mute)] mb-2 px-1">
            {label}
          </h2>
          <ul className="space-y-1.5">
            {items.map((n) => (
              <li
                key={n.id}
                className="px-3 py-2 rounded-lg bg-[var(--bg-elev)] border border-[var(--line)]"
              >
                <div className="text-sm font-medium">
                  {n.title || (n.body?.slice(0, 60) ?? "Untitled")}
                </div>
                {n.body && (
                  <div className="text-xs text-[var(--fg-mute)] mt-0.5 line-clamp-2">
                    {n.body}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function groupByMonth(notes: Note[]): [string, Note[]][] {
  const out = new Map<string, Note[]>();
  for (const n of notes) {
    const k = new Date(n.updated_at).toLocaleString(undefined, { year: "numeric", month: "long" });
    out.set(k, [...(out.get(k) ?? []), n]);
  }
  return [...out.entries()];
}
