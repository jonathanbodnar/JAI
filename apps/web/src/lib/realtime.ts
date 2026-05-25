"use client";
import { useEffect } from "react";
import { useSWRConfig } from "swr";
import { supabase } from "./supabase";

/**
 * Subscribe to all changes on a Supabase table for the current user and call
 * `swr.mutate(key)` whenever something changes. Lets tasks/notes update
 * instantly across devices without polling.
 */
export function useRealtimeRevalidate(table: string, swrKey: string | RegExp) {
  const { mutate } = useSWRConfig();
  useEffect(() => {
    const client = supabase();
    let cancelled = false;
    let channel: ReturnType<typeof client.channel> | null = null;

    (async () => {
      const { data } = await client.auth.getSession();
      const uid = data.session?.user?.id;
      if (!uid || cancelled) return;
      channel = client
        .channel(`rt-${table}-${uid}`)
        .on(
          "postgres_changes",
          {
            event: "*",
            schema: "public",
            table,
            filter: `user_id=eq.${uid}`,
          },
          () => {
            if (typeof swrKey === "string") {
              mutate(swrKey);
              mutate((k) => typeof k === "string" && k.startsWith(swrKey + "?"));
            } else {
              mutate((k) => typeof k === "string" && swrKey.test(k));
            }
          },
        )
        .subscribe();
    })();

    return () => {
      cancelled = true;
      if (channel) channel.unsubscribe();
    };
  }, [table, swrKey, mutate]);
}
