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
    output so the responder can refine/re-filter it instead of treating
    the user's follow-up ("not junk mail", "only from people", etc.) as
    a standalone musing.
    """
    output = state.get("skill_output")
    if not output:
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
    trimmed = _trim_for_synthesis(output)
    try:
        payload = json.dumps(trimmed, default=str, indent=2)
    except Exception:
        payload = str(trimmed)
    if len(payload) > 8000:
        payload = payload[:8000] + "\n…(truncated)"

    sections: list[str] = []
    sections.append(f"Skill: {skill_name}")
    if summary:
        sections.append(f"Last summary you gave the user:\n{summary[:1500]}")
    sections.append(f"Raw data still available for refinement:\n```json\n{payload}\n```")
    return "\n\n".join(sections)


async def respond(state: JaiState) -> dict:
    llm = chat_for(Role.RESPOND, temperature=0.5, streaming=False)
    memory_block = _format_memory(state)
    skill_block = _format_skill_context(state)

    sys_text = RESPOND_SYSTEM + "\n\n=== RETRIEVED MEMORY ===\n" + memory_block
    if skill_block:
        sys_text += (
            "\n\n=== RECENT SKILL OUTPUT (in scope for follow-ups) ===\n"
            + skill_block
            + "\n\nIf the user's current message is a refinement, filter, "
            "exclusion, or commentary about that output (e.g. \"not junk\", "
            "\"only from people\", \"without GitHub noise\", \"actually just X\"), "
            "re-derive the answer from the raw data above. Do NOT redirect them "
            "to re-run a skill — you already have the data. Keep the same "
            "structure (grouped by account, dated, etc.) and apply their "
            "constraint. If the user is clearly off-topic, ignore this section."
        )

    sys = SystemMessage(content=sys_text)

    window = (state.get("messages") or [])[-20:]

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
