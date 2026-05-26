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


async def orchestrator(state: JaiState) -> dict:
    # Use FAST role for routing — orchestration is ~80% structured routing
    # and ~20% short-form drafts. A fast model finishes in 600–1500ms vs
    # 3–8s for Qwen Max; users feel that gap as "JAI is slow".
    llm = chat_for(Role.FAST, temperature=0.2, streaming=False)
    structured = llm.with_structured_output(OrchestratorDecision)

    memory_block = _format_memory(state)
    sys = SystemMessage(
        content=ORCHESTRATOR_SYSTEM + "\n\n=== RETRIEVED MEMORY ===\n" + memory_block
    )

    # Smaller window also helps latency — 10 turns is plenty for routing.
    window = (state.get("messages") or [])[-10:]
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
