"use client";
import { useEffect, useRef, useState } from "react";
import { ChatSocket, type ServerMsg } from "@/lib/ws";
import { PressRecorder, StreamingAudioPlayer } from "@/lib/voice";
import Link from "next/link";
import { Settings, Trash2 } from "lucide-react";
import { MessageList, type Message } from "./MessageList";
import { Composer } from "./Composer";
import { PushToTalk } from "./PushToTalk";
import { cn } from "@/lib/cn";

const CHAT_KEY = "jai.chat.messages.v1";
const CHAT_MAX = 500; // cap so localStorage doesn't blow up

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
    // quota exceeded → drop oldest half and retry once
    try {
      localStorage.setItem(CHAT_KEY, JSON.stringify(msgs.slice(-Math.floor(CHAT_MAX / 2))));
    } catch {
      // give up; chat continues, just not persisted
    }
  }
}

export function ChatView() {
  // Hydrate from localStorage so the conversation survives tab switches,
  // PWA backgrounding, or accidental reloads. The backend's LangGraph
  // checkpointer is the source of truth long-term; we'll wire history
  // sync from there later.
  const [messages, setMessages] = useState<Message[]>(() => loadMessages());
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [recording, setRecording] = useState(false);
  const wsRef = useRef<ChatSocket | null>(null);
  const recRef = useRef<PressRecorder | null>(null);
  const playerRef = useRef<StreamingAudioPlayer | null>(null);

  // Persist on every change.
  useEffect(() => {
    saveMessages(messages);
  }, [messages]);

  useEffect(() => {
    const sock = new ChatSocket({
      onOpen: () => setConnected(true),
      onClose: () => setConnected(false),
      onMessage: (m: ServerMsg) => {
        switch (m.type) {
          case "user_transcript":
            setMessages((prev) => [
              ...prev,
              { id: cryptoId(), role: "user", text: m.text },
            ]);
            setThinking(true);
            break;
          case "assistant_final":
            setMessages((prev) => [
              ...prev,
              { id: cryptoId(), role: "assistant", text: m.text, agent: m.role_used },
            ]);
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
    setThinking(true);
    wsRef.current.sendText(text);
  };

  const onTalkStart = async () => {
    if (!wsRef.current) return;
    recRef.current = new PressRecorder();
    wsRef.current.sendAudioStart();
    setRecording(true);
    try {
      await recRef.current.start((chunk) => wsRef.current?.sendAudioChunk(chunk));
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: cryptoId(), role: "assistant", text: `⚠️ mic error: ${(e as Error).message}` },
      ]);
      setRecording(false);
    }
  };

  const onTalkEnd = async () => {
    setRecording(false);
    if (!recRef.current || !wsRef.current) return;
    await recRef.current.stop();
    wsRef.current.sendAudioDone();
    setThinking(true);
  };

  return (
    <div className="flex flex-col h-full">
      <header className="safe-top px-4 py-3 border-b border-[var(--line)] flex items-center justify-between">
        <h1 className="text-base font-semibold tracking-tight">JAI</h1>
        <div className="flex items-center gap-3 text-xs text-[var(--fg-mute)]">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                connected ? "bg-[var(--ok)]" : "bg-[var(--fg-dim)]"
              )}
            />
            {connected ? "live" : "connecting…"}
          </div>
          {messages.length > 0 && (
            <button
              onClick={() => {
                if (confirm("Clear local chat view? Conversation history in memory is unaffected."))
                  setMessages([]);
              }}
              aria-label="Clear chat"
              className="text-[var(--fg-mute)] hover:text-white"
              title="Clear local chat view"
            >
              <Trash2 size={16} />
            </button>
          )}
          <Link href="/settings" aria-label="Settings" className="text-[var(--fg-mute)] hover:text-white">
            <Settings size={18} />
          </Link>
        </div>
      </header>

      <MessageList messages={messages} thinking={thinking} />

      <div className="border-t border-[var(--line)] bg-[var(--bg-elev)]">
        <div className="px-3 py-3 flex items-end gap-2">
          <Composer onSend={send} disabled={!connected} />
          <PushToTalk
            recording={recording}
            disabled={!connected}
            onStart={onTalkStart}
            onEnd={onTalkEnd}
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
