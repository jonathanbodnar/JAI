"""Tool routing — runs a ReAct loop with the user's MCP tools + built-ins."""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from ... import audit
from ...models.registry import Role, chat_for
from ...tools.builtin_tools import builtin_tools_for
from ...tools.mcp_loader import load_user_mcp_tools
from ..state import JaiState

log = structlog.get_logger()


SYSTEM = (
    "You are JAI's tool-using executor. You have access to the user's "
    "connected integrations (Gmail, Calendar, etc.) plus built-in tools to "
    "read/write the user's own tasks, notes, and memory. "
    "Call the right tools to complete the user's request. When done, "
    "respond with a concise, plain-English summary of what you did and the "
    "result. Be specific about counts, IDs, and what's still pending."
)


async def tool_router(state: JaiState) -> dict:
    user_id = state["user_id"]
    text = state.get("input_text", "")

    mcp_tools = await load_user_mcp_tools(user_id)
    tools = builtin_tools_for(user_id) + mcp_tools

    if not tools:
        msg = (
            "I'd use a tool here, but you don't have any external integrations "
            "connected yet. Built-in tools (tasks/notes/memory) are limited — "
            "want to add a Gmail/Calendar/Linear connection in Settings?"
        )
        return {"final_text": msg, "messages": [AIMessage(content=msg)], "role_used": "tool_router"}

    llm = chat_for(Role.ORCHESTRATOR, temperature=0.2, streaming=False)
    agent = create_react_agent(llm, tools, prompt=SYSTEM)

    tool_calls_used: list[str] = []
    error: str | None = None
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=text)]})
        last = result["messages"][-1]
        final = last.content if isinstance(last.content, str) else str(last.content)
        for m in result.get("messages", []):
            for tc in getattr(m, "tool_calls", None) or []:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    tool_calls_used.append(name)
    except Exception as e:
        log.exception("tool_router.failed", error=str(e))
        final = f"Tool execution failed: {e}. Want me to try a different approach?"
        error = str(e)

    await audit.write(
        user_id=user_id,
        actor="agent:tool_router",
        action="tool.run",
        target=",".join(tool_calls_used)[:512] or None,
        payload={"intent": text[:200], "tools_used": tool_calls_used},
        ok=error is None,
        error=error,
    )

    return {
        "final_text": final,
        "messages": [AIMessage(content=final)],
        "role_used": "tool_router",
    }
