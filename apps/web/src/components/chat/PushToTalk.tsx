"use client";
import { Mic } from "lucide-react";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

/** Hold-to-talk button. Press = start; release = stop. Works for touch + mouse. */
export function PushToTalk({
  recording,
  disabled,
  onStart,
  onEnd,
}: {
  recording: boolean;
  disabled?: boolean;
  onStart: () => void;
  onEnd: () => void;
}) {
  const fired = useRef(false);

  const begin = (e: React.PointerEvent) => {
    e.preventDefault();
    if (disabled || fired.current) return;
    fired.current = true;
    onStart();
  };
  const end = (e: React.PointerEvent) => {
    e.preventDefault();
    if (!fired.current) return;
    fired.current = false;
    onEnd();
  };

  // safety: if pointer cancels (incoming call, etc.) we still end
  useEffect(() => {
    const cancel = () => {
      if (fired.current) {
        fired.current = false;
        onEnd();
      }
    };
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("blur", cancel);
    return () => {
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("blur", cancel);
    };
  }, [onEnd]);

  return (
    <button
      onPointerDown={begin}
      onPointerUp={end}
      onPointerLeave={end}
      disabled={disabled}
      className={cn(
        "h-12 w-12 rounded-full flex items-center justify-center shrink-0 transition-all",
        recording
          ? "bg-[var(--accent)] text-white scale-110 ptt-pulse"
          : "bg-[var(--bg-elev2)] text-[var(--fg)] active:scale-95",
        disabled && "opacity-50"
      )}
      aria-label={recording ? "Release to send" : "Hold to talk"}
    >
      {recording ? <Mic size={22} /> : <Mic size={22} />}
    </button>
  );
}
