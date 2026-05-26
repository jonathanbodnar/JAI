"use client";
import { useCallback, useEffect } from "react";
import { useSWRConfig } from "swr";
import { supabase } from "./supabase";

/**
 * Subscribe to all changes on a Supabase table for the current user and call
 * `swr.mutate(key)` whenever something changes. Lets tasks/notes update
 * instantly across devices without polling.
 *
 * Resilience:
 *  - On channel SUBSCRIBED (initial + re-subscribe after reconnect) we
 *    fire `revalidate()` so any rows that changed while the socket was
 *    down get pulled in.
 *  - On document visibility-change (back to foreground) we revalidate
 *    AND tear the channel back up if needed.
 *  - On `online` event we re-subscribe and revalidate.
 *
 *  Without this, a user who has the tab in the background while a
 *  skill writes a note (or a deploy bounces the API) sees stale data
 *  until they reload.
 */
export function useRealtimeRevalidate(table: string, swrKey: string | RegExp) {
  const { mutate } = useSWRConfig();

  const revalidate = useCallback(() => {
    if (typeof swrKey === "string") {
      mutate(swrKey);
      // Also kick any `key?param=...` variants like /tasks?list_id=...
      mutate((k) => typeof k === "string" && k.startsWith(swrKey + "?"));
    } else {
      mutate((k) => typeof k === "string" && swrKey.test(k));
    }
  }, [mutate, swrKey]);

  useEffect(() => {
    const client = supabase();
    let cancelled = false;
    let channel: ReturnType<typeof client.channel> | null = null;
    // Track whether we've ever successfully subscribed, so we know
    // we're recovering (not initial-loading) on a re-subscribe.
    let everSubscribed = false;

    const teardown = () => {
      if (channel) {
        try {
          channel.unsubscribe();
        } catch {
          // Already gone — fine.
        }
        channel = null;
      }
    };

    const subscribe = async () => {
      if (cancelled) return;
      teardown();
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
          () => revalidate(),
        )
        .subscribe((status) => {
          if (status === "SUBSCRIBED") {
            // If this is a re-subscribe (after a reconnect), pull
            // anything we missed while the socket was down.
            if (everSubscribed) revalidate();
            everSubscribed = true;
          }
          if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
            // Realtime sometimes hands us a dead channel after a
            // network blip; rebuild and revalidate on the way back up.
            setTimeout(() => {
              if (!cancelled) void subscribe();
            }, 1000);
          }
        });
    };

    void subscribe();

    // Foreground / network events that should also trigger a refresh.
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        revalidate();
        // If the channel's state is anything other than joined, rebuild it.
        const state = channel?.state;
        if (state !== "joined" && state !== "joining") {
          void subscribe();
        }
      }
    };
    const onOnline = () => {
      revalidate();
      void subscribe();
    };
    const onFocus = () => revalidate();

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onOnline);
    window.addEventListener("focus", onFocus);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("focus", onFocus);
      teardown();
    };
  }, [table, revalidate]);
}
