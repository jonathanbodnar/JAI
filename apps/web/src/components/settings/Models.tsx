"use client";

const ROLES: { role: string; envKey: string; description: string }[] = [
  { role: "Orchestrator", envKey: "JAI_MODEL_ORCHESTRATOR", description: "Routes turns, picks tools." },
  { role: "Reflection",   envKey: "JAI_MODEL_REFLECTION",   description: "Introspective patterns + emotional reasoning." },
  { role: "Strategy",     envKey: "JAI_MODEL_STRATEGY",     description: "Business decisions, scenario analysis." },
  { role: "Skill Builder",envKey: "JAI_MODEL_SKILL_BUILDER",description: "Writes scripts for new skills." },
  { role: "Fast",         envKey: "JAI_MODEL_FAST",         description: "Background jobs, summarization, embeddings." },
];

export function Models() {
  return (
    <div className="p-3 space-y-4">
      <p className="text-xs text-[var(--fg-mute)] px-1">
        Models are set via environment on the backend. Edit your <code>.env</code> and
        restart to swap any role. All slugs are OpenRouter slugs (browse them at{" "}
        <a href="https://openrouter.ai/models" className="underline" target="_blank" rel="noreferrer">
          openrouter.ai/models
        </a>
        ).
      </p>
      <ul className="space-y-2">
        {ROLES.map((r) => (
          <li key={r.role} className="rounded-xl border border-[var(--line)] bg-[var(--bg-elev)] p-3">
            <div className="flex items-baseline justify-between gap-2">
              <div className="text-sm font-medium">{r.role}</div>
              <code className="text-[11px] text-[var(--fg-mute)]">{r.envKey}</code>
            </div>
            <div className="text-xs text-[var(--fg-mute)] mt-1">{r.description}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
