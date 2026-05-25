"use client";
import { supabase } from "./supabase";

const BASE = process.env.NEXT_PUBLIC_JAI_BACKEND_URL || "http://localhost:8000";

async function authHeader(): Promise<Record<string, string>> {
  try {
    const { data } = await supabase().auth.getSession();
    const t = data.session?.access_token;
    return t ? { Authorization: `Bearer ${t}` } : {};
  } catch {
    return {};
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const h = await authHeader();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...h,
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const apiBase = BASE;

export async function wsToken(): Promise<string | undefined> {
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token;
}
