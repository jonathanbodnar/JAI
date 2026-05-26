"use client";
import { useEffect, useRef, useState } from "react";
import { ChatSocket, type ServerMsg } from "@/lib/ws";
import { PressRecorder, StreamingAudioPlayer } from "@/lib/voice";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import Link from "next/link";
import { Settings, Trash2, BrainCircuit } from "lucide-react";
import { MessageList, type Message, type Step } from "./MessageList";
import { Composer } from "./Composer";
import { cn } from "@/lib/cn";

const CHAT_KEY = "jai.chat.messages.v1";
const CHAT_MAX = 500;

function loadMessages(): Message[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CHAT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Message[]) : [];
  } catch {
    return [];
  }
}

function saveMessages(msgs: Message[]) {
  if (typeof window === "undefined") return;
  try {
    const trimmed = msgs.slice(-CHAT_MAX);
    localStorage.setItem(CHAT_KEY, JSON.stringify(trimmed));
  } catch {
    try {
      localStorage.setItem(CHAT_KEY, JSON.stringify(msgs.slice(-Math.floor(CHAT_MAX / 2))));
    } catch {
      // quota exceeded; give up
    }
  }
}

type ServerMessageRow = {
  id: string;
  role: string;
  content: string;
  metadata?: { role_used?: string } | null;
  created_at: string;
};

