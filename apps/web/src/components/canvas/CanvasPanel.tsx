"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  X,
  Send,
  Pencil,
  Copy,
  Check,
  Mail,
  FileText,
  Code2,
  ListChecks,
  Sparkles,
} from "lucide-react";
import { useCanvas, canvasStore } from "@/lib/canvas";
import type { CanvasAction, CanvasPayload } from "@/lib/ws";
import { cn } from "@/lib/cn";

/**
 * Side panel that holds long-form artifacts produced by skills —
 * email drafts, documents, code, plans — instead of stuffing them
 * into a chat bubble. Same general idea as ChatGPT Canvas.
 *
 * Activation: anything in the app can call `canvasStore.open(payload)`.
 *   - Chat WS handler does it when a skill returns a canvas.
 *   - Chat bubbles do it when the user clicks "Open canvas".
 *
 * Actions fire by inserting text into the chat composer via a global
 * event (`jai:canvas-action`) which ChatView listens for.
 */
export function CanvasPanel() {
  const { open, payload } = useCanvas();
  const [editing, setEditing] = useState(false);
  const [draftBody, setDraftBody] = useState("");

  useEffect(() => {
    if (payload) setDraftBody(payload.content);
    setEditing(false);
    // Re-seed the local draft state any time a new payload is shown.
    // We don't want to refire on `editing` because that's owned here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload?.title, payload?.kind, payload?.content]);

  if (!payload) return null;

  const close = () => canvasStore.close();

  const handleAction = (action: CanvasAction) => {
    // The action just queues text in the composer (or sends it immediately
    // for non-template actions like "send"). ChatView listens.
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent("jai:canvas-action", {
        detail: {
          actionId: action.id,
          prompt: action.prompt,
          immediate: !action.is_template,
          canvasKind: payload.kind,
        },
      }),
    );
    if (!action.is_template) {
      // The action is a fire-and-forget like "send draft". Close so
      // the chat can take focus.
      canvasStore.close();
    }
  };

  return (
    <>
      {/* Backdrop — only visible on mobile because desktop reveals the
          canvas alongside the chat, not on top of it. */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/60 transition-opacity duration-200 md:hidden",
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
        )}
        onClick={close}
      />

      <aside
        className={cn(
          "fixed top-0 right-0 z-50 h-dvh bg-[#131314] border-l border-[#2d2f31]",
          "shadow-[-12px_0_40px_rgba(0,0,0,0.35)] flex flex-col",
          "w-full md:w-[min(640px,55vw)]",
          "transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
        aria-hidden={!open}
      >
        <Header payload={payload} onClose={close} />

        <div className="flex-1 overflow-y-auto px-5 md:px-8 py-5 md:py-7">
          <Body
            payload={payload}
            editing={editing}
            draftBody={draftBody}
            onChangeDraftBody={setDraftBody}
          />
        </div>

        <Footer
          payload={payload}
          editing={editing}
          onToggleEdit={() => setEditing((v) => !v)}
          onAction={handleAction}
          draftBody={draftBody}
        />
      </aside>
    </>
  );
}

function Header({
  payload,
  onClose,
}: {
  payload: CanvasPayload;
  onClose: () => void;
}) {
  const Icon = kindIcon(payload.kind);
  return (
    <div className="flex items-center gap-3 px-5 md:px-8 py-4 border-b border-[#2d2f31] bg-[#0f0f10]">
      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-tr from-[#7c5cff] via-[#9b76ff] to-[#f43f5e] shadow-[0_2px_10px_rgba(124,92,255,0.3)]">
        <Icon size={14} className="text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[11px] uppercase tracking-wider font-bold text-[var(--accent)]">
          {kindLabel(payload.kind)}
        </div>
        <div className="text-[15px] font-semibold text-white truncate">
          {payload.title}
        </div>
      </div>
      <button
        onClick={onClose}
        className="p-2 rounded-full hover:bg-[#1e1f20] text-[#8e918f] hover:text-white transition-colors"
        title="Close canvas"
      >
        <X size={18} />
      </button>
    </div>
  );
}

function Body({
  payload,
  editing,
  draftBody,
  onChangeDraftBody,
}: {
  payload: CanvasPayload;
  editing: boolean;
  draftBody: string;
  onChangeDraftBody: (v: string) => void;
}) {
  if (payload.kind === "email_draft") {
    const meta = (payload.metadata || {}) as Record<string, unknown>;
    return (
      <div className="space-y-5">
        <div className="space-y-2 text-[14px]">
          <Row label="From" value={String(meta.from ?? "—")} />
          <Row label="To" value={String(meta.to ?? "—")} />
          <Row label="Subject" value={String(meta.subject ?? "(no subject)")} />
          {meta.tone ? <Row label="Tone" value={String(meta.tone)} /> : null}
          {meta.saved_to ? (
            <div className="text-[12px] text-[#8e918f] pt-1">
              {String(meta.saved_to)}
            </div>
          ) : null}
        </div>
        <div className="h-px bg-[#2d2f31]" />
        {editing ? (
          <textarea
            value={draftBody}
            onChange={(e) => onChangeDraftBody(e.target.value)}
            className="w-full min-h-[280px] bg-[#0f0f10] border border-[#2d2f31] rounded-2xl p-4 text-[14.5px] leading-relaxed text-[#ececef] focus:outline-none focus:border-[var(--accent)] resize-y"
            spellCheck
          />
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-[14.5px] leading-relaxed text-[#ececef]">
            {payload.content || "(empty body)"}
          </pre>
        )}
      </div>
    );
  }

  if (payload.kind === "code") {
    return (
      <pre className="bg-[#0f0f10] border border-[#2d2f31] rounded-2xl p-4 overflow-x-auto text-[13.5px] leading-relaxed font-mono text-zinc-100">
        <code>{payload.content}</code>
      </pre>
    );
  }

  // document / plan / list — render as markdown
  return (
    <div
      className="
        prose-chat text-[#ececef]
        [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0
        [&_ul]:my-2 [&_ul]:pl-6 [&_ul]:list-disc
        [&_ol]:my-2 [&_ol]:pl-6 [&_ol]:list-decimal
        [&_li]:my-1
        [&_h1]:text-xl [&_h1]:font-bold [&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-white
        [&_h2]:text-lg [&_h2]:font-bold [&_h2]:mt-4 [&_h2]:mb-1.5 [&_h2]:text-white
        [&_h3]:text-base [&_h3]:font-bold [&_h3]:mt-3 [&_h3]:mb-1 [&_h3]:text-zinc-200
        [&_strong]:font-bold [&_strong]:text-white [&_em]:italic
        [&_a]:text-[var(--accent)] [&_a]:underline
        [&_code]:bg-[#1e1f20] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[13px]
        [&_pre]:bg-[#0f0f10] [&_pre]:p-4 [&_pre]:rounded-2xl [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:border [&_pre]:border-[#2d2f31]
        [&_blockquote]:border-l-3 [&_blockquote]:border-[var(--accent)] [&_blockquote]:pl-3.5 [&_blockquote]:text-[#8e918f] [&_blockquote]:italic
      "
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {payload.content || "_(empty)_"}
      </ReactMarkdown>
    </div>
  );
}

function Footer({
  payload,
  editing,
  onToggleEdit,
  onAction,
  draftBody,
}: {
  payload: CanvasPayload;
  editing: boolean;
  onToggleEdit: () => void;
  onAction: (action: CanvasAction) => void;
  draftBody: string;
}) {
  const [copied, setCopied] = useState(false);
  const actions = payload.actions || [];

  const handleCopy = () => {
    const text =
      payload.kind === "email_draft" && editing ? draftBody : payload.content;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="border-t border-[#2d2f31] bg-[#0f0f10] px-5 md:px-8 py-3.5 flex items-center gap-2 flex-wrap">
      <button
        onClick={handleCopy}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12.5px] font-medium text-[#8e918f] hover:text-white border border-[#2d2f31] hover:border-[#3d3f41] transition-colors"
        title="Copy contents"
      >
        {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
        {copied ? "Copied" : "Copy"}
      </button>

      {payload.kind === "email_draft" && (
        <button
          onClick={onToggleEdit}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12.5px] font-medium border transition-colors",
            editing
              ? "bg-[var(--accent)]/15 border-[var(--accent)] text-white"
              : "text-[#8e918f] hover:text-white border-[#2d2f31] hover:border-[#3d3f41]",
          )}
          title="Edit locally (won't push to Gmail — use 'Refine' to ask JAI to rewrite)"
        >
          <Pencil size={13} />
          {editing ? "Done editing" : "Edit"}
        </button>
      )}

      <div className="flex-1" />

      {actions.map((a) => {
        const isPrimary = a.id === "send";
        return (
          <button
            key={a.id}
            onClick={() => onAction(a)}
            className={cn(
              "inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-[12.5px] font-semibold transition-colors",
              isPrimary
                ? "bg-[var(--accent)] text-white hover:opacity-90"
                : "border border-[#2d2f31] text-zinc-200 hover:border-[#3d3f41] hover:bg-[#1e1f20]",
            )}
          >
            {actionIcon(a.id)}
            {a.label}
          </button>
        );
      })}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <div className="w-[68px] shrink-0 text-[12px] uppercase tracking-wide font-semibold text-[#8e918f] pt-px">
        {label}
      </div>
      <div className="flex-1 min-w-0 text-[#ececef] break-words">{value}</div>
    </div>
  );
}

function kindIcon(kind: CanvasPayload["kind"]) {
  switch (kind) {
    case "email_draft":
      return Mail;
    case "code":
      return Code2;
    case "list":
      return ListChecks;
    case "plan":
      return Sparkles;
    default:
      return FileText;
  }
}

function kindLabel(kind: CanvasPayload["kind"]) {
  switch (kind) {
    case "email_draft":
      return "Email draft";
    case "code":
      return "Code";
    case "list":
      return "List";
    case "plan":
      return "Plan";
    default:
      return "Document";
  }
}

function actionIcon(id: string) {
  if (id === "send") return <Send size={13} />;
  if (id === "refine") return <Pencil size={13} />;
  return null;
}
