"""Write the turn to Mem0 + Qdrant after responding.

Critical decisions for latency + signal-to-noise:

  1. Persist runs IN BACKGROUND inside the node (we fire `asyncio.create_task`
     and return immediately). LangGraph would otherwise block the response
     on Qdrant + Mem0 writes which can add 1–3s per turn.
  2. We DO NOT push every chat turn to Mem0 or Qdrant. Mem0 should only see
     content that's plausibly a durable identity fact (beliefs, preferences,
     facts about the user, their companies, recurring themes). Chat about
     today's weather, "what's on my list", or "add a task X" is noise and
     pollutes recall. We use a cheap heuristic + the orchestrator's
     `role_used` to gate writes.
"""

from __future__ import annotations

import asyncio
import re

import structlog

from ...memory.mem0 import JaiMem0
from ...memory.qdrant import JaiQdrant
from ..state import JaiState

log = structlog.get_logger()


# Phrases that signal an obviously-throwaway turn we don't want in long-term
# memory (Mem0 / Qdrant). Tasks/notes/morning-briefings have their own home.
_NOISE_RE = re.compile(
    r"^\s*(?:"
    r"good\s*morning|morning|gm|hello|hi|hey|sup|"
    r"thanks?|thank\s+you|cool|nice|ok|okay|got\s+it|sounds?\s+good|"
    r"what['\u2019]?s?\s+(?:up|on|today|the\s+plan)|"
    r"what\s+do\s+i\s+have|what\s+time|"
    r"add\s+(?:a\s+)?(?:task|todo|note)|note:|todo:|remind\s+me|"
    r"(?:can|could)\s+you\s+(?:remove|delete|clear|forget)|"
    r"(?:show|give|tell)\s+me\s+my\s+(?:tasks?|todos?|notes?|agenda)|"
    r"who\s+is|who\s+was|how\s+are\s+you|test|hi\s+jai"
    r")[\s?!.,]*$",
    re.IGNORECASE,
)

# A turn is "meaningful" if it's long enough OR contains identity-shaped
# verbs ("I believe", "I want", "my company", "we decided", "I'm working on").
_MEANINGFUL_RE = re.compile(
    r"\b("
    r"i\s+(?:believe|think|feel|want|need|love|hate|prefer|decided|plan|"
    r"realized|learned|figured|noticed|fear|worry|trust|distrust|"
    r"work\s+on|focus\s+on|care\s+about|am\s+(?:building|launching|hiring))"
    r"|my\s+(?:company|business|team|client|customer|wife|husband|partner|"
    r"goal|vision|values?|belief|strategy|approach|product|service)"
    r"|we\s+(?:decided|launched|hired|signed|built|chose|pivoted)"
    r"|(?:shoutout|ftr|cal\s*pal)\b"
    r")",
    re.IGNORECASE,
)


def _is_meaningful(user_text: str, role_used: str | None) -> bool:
    """Decide if this turn should write to Mem0 / long-term Qdrant.

    Builtin hits (add_task, add_note, morning_briefing, schedule_created)
    are always rejected — they have their own data home in Postgres.
    """
    if role_used and role_used.startswith("builtin:"):
        return False
    text = (user_text or "").strip()
    if len(text) < 20:
        return False
    if _NOISE_RE.match(text):
        return False
    if _MEANINGFUL_RE.search(text):
        return True
    # 200+ char turns are usually substantive — let them through.
    return len(text) > 200


def make_persist(mem0: JaiMem0, qdrant: JaiQdrant):
    async def persist(state: JaiState) -> dict:
        user_id = state.get("user_id")
        user_text = state.get("input_text", "")
        assistant_text = state.get("final_text", "")
        role_used = state.get("role_used")
        if not (user_id and (user_text or assistant_text)):
            return {}

        meaningful = _is_meaningful(user_text, role_used)
        log.info(
            "persist.decision",
            meaningful=meaningful,
            role_used=role_used,
            user_text_len=len(user_text or ""),
        )

        async def _run_writes():
            tasks = []
            # Mem0 — only for plausibly-durable identity content.
            if meaningful and mem0.enabled and user_text:
                tasks.append(
                    mem0.add(
                        user_id,
                        [
                            {"role": "user", "content": user_text},
                            {"role": "assistant", "content": assistant_text},
                        ],
                        metadata={"role_used": role_used},
                    )
                )
            # Qdrant — store conversation turns only if meaningful, so search
            # results aren't drowned in "good morning"s and task confirmations.
            if meaningful and user_text:
                tasks.append(
                    qdrant.add(
                        user_id=user_id,
                        text=user_text,
                        source="conversation_user",
                        metadata={"role_used": role_used},
                    )
                )
            if meaningful and assistant_text:
                tasks.append(
                    qdrant.add(
                        user_id=user_id,
                        text=assistant_text,
                        source="conversation_assistant",
                        metadata={"role_used": role_used},
                    )
                )

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, Exception):
                        log.warning("persist.partial_failure", error=str(r))

        # Fire-and-forget so the chat doesn't wait on Qdrant/Mem0.
        asyncio.create_task(_run_writes())
        return {}

    return persist
