"use client";
import { createBrowserClient } from "@supabase/ssr";

let _client: ReturnType<typeof createBrowserClient> | null = null;

export function supabase() {
  if (_client) return _client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  if (!url || !key) {
    console.warn("Supabase URL/anon key missing; auth will be disabled.");
  }
  _client = createBrowserClient(url ?? "", key ?? "");
  return _client;
}
