"use client";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  agent?: string;
};

export function MessageList({
  messages,
  thinking,
}: {
  messages: Message[];
  thinking: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  return (
    <div ref={ref} className="flex-1 overflow-y-auto px-3 py-4 space-y-3">
      {messages.length === 0 && (
        <Empty />
      )}
      {messages.map((m) => (
        <Bubble key={m.id} m={m} />
      ))}
      {thinking && <Thinking />}
    </div>
  );
}

function Bubble({ m }: { m: Message }) {
  const isUser = m.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-[15px] leading-snug whitespace-pre-wrap",
          isUser
            ? "bg-[var(--accent)] text-white rounded-br-md"
            : "bg-[var(--bg-elev2)] text-[var(--fg)] rounded-bl-md"
        )}
      >
        {!isUser && m.agent && m.agent !== "orchestrator" && (
          <div className="text-[10px] uppercase tracking-wider text-[var(--fg-dim)] mb-1">
            {m.agent}
          </div>
        )}
        {m.text}
      </div>
    </div>
  );
}

function Thinking() {
  return (
    <div className="flex">
      <div className="bg-[var(--bg-elev2)] rounded-2xl rounded-bl-md px-4 py-3 flex gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--fg-mute)] animate-pulse [animation-delay:-200ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--fg-mute)] animate-pulse [animation-delay:-100ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--fg-mute)] animate-pulse" />
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 text-center px-6 py-12">
      <div className="text-5xl">🧠</div>
      <h2 className="text-lg font-medium">One living conversation.</h2>
      <p className="text-sm text-[var(--fg-mute)] max-w-sm">
        Hold the mic to talk. Type if you prefer. JAI remembers everything across days,
        months, and topics — and acts on your behalf when you ask.
      </p>
    </div>
  );
}