export function ChatView() {
  const [messages, setMessages] = useState<Message[]>(() => loadMessages());
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [recording, setRecording] = useState(false);
  const [liveSteps, setLiveSteps] = useState<Step[]>([]);
  // When the server reports an interrupted turn (Railway redeploy
  // killed it mid-skill) we stash the original prompt + a timestamp so
  // we can render a Retry banner above the composer.
  const [lastUserInput, setLastUserInput] = useState<string>("");
  const [interruptedAt, setInterruptedAt] = useState<number | null>(null);
  const liveStepsRef = useRef<Step[]>([]);
  const wsRef = useRef<ChatSocket | null>(null);
  const recRef = useRef<PressRecorder | null>(null);
  const playerRef = useRef<StreamingAudioPlayer | null>(null);
  const thinkingStartRef = useRef<number | null>(null);

  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  useEffect(() => {
    liveStepsRef.current = liveSteps;
  }, [liveSteps]);

  // Watchdog — if `thinking` stays on for >2 minutes with no fresh
  // activity, assume the in-flight turn was killed (Railway deploy,
  // process crash, etc.) and surface a Retry option instead of
  // spinning forever. The server-side orphan detection in /chat/recent
  // catches refreshes; this catches users who stayed on the page.
  useEffect(() => {
    if (!thinking) {
      thinkingStartRef.current = null;
      return;
    }
    if (thinkingStartRef.current == null) {
      thinkingStartRef.current = Date.now();
    }
    const t = setInterval(() => {
      const started = thinkingStartRef.current;
      if (!started) return;
      if (Date.now() - started > 120_000) {
        setThinking(false);
        const lastUser = [...messages].reverse().find((m) => m.role === "user");
        if (lastUser) setLastUserInput(lastUser.text);
        setInterruptedAt(Date.now());
        thinkingStartRef.current = null;
      }
    }, 5000);
    return () => clearInterval(t);
  }, [thinking, messages]);

  // Pulls recent messages from the server and merges any that the local
  // client missed (e.g. an assistant_final the server persisted while we
  // were on another tab / page).
  const recoverFromServer = async () => {
    try {
      const { messages: rows, interrupted } = (await api(
        "/chat/recent?limit=100",
      )) as {
        messages: ServerMessageRow[];
        interrupted?: boolean;
      };
      if (!Array.isArray(rows) || rows.length === 0) return;
      setMessages((prev) => {
        const merged = mergeServerMessages(prev, rows);
        const last = merged[merged.length - 1];
        if (last && last.role === "user") {
          // Server says the in-flight turn was killed (almost always a
          // Railway deploy mid-skill). Don't keep spinning forever —
          // surface a retry affordance and stop the spinner.
          if (interrupted) {
            setThinking(false);
            setLastUserInput(last.text);
            setInterruptedAt(Date.now());
          } else {
            setThinking(true);
          }
        }
        return merged;
      });
    } catch {
      // Network or auth blip — ignore; localStorage still has the user's view.
    }
  };

  // Sidebar's "New chat" pill dispatches this event to wipe the current thread.
  useEffect(() => {
    const onNew = () => {
      setMessages([]);
      void api("/chat/reset", { method: "POST" }).catch(() => { /* ignore */ });
    };
    window.addEventListener("jai:new-chat", onNew);
    return () => window.removeEventListener("jai:new-chat", onNew);
  }, []);

  // Supabase Realtime subscription: whenever the API writes a new message
  // row for this user (including server-side responses that happened while
  // the page was refreshing or the WS was dead), append it to the local
  // list. This is the safety net that makes "refresh while waiting" safe.
  useEffect(() => {
    const client = supabase();
    let channel: ReturnType<typeof client.channel> | null = null;
    let cancelled = false;
    (async () => {
      const { data } = await client.auth.getSession();
      const uid = data.session?.user?.id;
      if (!uid || cancelled) return;

      channel = client
        .channel(`rt-messages-${uid}`)
        .on(
          "postgres_changes",
          {
            event: "INSERT",
            schema: "public",
            table: "messages",
            filter: `user_id=eq.${uid}`,
          },
          (payload) => {
            const row = payload.new as {
              id: string;
              role: string;
              content: string;
              metadata?: { role_used?: string } | null;
            };
            if (row.role !== "user" && row.role !== "assistant") return;
            setMessages((prev) => {
              // Dedupe by (role, content) — the WS may have already pushed
              // this exact text, and we don't want it twice.
              const key = `${row.role}|${(row.content || "").trim()}`;
              const seen = prev.some(
                (m) => `${m.role}|${(m.text || "").trim()}` === key,
              );
              if (seen) return prev;
              return [
                ...prev,
                {
                  id: row.id,
                  role: row.role as "user" | "assistant",
                  text: row.content,
                  agent: row.metadata?.role_used,
                },
              ];
            });
            if (row.role === "assistant") {
              setThinking(false);
              // If the late reply finally lands, retire the interrupted
              // banner — no point asking the user to retry something
              // that just succeeded.
              setInterruptedAt(null);
            }
          },
        )
        .subscribe();
    })();
    return () => {
      cancelled = true;
      if (channel) channel.unsubscribe();
    };
  }, []);

  useEffect(() => {
    // Pull whatever the server has on first mount so a response that
    // landed while the tab was closed shows up immediately.
    void recoverFromServer();
    const sock = new ChatSocket({
      onOpen: () => {
        setConnected(true);
        // Anything that arrived while the socket was down — recover it.
        void recoverFromServer();
        // If we re-opened with a still-spinning "thinking" indicator,
        // the server-side turn has either finished (recoverFromServer
        // appended the assistant) or failed silently. Clear the spinner.
        setThinking(false);
      },
      onClose: () => setConnected(false),
      onMessage: (m: ServerMsg) => {
        switch (m.type) {
          case "user_transcript":
            setMessages((prev) => [
              ...prev,
              { id: cryptoId(), role: "user", text: m.text },
            ]);
            setThinking(true);
            setLiveSteps([]);
            break;
          case "step":
            setLiveSteps((prev) => [
              ...prev,
              {
                id: cryptoId(),
                node: m.node,
                label: m.label,
                detail: m.detail ?? null,
                done: true,
              },
            ]);
            break;
          case "assistant_final":
            setMessages((prev) => {
              const steps = liveStepsRef.current;
              return [
                ...prev,
                {
                  id: cryptoId(),
                  role: "assistant",
                  text: m.text,
                  agent: m.role_used,
                  steps: steps.length ? steps : undefined,
                },
              ];
            });
            setLiveSteps([]);
            setThinking(false);
            playerRef.current = new StreamingAudioPlayer("audio/mpeg");
            break;
          case "audio_chunk":
            playerRef.current?.push(m.b64);
            break;
          case "audio_done":
            playerRef.current?.finish();
            playerRef.current = null;
            break;
          case "error":
            setMessages((prev) => [
              ...prev,
              { id: cryptoId(), role: "assistant", text: `⚠️ ${m.message}`, agent: "error" },
            ]);
            setThinking(false);
            break;
        }
      },
    });
    sock.connect();
    wsRef.current = sock;
    return () => sock.close();
  }, []);

  const send = (text: string) => {
    if (!text.trim() || !wsRef.current) return;
    setMessages((prev) => [...prev, { id: cryptoId(), role: "user", text }]);
    setLiveSteps([]);
    setThinking(true);
    setInterruptedAt(null);
    wsRef.current.sendText(text);
  };

  const retryInterrupted = () => {
    if (!lastUserInput) return;
    setInterruptedAt(null);
    setLiveSteps([]);
    setThinking(true);
    wsRef.current?.sendText(lastUserInput);
  };

  const dismissInterrupted = () => {
    setInterruptedAt(null);
  };

  const onTalkStart = async () => {
    if (!wsRef.current) return;
    recRef.current = new PressRecorder();
    setRecording(true);
    try {
      await recRef.current.start();
      wsRef.current.sendAudioStart();
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: cryptoId(), role: "assistant", text: `⚠️ mic error: ${(e as Error).message}` },
      ]);
      setRecording(false);
      recRef.current = null;
    }
  };

  const onTalkEnd = async () => {
    setRecording(false);
    if (!recRef.current || !wsRef.current) return;
    let blob: Blob;
    try {
      blob = await recRef.current.stop();
    } catch {
      return;
    } finally {
      recRef.current = null;
    }
    if (blob.size === 0) {
      setMessages((prev) => [
        ...prev,
        { id: cryptoId(), role: "assistant", text: "⚠️ no audio captured — try holding the mic a bit longer." },
      ]);
      return;
    }
    const buf = await blob.arrayBuffer();
    wsRef.current.sendAudioChunk(buf);
    wsRef.current.sendAudioDone();
    setThinking(true);
  };

  return (
    <div className="flex flex-col h-full bg-[#131314] select-none relative">
      {/* Top Header */}
      <header className="header-safe-pt px-6 pb-4 flex items-center justify-between border-b border-[#2d2f31] bg-[#131314]/80 backdrop-blur-xl z-20">
        <div className="flex items-center gap-3">
          {/* Logo */}
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-tr from-[#7c5cff] via-[#9b76ff] to-[#f43f5e] shadow-[0_0_15px_rgba(124,92,255,0.3)] shrink-0">
            <BrainCircuit size={18} className="text-white" />
          </div>
          {/* Multi-model stack — voice is Kimi K2.6, routing is Flash, strategy
              is DeepSeek, skills are Qwen. The badge says "Multi" so we don't
              lie about which model wrote any given turn. */}
          <div className="flex flex-col">
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-1.5">
              JAI
              <span
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] font-bold text-zinc-300 border border-zinc-700/50 uppercase"
                title="Routing on Gemini Flash · Voice on Kimi K2.6 · Strategy on DeepSeek · Skills on Qwen"
              >
                Multi
              </span>
            </h1>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-4 text-xs text-[#8e918f]">
          {/* Realtime WS Indicator */}
          <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#1e1f20] border border-[#2d2f31] text-[11px] font-medium">
            <span
              className={cn(
                "h-2 w-2 rounded-full transition-transform duration-300",
                connected ? "bg-emerald-400 shadow-[0_0_8px_#34d399]" : "bg-[#8e918f]"
              )}
            />
            {connected ? "Live" : "Connecting…"}
          </div>

          {messages.length > 0 && (
            <button
              onClick={async () => {
                if (
                  !confirm(
                    "Clear this chat and reset JAI's working memory? " +
                      "Identity facts (Mem0) and your uploaded context (Qdrant / graph) are kept.",
                  )
                )
                  return;
                setMessages([]);
                try {
                  await api("/chat/reset", { method: "POST" });
                } catch (e) {
                  console.warn("chat reset failed", e);
                }
              }}
              aria-label="Clear chat"
              className="p-1.5 rounded-full hover:bg-zinc-800/40 text-[#8e918f] hover:text-white transition-all border border-transparent hover:border-[#2d2f31]"
              title="Clear chat + reset JAI's working memory"
            >
              <Trash2 size={16} />
            </button>
          )}

          <Link
            href="/settings"
            aria-label="Settings"
            className="p-1.5 rounded-full hover:bg-zinc-800/40 text-[#8e918f] hover:text-white transition-all border border-transparent hover:border-[#2d2f31]"
          >
            <Settings size={17} />
          </Link>
        </div>
      </header>

      {/* Message List */}
      <MessageList messages={messages} thinking={thinking} liveSteps={liveSteps} onSend={send} />

      {/* Centered Pill Input Pack */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-[#131314] via-[#131314]/90 to-transparent pt-12 pb-24 md:pb-6 z-10 pointer-events-none">
        <div className="pointer-events-auto">
          {interruptedAt && (
            <div className="max-w-3xl mx-auto px-4 mb-2">
              <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 flex items-center gap-3 text-[12px]">
                <span className="text-amber-400 shrink-0">⚠</span>
                <span className="flex-1 text-amber-100/90">
                  That request was interrupted (likely a server restart).
                  Want me to retry it?
                </span>
                <button
                  onClick={retryInterrupted}
                  disabled={!connected}
                  className="px-3 py-1 rounded-full bg-[var(--accent)] text-white text-[11px] font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Retry
                </button>
                <button
                  onClick={dismissInterrupted}
                  className="text-[var(--fg-mute)] hover:text-white text-[11px] px-2"
                  aria-label="Dismiss"
                >
                  ✕
                </button>
              </div>
            </div>
          )}
          <Composer
            onSend={send}
            disabled={!connected}
            recording={recording}
            onTalkStart={onTalkStart}
            onTalkEnd={onTalkEnd}
          />
        </div>
      </div>
    </div>
  );
}

function cryptoId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2);
}

function normalizeContent(s: string): string {
  return (s || "").trim();
}

// Merge server-fetched messages with the local list. Local messages are
// authoritative for ordering and step traces; server messages fill any gap
// (typically the last assistant_final that the client missed because the
// WebSocket dropped before the frame arrived).
function mergeServerMessages(local: Message[], rows: ServerMessageRow[]): Message[] {
  const localKeys = new Set(
    local.map((m) => `${m.role}|${normalizeContent(m.text)}`),
  );
  const merged: Message[] = [...local];
  for (const row of rows) {
    if (row.role !== "user" && row.role !== "assistant") continue;
    const key = `${row.role}|${normalizeContent(row.content)}`;
    if (localKeys.has(key)) continue;
    merged.push({
      id: row.id,
      role: row.role as "user" | "assistant",
      text: row.content,
      agent: row.metadata?.role_used,
    });
    localKeys.add(key);
  }
  return merged;
}
