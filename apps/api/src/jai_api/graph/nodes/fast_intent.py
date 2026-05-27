"""Fast-path intent matcher + casual-chat lane.

Runs immediately after `ingest`. Two short-circuits live here so the
hot path skips work that doesn't change the answer:

  1. Builtin tasks/notes/etc. — try_builtin handles them and we jump
     straight to `persist`.
  2. Casual short follow-ups — "saas", "not sure", "yes do it",
     "tell me more" — we skip retrieval + orchestrator and go straight
     to `respond`. The 30-message history already supplies the
     conversational context; an extra Mem0/Qdrant/Neo4j round-trip
     plus a Flash routing call adds 1.5-3s of latency that doesn't
     improve the answer. ChatGPT/Gemini don't do RAG per turn for
     this exact reason.

The router (`route_after_fast_intent`) reads `state['route']`:
  - "respond" → we handled it; skip retrieve/orchestrator entirely
  - anything else → normal flow
"""

from __future__ import annotations

import re

import structlog
from langchain_core.messages import AIMessage

from ...skills.builtin import try_builtin
from ..state import JaiState

log = structlog.get_logger()


# Verbs/keywords that should ALWAYS pull memory + go through the
# orchestrator, even on short messages. Mostly action requests where
# the orchestrator's skill-vs-respond decision actually matters.
_NON_CASUAL_HINTS = re.compile(
    r"\b("
    # Outbound actions
    r"send|draft|write|compose|reply|email|gmail|calendar|meeting|"
    r"event|invite|schedule|free time|free slot|drive|sheet|doc|"
    # Data queries
    r"search|find|list|show me|read|fetch|pull|check|look up|"
    # KPIs/tracking
    r"track|kpi|metric|goal|progress|"
    # Tasks/notes (these would be caught by try_builtin anyway, but
    # if phrasing varies we still want orchestrator routing)
    r"task|note|reminder|todo|"
    # Strategy/reflection trigger words
    r"strategy|strategize|plan|reflect|introspect"
    r")\b",
    re.IGNORECASE,
)


# Tight upper bound on what we treat as "casual short follow-up".
# Beyond ~140 chars the user is usually asking something new with
# enough specificity that retrieval might actually help.
_CASUAL_MAX_CHARS = 140


def _is_casual_followup(state: JaiState, text: str) -> bool:
    """True if this turn can safely skip retrieve + orchestrator.

    Requires:
      - A short message (≤140 chars).
      - At least one prior assistant turn in scope (so respond has
        something to continue from).
      - No outbound-action keywords (drafts, calendar, sheets, etc.) —
        those need orchestrator routing to land at the right skill.
      - No URLs / emails / @mentions — those are often action triggers
        even when the rest of the message is short.
    """
    if len(text) > _CASUAL_MAX_CHARS:
        return False
    if _NON_CASUAL_HINTS.search(text):
        return False
    if "://" in text or "@" in text:
        return False

    messages = state.get("messages") or []
    has_prior_assistant = any(
        getattr(m, "type", None) == "ai"
        or (isinstance(m, dict) and m.get("role") == "assistant")
        for m in messages
    )
    if not has_prior_assistant:
        return False

    return True


async def fast_intent(state: JaiState) -> dict:
    user_id = state.get("user_id")
    text = (state.get("input_text") or "").strip()
    if not user_id or not text:
        return {}

    try:
        hit = await try_builtin(user_id=user_id, text=text)
    except Exception as e:
        log.warning("fast_intent.builtin_failed", error=str(e))
        hit = None

    if hit:
        log.info("fast_intent.hit", kind=hit.kind, record=hit.record_id)
        return {
            "route": "respond",
            "route_reason": f"built-in {hit.kind}",
            "final_text": hit.response,
            "messages": [AIMessage(content=hit.response)],
            "role_used": f"builtin:{hit.kind}",
        }

    # Casual fast-lane — direct to respond.
    if _is_casual_followup(state, text):
        log.info("fast_intent.casual_fastlane", text=text[:60])
        return {
            "route": "respond",
            "route_reason": "casual short follow-up — bypass retrieval",
            # We set a flag respond can read to skip the heavy skill-context
            # block; the message history alone is enough here.
            "casual_fastlane": True,
        }

    return {}
