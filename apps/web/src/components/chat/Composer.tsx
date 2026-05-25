"use client";
import { useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";

export function Composer({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [v, setV] = useState("");
  const submit = () => {
    const t = v.trim();
    if (!t) return;
    onSend(t);
    setV("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };
  return (
    <div className="flex-1 flex items-end gap-2 bg-[var(--bg)] rounded-2xl px-3 py-2 border border-[var(--line)]">
      <textarea
        rows={1}
        value={v}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={onKey}
        disabled={disabled}
        placeholder="Message JAI…"
        className="flex-1 bg-transparent resize-none outline-none text-[15px] max-h-32"
      />
      {v.trim() && (
        <button
          onClick={submit}
          disabled={disabled}
          className="p-1.5 rounded-full bg-[var(--accent)] text-white disabled:opacity-50"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
      )}
    </div>
  );
}
