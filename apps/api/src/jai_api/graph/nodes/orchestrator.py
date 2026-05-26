"""The orchestrator decides what kind of turn this is.

Uses structured output so we can route deterministically. The orchestrator
ONLY routes — actual drafting lives downstream:
  - respond  → respond.py (Kimi K2.6, the JAI voice)
  - reflect  → reflect.py (Kimi K2.6)
  - strategize → strategize.py (DeepSeek)
  - tool/skill → tool_router / skill_executor
  - ask      → a one-line clarifying question is fine to draft here (Flash)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import structlog
from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from ...models.registry import Role, chat_for
from ..prompts import ORCHESTRATOR_SYSTEM
from ..state import JaiState

log = structlog.get_logger()


class OrchestratorDecision(BaseModel):
    route: Literal["respond", "reflect", "strategize", "tool", "skill", "ask"]
    reason: str = Field(description="One sentence why this route")
    draft: str | None = Field(
        default=None,
        description="ONLY populate when route is 'ask' — a single-sentence clarifying question. NEVER populate for 'respond'; the responder node handles that.",
    )


def _format_memory(state: JaiState) -> str:
    """Compact memory block — small enough to keep TTFB <1.5s on routing."""
    parts: list[str] = []
    mem0 = state.get("retrieved_mem0") or []
    if mem0:
        parts.append("Identity facts (Mem0):")
        for m in mem0[:6]:
            text = (m.get("text", "") or m.get("memory", "") or "").strip()
            if text:
                # Hard-trim — facts should already be short, but be defensive.
                parts.append(f"- {text[:200]}")
    qdrant = state.get("retrieved_qdrant") or []
    if qdrant:
        parts.append("\nUploaded context (Qdrant):")
        for q in qdrant[:5]:
            text = (q.get("text", "") or "").strip()
            if not text:
                continue
            meta = q.get("metadata") or {}
            src = meta.get("filename") or meta.get("source") or meta.get("title")
            tag = f" [{src}]" if src else ""
            snippet = text[:300] + ("…" if len(text) > 300 else "")
            parts.append(f"-{tag} {snippet}")
    graph = state.get("retrieved_graph") or []
    if graph:
        parts.append("\nGraph (Neo4j):")
        for g in graph[:4]:
            node = g.get("node", {})
            edges = g.get("edges", [])
            parts.append(
                f"- {node.get('name', node.get('id','?'))}: "
                + ", ".join(
                    f"{e['rel']}→{(e['node'] or {}).get('name', '?')}"
                    for e in edges[:3]
                )
            )
    return "\n".join(parts) if parts else "(no memory retrieved)"


_REFINEMENT_TTL = timedelta(minutes=20)


def _has_recent_skill_output(state: JaiState) -> bool:
    """True if the previous turn produced skill data that's still fresh
    enough for a follow-up to refer back to. Keeps the orchestrator
    hint cheap — no need to inspect the actual payload here.
    """
    if not state.get("skill_output"):
        return False
    when = state.get("skill_output_at")
    if not when:
        return True
    try:
        ts = datetime.fromisoformat(when)
        return datetime.now(timezone.utc) - ts < _REFINEMENT_TTL
    except Exception:
        return True


async def orchestrator(state: JaiState) -> dict:
    # Use FAST role for routing — orchestration is ~80% structured routing
    # and ~20% short-form drafts. A fast model finishes in 600–1500ms vs
    # 3–8s for Qwen Max; users feel that gap as "JAI is slow".
    llm = chat_for(Role.FAST, temperature=0.2, streaming=False)
    structured = llm.with_structured_output(OrchestratorDecision)

    memory_block = _format_memory(state)
    sys_text = ORCHESTRATOR_SYSTEM + "\n\n=== RETRIEVED MEMORY ===\n" + memory_block
    if _has_recent_skill_output(state):
        skill_name = state.get("skill_name") or "a skill"
        sys_text += (
            "\n\n=== RECENT CONTEXT ===\n"
            f"The previous assistant turn was a result from {skill_name} and "
            "the raw data is still cached in scope. If the current user "
            "message is a refinement, filter, exclusion, transformation, "
            "templating, formatting, or commentary on that result "
            "(\"only the personal ones\", \"not junk\", \"render per row\", "
            "\"now write the DM for each\", \"format as table\", \"use that "
            "to draft X\", \"go\", \"do it\", etc.), pick \"respond\" — the "
            "responder can re-derive from the cached data without re-running "
            "the skill. Only pick \"skill\" again if the user is asking for "
            "genuinely NEW data (different query, fresh fetch, different "
            "action like sending an email or creating an event)."
        )
    sys = SystemMessage(content=sys_text)

    # Smaller window also helps latency — 10 turns is plenty for routing.
    window = (state.get("messages") or [])[-10:]

    # Structured-output parse failures bubble up as JSONDecodeError /
    # ValidationError and crash the whole graph turn. That's a terrible
    # UX — the user just sees "Expecting value: line 237 column 1". Catch
    # any parse failure and fall back to the responder, which always
    # generates SOMETHING. Log the raw failure so we can debug afterward.
    try:
        decision: OrchestratorDecision = await structured.ainvoke([sys, *window])
    except Exception as e:  # JSONDecodeError, ValidationError, OutputParserException, etc.
        log.warning(
            "orchestrator.parse_failed",
            error=str(e)[:300],
            error_type=type(e).__name__,
        )
        # Default to respond — Kimi will handle whatever the user said,
        # cached skill data is still in state for follow-up patterns.
        return {
            "route": "respond",
            "route_reason": "orchestrator parse fell back to respond",
            "role_used": "orchestrator",
        }

    log.info("orchestrator.route", route=decision.route, reason=decision.reason)

    out: dict = {
        "route": decision.route,
        "route_reason": decision.reason,
        "role_used": "orchestrator",
    }
    # Only "ask" drafts a one-liner here. "respond" always goes to the
    # dedicated responder node so the JAI voice is consistent (Kimi),
    # not whatever Flash happens to draft.
    if decision.route == "ask" and decision.draft:
        out["final_text"] = decision.draft
        out["messages"] = [AIMessage(content=decision.draft)]
    return out
