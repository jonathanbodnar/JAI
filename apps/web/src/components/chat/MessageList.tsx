"use client";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Sparkles, Copy, Check, ArrowUpRight, Flame, ClipboardList, Network, StickyNote } from "lucide-react";
import { supabase } from "@/lib/supabase";

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  agent?: string;
};

export function MessageList({
  messages,
  thinking,
  onSend,
}: {
  messages: Message[];
  thinking: boolean;
  onSend?: (text: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  return (
    <div ref={ref} className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-6 pb-28">
      {messages.length === 0 && (
        <Empty onSend={onSend} />
      )}
      <div className="max-w-3xl mx-auto space-y-8">
        {messages.map((m) => (
          <Bubble key={m.id} m={m} />
        ))}
        {thinking && <Thinking />}
      </div>
    </div>
  );
}

function Bubble({ m }: { m: Message }) {
  const isUser = m.role === "user";
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(m.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={cn("flex flex-col", isUser ? "items-end" : "items-start")}>
      <div className={cn("flex gap-3.5 w-full", isUser ? "flex-row-reverse" : "flex-row")}>
        {/* Avatar */}
        {!isUser && (
          <div className="shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-tr from-[#7c5cff] via-[#9b76ff] to-[#f43f5e] shadow-[0_2px_10px_rgba(124,92,255,0.3)] mt-0.5">
            <Sparkles size={14} className="text-white" />
          </div>
        )}

        <div className={cn("flex-1 min-w-0", isUser ? "flex justify-end" : "")}>
          {/* Main content body */}
          <div
            className={cn(
              "text-[15px] leading-relaxed transition-all duration-200",
              isUser
                ? "bg-[#1e1f20] text-[#ececef] rounded-[24px] rounded-tr-sm px-5 py-3 max-w-[85%] whitespace-pre-wrap shadow-sm border border-[#2d2f31]/60"
                : "text-[#ececef] pl-1.5 md:pl-0",
            )}
          >
            {/* Show specific subagent/skills tag above non-user answers */}
            {!isUser && m.agent && m.agent !== "orchestrator" && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase bg-[#1e1f20] text-[var(--accent)] border border-[#2d2f31] mb-2.5">
                {m.agent}
              </span>
            )}

            {isUser ? m.text : <Markdown text={m.text} />}
          </div>

          {/* Action buttons (Copy, etc.) under the assistant message */}
          {!isUser && (
            <div className="flex items-center gap-1.5 mt-2.5 ml-1.5 md:ml-0 opacity-0 hover:opacity-100 focus-within:opacity-100 transition-opacity duration-200">
              <button
                onClick={copyToClipboard}
                className="p-2 rounded-full hover:bg-[#1e1f20] text-[#8e918f] hover:text-white transition-colors border border-transparent hover:border-[#2d2f31]"
                title="Copy response"
              >
                {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Markdown({ text }: { text: string }) {
  return (
    <div
      className="
        prose-chat
        text-[#ececef]
        [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0
        [&_ul]:my-2 [&_ul]:pl-6 [&_ul]:list-disc
        [&_ol]:my-2 [&_ol]:pl-6 [&_ol]:list-decimal
        [&_li]:my-1 [&_li_p]:my-0
        [&_h1]:text-lg [&_h1]:font-bold [&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-white
        [&_h2]:text-base [&_h2]:font-bold [&_h2]:mt-4 [&_h2]:mb-1.5 [&_h2]:text-white
        [&_h3]:text-[15px] [&_h3]:font-bold [&_h3]:mt-3 [&_h3]:mb-1 [&_h3]:text-zinc-200
        [&_strong]:font-bold [&_strong]:text-white [&_em]:italic
        [&_a]:text-[var(--accent)] [&_a]:underline [&_a]:underline-offset-4 [&_a]:decoration-1 [&_a]:hover:text-white
        [&_code]:bg-[#1e1f20] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[13px] [&_code]:font-mono [&_code]:text-[#f43f5e] [&_code]:border [&_code]:border-[#2d2f31]/40
        [&_pre]:bg-[#1e1f20] [&_pre]:p-3.5 [&_pre]:rounded-2xl [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:border [&_pre]:border-[#2d2f31]
        [&_pre>code]:bg-transparent [&_pre>code]:p-0 [&_pre>code]:text-[13px] [&_pre>code]:leading-relaxed [&_pre>code]:text-zinc-100
        [&_blockquote]:border-l-3 [&_blockquote]:border-[var(--accent)] [&_blockquote]:pl-3.5 [&_blockquote]:text-[#8e918f] [&_blockquote]:my-2.5 [&_blockquote]:italic
        [&_hr]:border-[#2d2f31] [&_hr]:my-4
        [&_table]:my-3 [&_table]:text-[14px] [&_table]:border-collapse [&_table]:w-full
        [&_th]:border [&_th]:border-[#2d2f31] [&_th]:px-3 [&_th]:py-1.5 [&_th]:bg-[#1e1f20] [&_th]:text-left [&_th]:font-semibold [&_th]:text-white
        [&_td]:border [&_td]:border-[#2d2f31] [&_td]:px-3 [&_td]:py-1.5
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
    <div className="flex gap-3.5">
      <div className="shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-tr from-[#7c5cff] via-[#9b76ff] to-[#f43f5e] shadow-[0_2px_10px_rgba(124,92,255,0.3)]">
        <Sparkles size={14} className="text-white animate-spin [animation-duration:3s]" />
      </div>
      <div className="flex items-center gap-1.5 pl-1.5 md:pl-0 mt-2">
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:-200ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce [animation-delay:-100ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce" />
      </div>
    </div>
  );
}

function Empty({ onSend }: { onSend?: (text: string) => void }) {
  const [userName, setUserName] = useState("Jonathan");

  useEffect(() => {
    // Dynamically retrieve user name
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data: sub } = supabase().auth.onAuthStateChange((_event: any, session: any) => {
      if (session?.user) {
        const name = session.user.user_metadata?.full_name || session.user.email?.split("@")[0] || "there";
        setUserName(name.charAt(0).toUpperCase() + name.slice(1));
      }
    });
    // Fallback try once
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    supabase().auth.getUser().then(({ data }: any) => {
      if (data?.user) {
        const name = data.user.user_metadata?.full_name || data.user.email?.split("@")[0] || "there";
        setUserName(name.charAt(0).toUpperCase() + name.slice(1));
      }
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const suggestions = [
    {
      title: "Rundown",
      desc: "Good morning schedule & rundown",
      query: "What is on my agenda today?",
      Icon: ClipboardList,
      color: "text-blue-400",
    },
    {
      title: "Context Graph",
      desc: "Summarize what you know about me",
      query: "Give me a summary of what you know about my identity and goals from my context",
      Icon: Network,
      color: "text-emerald-400",
    },
    {
      title: "Task Breakdown",
      desc: "Help me check my open tasks",
      query: "Show me a breakdown of all my open tasks.",
      Icon: Flame,
      color: "text-amber-400",
    },
    {
      title: "Jot Ideas",
      desc: "Take a note about my thoughts",
      query: "Take a note about my ideas: ",
      Icon: StickyNote,
      color: "text-purple-400",
    },
  ];

  return (
    <div className="max-w-2xl mx-auto flex flex-col justify-center min-h-[72dvh] py-12 px-2 select-none">
      {/* Dynamic Greetings */}
      <div className="space-y-1 mb-10">
        <h1 className="text-4xl sm:text-5xl md:text-[54px] font-bold tracking-tight bg-gradient-to-r from-blue-400 via-purple-400 via-pink-400 to-amber-400 bg-clip-text text-transparent pb-1">
          Hello, {userName}
        </h1>
        <h2 className="text-3xl sm:text-4xl md:text-[44px] font-bold tracking-tight text-[#303134]">
          How can I help you today?
        </h2>
      </div>

      {/* Suggested Starters Grid */}
      <div className="grid grid-cols-2 gap-3.5">
        {suggestions.map((s, idx) => (
          <button
            key={idx}
            onClick={() => onSend?.(s.query)}
            className="flex flex-col justify-between items-start text-left p-4 rounded-2xl bg-[#1e1f20] hover:bg-[#2a2b2d] border border-transparent hover:border-[#2d2f31] transition-all duration-200 group h-[132px] w-full shadow-sm"
          >
            <div className="space-y-1 w-full">
              <p className="text-sm font-semibold text-zinc-100 group-hover:text-[var(--accent)] transition-colors">
                {s.title}
              </p>
              <p className="text-xs text-[#8e918f] font-medium leading-normal line-clamp-2">
                {s.desc}
              </p>
            </div>
            <div className="w-full flex justify-between items-center mt-2">
              <s.Icon size={16} className={s.color} />
              <div className="p-1 rounded-full bg-[#131314] opacity-0 group-hover:opacity-100 transition-opacity duration-200 border border-[#2d2f31]">
                <ArrowUpRight size={12} className="text-white" />
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
