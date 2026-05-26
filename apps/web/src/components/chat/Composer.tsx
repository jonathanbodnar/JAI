"use client";
import { useState, type KeyboardEvent, useRef, useEffect } from "react";
import { Send, Mic, Sparkles } from "lucide-react";
import { cn } from "@/lib/cn";

export function Composer({
  onSend,
  disabled,
  recording,
  onTalkStart,
  onTalkEnd,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  recording: boolean;
  onTalkStart: () => void;
  onTalkEnd: () => void;
}) {
  const [v, setV] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fired = useRef(false);

  const submit = () => {
    const t = v.trim();
    if (!t) return;
    onSend(t);
    setV("");
    // Reset height
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  // Auto-grow logic for textarea
  const adjustHeight = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  useEffect(() => {
    adjustHeight();
  }, [v]);

  // Pointer event handlers for Mic hold-to-talk
  const beginTalk = (e: React.PointerEvent) => {
    e.preventDefault();
    if (disabled || fired.current) return;
    fired.current = true;
    onTalkStart();
  };

  const endTalk = (e: React.PointerEvent) => {
    e.preventDefault();
    if (!fired.current) return;
    fired.current = false;
    onTalkEnd();
  };

  useEffect(() => {
    const cancel = () => {
      if (fired.current) {
        fired.current = false;
        onTalkEnd();
      }
    };
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("blur", cancel);
    return () => {
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("blur", cancel);
    };
  }, [onTalkEnd]);

  return (
    <div className="max-w-3xl mx-auto w-full px-4 mb-2 select-none">
      {/* Pill capsule input container */}
      <div className={cn(
        "flex items-end gap-2.5 bg-[#1e1f20] rounded-[28px] px-4.5 py-3 border border-[#2d2f31] focus-within:border-zinc-700 transition-all duration-200 shadow-md",
        recording && "border-[var(--accent)]/50 ring-2 ring-[var(--accent)]/20"
      )}>
        {/* Text Input */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={v}
          onChange={(e) => setV(e.target.value)}
          onKeyDown={onKey}
          disabled={disabled || recording}
          placeholder={recording ? "Listening... Release to send" : "Message JAI..."}
          className="flex-1 bg-transparent resize-none outline-none text-[15px] max-h-32 text-[#e3e3e3] placeholder-[#8e918f] py-1 leading-relaxed self-center"
          style={{ height: "auto" }}
        />

        {/* Action button pack */}
        <div className="flex items-center gap-1.5 self-center shrink-0">
          {/* Unified Mic Button */}
          <button
            onPointerDown={beginTalk}
            onPointerUp={endTalk}
            onPointerLeave={endTalk}
            disabled={disabled || (v.trim().length > 0 && !recording)}
            className={cn(
              "h-10 w-10 rounded-full flex items-center justify-center transition-all duration-200 shrink-0",
              recording
                ? "bg-[var(--accent)] text-white scale-110 ptt-pulse"
                : "bg-transparent text-[#c4c7c5] hover:text-white hover:bg-zinc-800/50 active:scale-95",
              (disabled || (v.trim().length > 0 && !recording)) && "opacity-0 w-0 h-0 p-0 pointer-events-none overflow-hidden"
            )}
            title="Hold to talk"
            aria-label="Hold to talk"
          >
            <Mic size={20} />
          </button>

          {/* Send Button */}
          {v.trim() && (
            <button
              onClick={submit}
              disabled={disabled}
              className="h-10 w-10 rounded-full bg-[var(--accent)] text-white flex items-center justify-center shrink-0 shadow-lg active:scale-95 hover:bg-[#8d65ff] transition-all duration-200"
              title="Send message"
              aria-label="Send"
            >
              <Send size={16} className="ml-0.5" />
            </button>
          )}
        </div>
      </div>

      {/* Gemini-style elegant tiny disclaimer footer */}
      <p className="text-[11px] text-[#8e918f] text-center mt-2 font-medium tracking-normal flex items-center justify-center gap-1">
        <Sparkles size={11} className="text-[var(--accent)] shrink-0 opacity-80" />
        JAI can make mistakes. Verify important information.
      </p>
    </div>
  );
}
