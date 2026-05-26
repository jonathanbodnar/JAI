"""Primary JAI voice — Kimi K2.6.

The orchestrator routes routine turns here. This node is the user-facing
personality: warm, specific, grounded in the retrieved memory. Heavier
than Flash but still a single call with no tool use, so latency is
~1.5–3s including network.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, SystemMessage

from ...models.registry import Role, chat_for
from ..prompts import RESPOND_SYSTEM
from ..state import JaiState
from .orchestrator import _format_memory

log = structlog.get_logger()


async def respond(state: JaiState) -> dict:
    llm = chat_for(Role.RESPOND, temperature=0.5, streaming=False)
    memory_block = _format_memory(state)
    sys = SystemMessage(content=RESPOND_SYSTEM + "\n\n=== RETRIEVED MEMORY ===\n" + memory_block)

    # Keep a healthy conversational window so Kimi can pick up on tone +
    # context from earlier in the thread.
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
