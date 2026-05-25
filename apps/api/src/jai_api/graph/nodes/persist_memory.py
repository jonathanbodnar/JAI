"""Write the turn to Mem0 + Qdrant after responding."""

from __future__ import annotations

import asyncio

import structlog

from ...memory.mem0 import JaiMem0
from ...memory.qdrant import JaiQdrant
from ..state import JaiState

log = structlog.get_logger()


def make_persist(mem0: JaiMem0, qdrant: JaiQdrant):
    async def persist(state: JaiState) -> dict:
        user_id = state.get("user_id")
        user_text = state.get("input_text", "")
        assistant_text = state.get("final_text", "")
        if not (user_id and (user_text or assistant_text)):
            return {}

        tasks = []
        # Mem0 — let it extract identity facts from the turn
        if mem0.enabled and user_text:
            tasks.append(
                mem0.add(
                    user_id,
                    [
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": assistant_text},
                    ],
                    metadata={"role_used": state.get("role_used")},
                )
            )
        # Qdrant — store both sides as semantic points
        if user_text:
            tasks.append(
                qdrant.add(
                    user_id=user_id,
                    text=user_text,
                    source="conversation_user",
                    metadata={"role_used": state.get("role_used")},
                )
            )
        if assistant_text:
            tasks.append(
                qdrant.add(
                    user_id=user_id,
                    text=assistant_text,
                    source="conversation_assistant",
                    metadata={"role_used": state.get("role_used")},
                )
            )

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    log.warning("persist.partial_failure", error=str(r))
        return {}

    return persist
