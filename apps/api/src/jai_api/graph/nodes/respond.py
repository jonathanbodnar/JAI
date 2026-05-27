"""Primary JAI voice — Kimi K2.6.

The orchestrator routes routine turns here. This node is the user-facing
personality: warm, specific, grounded in the retrieved memory. Heavier
than Flash but still a single call with no tool use, so latency is
~1.5–3s including network.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import structlog
from langchain_core.messages import AIMessage, SystemMessage

from ...models.registry import Role, chat_for
from ..prompts import RESPOND_SYSTEM
from ..state import JaiState
from .orchestrator import _format_memory
from .skill_executor import _trim_for_synthesis

log = structlog.get_logger()

# Skill output older than this is too stale to assume the user is
# referring to it. Most conversational refinements happen within a few
# minutes of seeing the original answer.
_SKILL_CONTEXT_TTL = timedelta(minutes=20)


def _format_skill_context(state: JaiState) -> str:
    """If the most recent skill run is still fresh, surface its RAW
    output (and the canvas, if any) so the responder can refine,
    expand, or otherwise act on it without forgetting what just
    happened. Without this, follow-ups like "longer please", "shorter",
    "drop the third one" come back with "I don't see my previous reply".
    """
    output = state.get("skill_output")
    canvas = state.get("canvas")
    if not output and not canvas:
        return ""
    when_str = state.get("skill_output_at")
    if when_str:
        try:
            when = datetime.fromisoformat(when_str)
            if datetime.now(timezone.utc) - when > _SKILL_CONTEXT_TTL:
                return ""
        except Exception:
            # Bad timestamp: still surface — better to over-share recent
            # context than to drop it entirely.
            pass

    skill_name = state.get("skill_name") or "unknown skill"
    summary = state.get("skill_output_summary") or ""

    sections: list[str] = []
    sections.append(f"Skill: {skill_name}")
    if summary:
        sections.append(f"Last chat reply you gave the user (the short bubble):\n{summary[:1500]}")

    # Surface the canvas verbatim when it's the user's "real" output —
    # the chat bubble is often a one-liner ("Drafted email to X") while
    # the canvas holds the actual content the user is asking about.
    if isinstance(canvas, dict):
        kind = canvas.get("kind") or "artifact"
        title = canvas.get("title") or ""
        content = (canvas.get("content") or "").strip()
        if content:
            meta = canvas.get("metadata") or {}
            meta_lines = ""
            if isinstance(meta, dict) and meta:
                meta_pairs = [
                    f"- {k}: {v}"
                    for k, v in meta.items()
                    if v not in (None, "", []) and isinstance(v, (str, int, float, bool))
                ]
                if meta_pairs:
                    meta_lines = "\n".join(meta_pairs) + "\n\n"
            # Cap canvas body so a 30k-char document doesn't blow the context
            body = content if len(content) <= 8000 else content[:8000] + "\n…(truncated)"
            sections.append(
                f"Canvas the user is looking at ({kind} — {title}):\n"
                f"{meta_lines}---\n{body}\n---"
            )

    if output:
        trimmed = _trim_for_synthesis(output)
        try:
            payload = json.dumps(trimmed, default=str, indent=2)
        except Exception:
            payload = str(trimmed)
        if len(payload) > 6000:
            payload = payload[:6000] + "\n…(truncated)"
        sections.append(f"Raw skill data still available:\n```json\n{payload}\n```")
    return "\n\n".join(sections)


def _last_assistant_text(state: JaiState) -> str:
    """Pull the most recent assistant message body out of state.

    Models occasionally ignore the bottom of a long message history;
    surfacing the last assistant turn as a dedicated system block
    eliminates that failure mode for continuation-style replies
    ("saas", "just curious", "do it", "not sure").
    """
    messages = state.get("messages") or []
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None)
        role = None
        content = None
        if msg_type == "ai":
            role = "assistant"
            content = getattr(msg, "content", "")
        elif isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
        if role == "assistant" and isinstance(content, str) and content.strip():
            return content.strip()
    return ""


async def respond(state: JaiState) -> dict:
    # streaming=True so the WebSocket layer can forward per-token chunks
    # to the UI via stream_mode="messages". Without this, Kimi's full
    # response has to complete before the user sees anything — that's
    # 30–90s on a heavy turn and reads as "stuck".
    llm = chat_for(Role.RESPOND, temperature=0.5, streaming=True)

    fastlane = bool(state.get("casual_fastlane"))

    # On the casual fast-lane we deliberately skipped retrieval, so the
    # memory block is guaranteed empty — don't bother formatting it or
    # injecting an empty "RETRIEVED MEMORY" section that just confuses
    # the LLM.
    if fastlane:
        memory_block = ""
    else:
        memory_block = _format_memory(state)
    skill_block = _format_skill_context(state)

    sys_text = RESPOND_SYSTEM
    if memory_block:
        sys_text += "\n\n=== RETRIEVED MEMORY ===\n" + memory_block

    # Surface the prior assistant message as its own block, ALWAYS
    # (not just on the fast-lane). The CONTINUATION rules in the base
    # system prompt are meaningless if the model drops the bottom of
    # the message history — putting the verbatim prior turn here means
    # Kimi cannot miss it.
    prev_assistant = _last_assistant_text(state)
    if prev_assistant:
        # Cap so a 5k-char canvas answer doesn't blow the budget.
        snippet = prev_assistant if len(prev_assistant) <= 2000 else prev_assistant[:2000] + "\n…(truncated)"
        sys_text += (
            "\n\n=== PREVIOUS ASSISTANT MESSAGE (what the user is replying to) ===\n"
            f"{snippet}\n"
            "\nIf the user's current message is short or ambiguous, "
            "interpret it as a direct continuation of THIS message above. "
            "Do not ask for clarification when the antecedent is obvious "
            "from this prior turn."
        )

    if skill_block:
        sys_text += (
            "\n\n=== RECENT SKILL / CANVAS CONTEXT (in scope for follow-ups) ===\n"
            + skill_block
            + "\n\nThis is the artifact the user JUST saw. Treat their current "
            "message as a follow-up about it unless they obviously change topic. "
            "Examples that ARE follow-ups:\n"
            "  - Refinements: \"only from real people\", \"not junk\", \"drop "
            "the third one\", \"without the GitHub noise\".\n"
            "  - Length changes: \"longer please\", \"shorter\", \"tl;dr\", "
            "\"go deeper\", \"more detail\", \"elaborate\", \"expand on that\".\n"
            "  - Edits to a draft: \"more casual\", \"add a P.S.\", \"reword "
            "the opener\", \"change the subject\", \"make it punchier\".\n"
            "  - Conditional rules: \"if it's X, do Y\" (apply to the artifact "
            "going forward — don't ask to see the data again).\n"
            "Re-derive the answer from the canvas / raw data above. DO NOT "
            "say \"I don't see my previous reply\" — it is right above; read "
            "it. DO NOT redirect them to re-run a skill. DO NOT ask them to "
            "re-paste data you already have. Keep the same structure (grouped "
            "by account, dated, draft format, etc.) and apply their constraint. "
            "Only ignore this section if the user clearly changes topic."
        )

    sys = SystemMessage(content=sys_text)

    # 30 messages ≈ 15 turns of back-and-forth — generous enough to
    # cover a multi-step thread (draft → tweak → tweak → send) while
    # staying well inside Kimi's context budget.
    window = (state.get("messages") or [])[-30:]

    res = await llm.ainvoke([sys, *window])
    text = res.content if isinstance(res.content, str) else str(res.content)
    text = (text or "").strip()

    if not text:
        text = "I'm here — what do you want to dig into?"

    return {
        "final_text": text,
        "messages": [AIMessage(content=text)],
        "role_used": "respond",
    }
