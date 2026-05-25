"""Normalize the incoming turn into the state."""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from ..state import JaiState


async def ingest(state: JaiState) -> dict:
    text = (state.get("input_text") or "").strip()
    if not text:
        return {"final_text": "I didn't catch that — could you say it again?"}
    return {
        "messages": [HumanMessage(content=text)],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
