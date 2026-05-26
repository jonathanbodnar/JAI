"""LangGraph state — the working memory of one turn."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

Route = Literal["respond", "reflect", "strategize", "tool", "skill", "ask"]


class JaiState(TypedDict, total=False):
    # --- identity ---
    user_id: str
    conversation_id: str

    # --- input ---
    input_text: str
    input_audio_url: str | None

    # --- transcript window (last K turns, autoreduced by builder) ---
    messages: Annotated[list[BaseMessage], add_messages]

    # --- retrieval results ---
    retrieved_mem0: list[dict]
    retrieved_qdrant: list[dict]
    retrieved_graph: list[dict]

    # --- routing ---
    route: Route
    route_reason: str | None
    needs_clarification: str | None

    # --- delegation / sub-agents ---
    reflection_note: str | None
    strategy_note: str | None

    # --- tool / skill ---
    pending_tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    skill_id: str | None
    skill_name: str | None
    skill_inputs: dict[str, Any] | None
    skill_output: dict[str, Any] | None
    # ISO timestamp of when skill_output was last set. Lets follow-up
    # turns decide whether the cached output is still relevant ("filter
    # that summary…") or too stale to reach back into.
    skill_output_at: str | None
    # User-facing text of the LAST skill summary, kept so the responder
    # can quote it verbatim instead of having to dig through messages.
    skill_output_summary: str | None

    # --- final ---
    final_text: str | None
    final_audio_url: str | None

    # --- bookkeeping ---
    started_at: str
    role_used: str | None
