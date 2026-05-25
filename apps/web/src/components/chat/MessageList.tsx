"use client";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed",
          isUser
            ? "bg-[var(--accent)] text-white rounded-br-md whitespace-pre-wrap"
            : "bg-[var(--bg-elev2)] text-[var(--fg)] rounded-bl-md",
        )}
      >
        {!isUser && m.agent && m.agent !== "orchestrator" && (
          <div className="text-[10px] uppercase tracking-wider text-[var(--fg-dim)] mb-1">
            {m.agent}
          </div>
        )}
        {isUser ? m.text : <Markdown text={m.text} />}
      </div>
    </div>
  );
}

function Markdown({ text }: { text: string }) {
  return (
    <div
      className="
        prose-chat
        [&_p]:my-1.5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0
        [&_ul]:my-1.5 [&_ul]:pl-5 [&_ul]:list-disc
        [&_ol]:my-1.5 [&_ol]:pl-5 [&_ol]:list-decimal
        [&_li]:my-0.5 [&_li_p]:my-0
        [&_h1]:text-base [&_h1]:font-semibold [&_h1]:mt-3 [&_h1]:mb-1.5
        [&_h2]:text-[15px] [&_h2]:font-semibold [&_h2]:mt-3 [&_h2]:mb-1
        [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
        [&_strong]:font-semibold [&_em]:italic
        [&_a]:text-[var(--accent)] [&_a]:underline [&_a]:underline-offset-2
        [&_code]:bg-black/30 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[13px] [&_code]:font-mono
        [&_pre]:bg-black/40 [&_pre]:p-2.5 [&_pre]:rounded-lg [&_pre]:my-2 [&_pre]:overflow-x-auto
        [&_pre>code]:bg-transparent [&_pre>code]:p-0 [&_pre>code]:text-[12.5px] [&_pre>code]:leading-snug
        [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--line)] [&_blockquote]:pl-2.5 [&_blockquote]:text-[var(--fg-mute)] [&_blockquote]:my-1.5
        [&_hr]:border-[var(--line)] [&_hr]:my-2
        [&_table]:my-2 [&_table]:text-sm [&_table]:border-collapse
        [&_th]:border [&_th]:border-[var(--line)] [&_th]:px-2 [&_th]:py-1 [&_th]:bg-black/20 [&_th]:text-left
        [&_td]:border [&_td]:border-[var(--line)] [&_td]:px-2 [&_td]:py-1
      "
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
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
