"use client";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { ChevronRight, Sparkles } from "lucide-react";

const STEPS = [
  {
    key: "intro",
    title: "Let's wire up your second brain",
    body: "I'll ask five quick things so I know how to think and talk like you. Skip anything you don't want to share.",
  },
  {
    key: "identity",
    title: "Who you are, in three sentences",
    helper: "Role, background, what you're building. I'll remember this forever.",
    placeholder: "I'm a founder building [thing]. Background in [x]. I care about [y].",
    field: "facts",
    type: "multiline",
    count: 3,
  },
  {
    key: "focus",
    title: "What you're shipping right now",
    helper: "The one thing on your mind this quarter.",
    placeholder: "Get JAI to TestFlight by end of June",
    field: "primary_focus",
    type: "text",
  },
  {
    key: "voice",
    title: "How I should talk to you",
    helper: "Concise? Direct? Use bullet points? Hate emoji? Tell me your style.",
    placeholder: "Concise, direct, no fluff. Push back when I'm wrong.",
    field: "voice_preference",
    type: "text",
  },
  {
    key: "people",
    title: "The people in your orbit",
    helper: "Co-founders, key customers, advisors — names and how they relate to you.",
    placeholder: "Alice — my co-founder. Bob — design lead. Carol — first paying customer.",
    field: "relationships",
    type: "multiline",
    count: 3,
  },
] as const;

export function OnboardingGate({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useSWR<{ completed: boolean }>(
    "/onboarding/status",
    (k: string) => api(k),
  );
  const [skipped, setSkipped] = useState(false);

  if (isLoading) return <>{children}</>;
  if (data?.completed || skipped) return <>{children}</>;

  return (
    <>
      {children}
      <OnboardingModal onClose={() => setSkipped(true)} />
    </>
  );
}

function OnboardingModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [facts, setFacts] = useState<string[]>(["", "", ""]);
  const [focus, setFocus] = useState("");
  const [voice, setVoice] = useState("");
  const [people, setPeople] = useState<string[]>(["", "", ""]);
  const [busy, setBusy] = useState(false);
  const { mutate } = useSWRConfig();

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  const s = STEPS[step];
  const last = step === STEPS.length - 1;

  async function finish() {
    setBusy(true);
    try {
      await api("/onboarding", {
        method: "POST",
        body: JSON.stringify({
          facts: facts.filter((f) => f.trim()),
          primary_focus: focus || null,
          voice_preference: voice || null,
          relationships: people.filter((p) => p.trim()),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }),
      });
      mutate("/onboarding/status");
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-6">
      <div className="bg-[var(--bg-elev)] w-full sm:max-w-md sm:rounded-2xl rounded-t-2xl border border-[var(--line)] flex flex-col max-h-[90vh]">
        <header className="px-5 py-4 border-b border-[var(--line)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-[var(--accent)]" />
            <span className="text-xs uppercase tracking-wider text-[var(--fg-mute)]">
              Step {step + 1} of {STEPS.length}
            </span>
          </div>
          <button onClick={onClose} className="text-xs text-[var(--fg-mute)] hover:text-white">
            Skip for now
          </button>
        </header>

        <div className="px-5 py-6 flex-1 overflow-y-auto space-y-4">
          <h2 className="text-xl font-semibold tracking-tight">{s.title}</h2>
          {"body" in s && s.body && (
            <p className="text-sm text-[var(--fg-mute)] leading-relaxed">{s.body}</p>
          )}
          {"helper" in s && s.helper && (
            <p className="text-xs text-[var(--fg-mute)]">{s.helper}</p>
          )}

          {"field" in s && s.field === "facts" && (
            <div className="space-y-2">
              {facts.map((f, i) => (
                <textarea
                  key={i}
                  value={f}
                  onChange={(e) =>
                    setFacts(facts.map((x, j) => (j === i ? e.target.value : x)))
                  }
                  rows={2}
                  placeholder={i === 0 ? s.placeholder : `Another fact about you (optional)`}
                  className="w-full bg-[var(--bg-elev2)] rounded-lg px-3 py-2 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none resize-none"
                />
              ))}
            </div>
          )}

          {"field" in s && s.field === "primary_focus" && (
            <input
              autoFocus
              value={focus}
              onChange={(e) => setFocus(e.target.value)}
              placeholder={s.placeholder}
              className="w-full bg-[var(--bg-elev2)] rounded-lg px-3 py-2 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none"
            />
          )}

          {"field" in s && s.field === "voice_preference" && (
            <textarea
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              rows={3}
              placeholder={s.placeholder}
              className="w-full bg-[var(--bg-elev2)] rounded-lg px-3 py-2 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none resize-none"
            />
          )}

          {"field" in s && s.field === "relationships" && (
            <div className="space-y-2">
              {people.map((p, i) => (
                <input
                  key={i}
                  value={p}
                  onChange={(e) =>
                    setPeople(people.map((x, j) => (j === i ? e.target.value : x)))
                  }
                  placeholder={i === 0 ? s.placeholder : `Another person (optional)`}
                  className="w-full bg-[var(--bg-elev2)] rounded-lg px-3 py-2 text-sm border border-[var(--line)] focus:border-[var(--accent)] outline-none"
                />
              ))}
            </div>
          )}
        </div>

        <footer className="px-5 py-4 border-t border-[var(--line)] flex items-center justify-between safe-bottom">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="text-sm text-[var(--fg-mute)] disabled:opacity-30"
          >
            Back
          </button>
          {last ? (
            <button
              onClick={finish}
              disabled={busy}
              className="bg-[var(--accent)] text-white text-sm font-medium rounded-full px-5 py-2 flex items-center gap-1.5 disabled:opacity-50"
            >
              {busy ? "Saving…" : "Save & start"}
            </button>
          ) : (
            <button
              onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
              className="bg-[var(--accent)] text-white text-sm font-medium rounded-full px-5 py-2 flex items-center gap-1.5"
            >
              Next <ChevronRight size={14} />
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
