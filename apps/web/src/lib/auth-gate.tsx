"use client";
import { useEffect, useState } from "react";
import { supabase } from "./supabase";

/**
 * Minimal email-link auth gate. Wrap the app's protected content with this
 * and we'll prompt for an email, send a magic link, and resume.
 *
 * In dev with no Supabase URL configured, this passes through (backend uses
 * JAI_USER_ID fallback).
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const [ready, setReady] = useState(!url);
  const [authed, setAuthed] = useState(!url);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

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

  const send = async () => {
    const sb = supabase();
    // Prefer NEXT_PUBLIC_SITE_URL so magic links always land on production,
    // even when sent from a localhost dev tab. Falls back to current origin
    // for fresh local-only setups.
    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
    await sb.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${siteUrl}/auth/callback` },
    });
    setSent(true);
  };

  return (
    <div className="h-full flex flex-col items-center justify-center px-6 gap-4">
      <div className="text-5xl">🧠</div>
      <h1 className="text-xl font-semibold">JAI</h1>
      <p className="text-sm text-[var(--fg-mute)] max-w-sm text-center">
        Your second brain, one living conversation. Sign in with your email; we&apos;ll send
        a magic link.
      </p>
      {sent ? (
        <p className="text-sm text-[var(--ok)]">Link sent — check {email}.</p>
      ) : (
        <div className="flex flex-col gap-2 w-full max-w-xs">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@email.com"
            className="px-3 py-2 rounded-lg bg-[var(--bg-elev2)] border border-[var(--line)] outline-none"
          />
          <button
            onClick={send}
            disabled={!email.includes("@")}
            className="px-3 py-2 rounded-lg bg-[var(--accent)] text-white disabled:opacity-50"
          >
            Send magic link
          </button>
        </div>
      )}
    </div>
  );
}

function Splash({ text }: { text: string }) {
  return (
    <div className="h-full flex items-center justify-center text-[var(--fg-mute)]">{text}</div>
  );
}
