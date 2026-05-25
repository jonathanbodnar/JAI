"use client";
import { useEffect, useState } from "react";
import { supabase } from "./supabase";

/**
 * Email + 6-digit OTP auth.
 *
 * We deliberately use the OTP code (not the magic link) because the link
 * flow depends on Supabase's Site URL + Redirect URLs allowlist being
 * configured perfectly — and Supabase silently falls back to whatever the
 * Site URL is on any mismatch, which is how the "magic link goes to
 * localhost" bug keeps coming back. OTP code is portable: same email arrives,
 * user types the 6 digits, no redirect, no allowlist, no dependency on
 * dashboard state.
 *
 * In dev with no Supabase URL configured this passes through (backend uses
 * JAI_USER_ID fallback).
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const [ready, setReady] = useState(!url);
  const [authed, setAuthed] = useState(!url);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<"email" | "code">("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!url) return;
    const sb = supabase();
    sb.auth.getSession().then(({ data }) => {
      setAuthed(!!data.session);
      setReady(true);
    });
    const { data: sub } = sb.auth.onAuthStateChange((_evt, session) => {
      setAuthed(!!session);
    });
    return () => sub.subscription.unsubscribe();
  }, [url]);

  if (!ready) return <Splash text="…" />;
  if (authed) return <>{children}</>;

  const sendCode = async () => {
    setError(null);
    setBusy(true);
    try {
      const sb = supabase();
      const { error } = await sb.auth.signInWithOtp({
        email,
        options: { shouldCreateUser: true },
      });
      if (error) throw error;
      setStage("code");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send code");
    } finally {
      setBusy(false);
    }
  };

  const verifyCode = async () => {
    setError(null);
    setBusy(true);
    try {
      const sb = supabase();
      const { error } = await sb.auth.verifyOtp({
        email,
        token: code.trim(),
        type: "email",
      });
      if (error) throw error;
      // onAuthStateChange will flip `authed` to true.
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid code");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full flex flex-col items-center justify-center px-6 gap-4">
      <div className="text-5xl">🧠</div>
      <h1 className="text-xl font-semibold">JAI</h1>
      <p className="text-sm text-[var(--fg-mute)] max-w-sm text-center">
        Your second brain. Sign in with your email — we&apos;ll send a 6-digit code.
      </p>

      {stage === "email" ? (
        <div className="flex flex-col gap-2 w-full max-w-xs">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && email.includes("@") && !busy && sendCode()}
            placeholder="you@email.com"
            className="px-3 py-2 rounded-lg bg-[var(--bg-elev2)] border border-[var(--line)] outline-none"
            autoComplete="email"
            autoFocus
          />
          <button
            onClick={sendCode}
            disabled={!email.includes("@") || busy}
            className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white disabled:opacity-50"
          >
            {busy ? "Sending…" : "Send code"}
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-2 w-full max-w-xs">
          <p className="text-xs text-[var(--fg-mute)] text-center">
            Sent to <span className="text-white">{email}</span>. Check inbox + spam.
          </p>
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) =>
              e.key === "Enter" && code.length === 6 && !busy && verifyCode()
            }
            placeholder="6-digit code"
            className="px-3 py-2 rounded-lg bg-[var(--bg-elev2)] border border-[var(--line)] outline-none text-center tracking-widest text-lg"
            autoFocus
            autoComplete="one-time-code"
          />
          <button
            onClick={verifyCode}
            disabled={code.length !== 6 || busy}
            className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white disabled:opacity-50"
          >
            {busy ? "Verifying…" : "Sign in"}
          </button>
          <button
            onClick={() => {
              setStage("email");
              setCode("");
              setError(null);
            }}
            disabled={busy}
            className="text-xs text-[var(--fg-mute)] hover:text-white"
          >
            Use a different email
          </button>
        </div>
      )}

      {error && <p className="text-xs text-[var(--err)] text-center max-w-xs">{error}</p>}
    </div>
  );
}

function Splash({ text }: { text: string }) {
  return (
    <div className="h-full flex items-center justify-center text-[var(--fg-mute)]">{text}</div>
  );
}
