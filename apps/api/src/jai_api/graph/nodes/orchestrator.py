"""The orchestrator decides what kind of turn this is and drafts a response.

Uses structured output so we can route deterministically. The orchestrator
also produces a short draft for the 'respond' and 'ask' routes; for the
delegated routes (reflect/strategize/tool/skill), it just routes.
"""

from __future__ import annotations

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
    draft: str | None = Field(default=None, description="Response draft for respond/ask routes")


def _format_memory(state: JaiState) -> str:
    parts: list[str] = []
    mem0 = state.get("retrieved_mem0") or []
    if mem0:
        parts.append("Identity facts (Mem0):")
        for m in mem0[:8]:
            parts.append(f"- {m.get('text','').strip()}")
    qdrant = state.get("retrieved_qdrant") or []
    if qdrant:
        parts.append("\nRelevant past notes (Qdrant):")
        for q in qdrant[:5]:
            text = (q.get("text", "") or "").strip()
            if text:
                parts.append(f"- {text[:240]}{'…' if len(text) > 240 else ''}")
    graph = state.get("retrieved_graph") or []
    if graph:
        parts.append("\nRelationship graph (Neo4j):")
        for g in graph[:5]:
            node = g.get("node", {})
            edges = g.get("edges", [])
            parts.append(f"- {node.get('name', node.get('id','?'))}: " +
                         ", ".join(f"{e['rel']}→{(e['node'] or {}).get('name','?')}" for e in edges[:5]))
    return "\n".join(parts) if parts else "(no memory retrieved)"


async def orchestrator(state: JaiState) -> dict:
    llm = chat_for(Role.ORCHESTRATOR, temperature=0.2, streaming=False)
    structured = llm.with_structured_output(OrchestratorDecision)

    memory_block = _format_memory(state)
    sys = SystemMessage(content=ORCHESTRATOR_SYSTEM + "\n\n=== RETRIEVED MEMORY ===\n" + memory_block)

    # Use the last K messages as the working window
    window = (state.get("messages") or [])[-20:]
    decision: OrchestratorDecision = await structured.ainvoke([sys, *window])

    log.info("orchestrator.route", route=decision.route, reason=decision.reason)

    out: dict = {
        "route": decision.route,
        "route_reason": decision.reason,
        "role_used": "orchestrator",
    }
    if decision.route in ("respond", "ask") and decision.draft:
        out["final_text"] = decision.draft
        out["messages"] = [AIMessage(content=decision.draft)]
    return out
