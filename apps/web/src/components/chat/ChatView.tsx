"use client";
import { useEffect, useRef, useState } from "react";
import { ChatSocket, type ServerMsg } from "@/lib/ws";
import { PressRecorder, StreamingAudioPlayer } from "@/lib/voice";
import { api } from "@/lib/api";
import Link from "next/link";
import { Settings, Trash2, BrainCircuit } from "lucide-react";
import { MessageList, type Message } from "./MessageList";
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

export function ChatView() {
  const [messages, setMessages] = useState<Message[]>(() => loadMessages());
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [recording, setRecording] = useState(false);
  const wsRef = useRef<ChatSocket | null>(null);
  const recRef = useRef<PressRecorder | null>(null);
  const playerRef = useRef<StreamingAudioPlayer | null>(null);

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
      <header className="safe-top px-6 py-4 flex items-center justify-between border-b border-[#2d2f31] bg-[#131314]/80 backdrop-blur-xl z-20">
        <div className="flex items-center gap-3">
          {/* Logo */}
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-tr from-[#7c5cff] via-[#9b76ff] to-[#f43f5e] shadow-[0_0_15px_rgba(124,92,255,0.3)] shrink-0">
            <BrainCircuit size={18} className="text-white" />
          </div>
          {/* Model selector mimic */}
          <div className="flex flex-col">
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-1.5">
              JAI
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] font-bold text-zinc-300 border border-zinc-700/50 uppercase">
                Flash 2.0
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
      <MessageList messages={messages} thinking={thinking} onSend={send} />

      {/* Centered Pill Input Pack */}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-[#131314] via-[#131314]/90 to-transparent pt-12 pb-24 md:pb-6 z-10 pointer-events-none">
        <div className="pointer-events-auto">
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
