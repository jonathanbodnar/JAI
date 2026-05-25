"""Fast-path intent matcher.

Runs immediately after `ingest`, *before* retrieval and the orchestrator.
If the user's text matches an obvious built-in (add_task / add_note),
we execute it directly and short-circuit straight to `persist`. This
prevents the LLM orchestrator from drafting "I need your Todoist token"
replies based on stale conversation context — the user simply wanted a
row in JAI's own tasks/notes table.

The router (`route_after_fast_intent`) reads `state['route']`:
  - "respond" → we handled it; skip retrieve/orchestrator entirely
  - anything else → normal flow
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage

from ...skills.builtin import try_builtin
from ..state import JaiState

log = structlog.get_logger()


async def fast_intent(state: JaiState) -> dict:
    user_id = state.get("user_id")
    text = (state.get("input_text") or "").strip()
    if not user_id or not text:
        return {}

    try:
        hit = await try_builtin(user_id=user_id, text=text)
    except Exception as e:
        log.warning("fast_intent.builtin_failed", error=str(e))
        return {}

    if not hit:
        return {}

    log.info("fast_intent.hit", kind=hit.kind, record=hit.record_id)
    return {
        "route": "respond",
        "route_reason": f"built-in {hit.kind}",
        "final_text": hit.response,
        "messages": [AIMessage(content=hit.response)],
        "role_used": f"builtin:{hit.kind}",
    }
