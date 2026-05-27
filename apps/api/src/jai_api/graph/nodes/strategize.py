"""Strategy sub-agent (DeepSeek V4 Pro)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, SystemMessage

from ...models.registry import Role, chat_for
from ..prompts import STRATEGY_SYSTEM
from ..state import JaiState
from .orchestrator import _format_memory


async def strategize(state: JaiState) -> dict:
    llm = chat_for(Role.STRATEGY, temperature=0.4, streaming=True)
    memory_block = _format_memory(state)
    sys = SystemMessage(content=STRATEGY_SYSTEM + "\n\n=== RETRIEVED MEMORY ===\n" + memory_block)
    window = (state.get("messages") or [])[-20:]
    res = await llm.ainvoke([sys, *window])
    text = res.content if isinstance(res.content, str) else str(res.content)
    return {
        "final_text": text,
        "messages": [AIMessage(content=text)],
        "strategy_note": text,
        "role_used": "strategy",
    }
