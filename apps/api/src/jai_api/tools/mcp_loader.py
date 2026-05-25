"""Load MCP tools from the user's `mcp_connections` rows.

Uses `langchain-mcp-adapters` which speaks every MCP transport (stdio, HTTP,
SSE) and gives us LangChain `BaseTool` instances we can bind to any chat
model that supports tool calling.

The loader is per-user. Cache the client + tools per user for the lifetime of
the request; LangGraph runs synchronously inside a turn, so a single load
per turn is cheap.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import BaseTool

from ..db import supabase_admin

log = structlog.get_logger()

try:
    from langchain_mcp_adapters.client import MultiServerMCPClient
    _HAS_MCP = True
except Exception:  # pragma: no cover
    MultiServerMCPClient = None  # type: ignore
    _HAS_MCP = False


async def load_user_mcp_tools(user_id: str) -> list[BaseTool]:
    if not _HAS_MCP:
        log.warning("mcp.unavailable", reason="langchain-mcp-adapters not installed")
        return []
    sb = supabase_admin()
    res = (
        sb.table("mcp_connections")
        .select("name,transport,url,config")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute()
    )
    rows = res.data or []
    if not rows:
        return []

    spec: dict[str, dict[str, Any]] = {}
    for r in rows:
        name = r["name"]
        transport = r["transport"]
        cfg = r.get("config") or {}
        if transport == "stdio":
            spec[name] = {
                "transport": "stdio",
                "command": cfg.get("command", ""),
                "args": cfg.get("args", []),
                "env": cfg.get("env", {}),
            }
        elif transport == "sse":
            spec[name] = {"transport": "sse", "url": r["url"]}
        elif transport == "http":
            spec[name] = {"transport": "streamable_http", "url": r["url"]}
        else:
            log.warning("mcp.unknown_transport", transport=transport, name=name)

    try:
        client = MultiServerMCPClient(spec)
        tools = await client.get_tools()
        log.info("mcp.loaded", count=len(tools), connections=list(spec.keys()))
        return tools
    except Exception as e:
        log.error("mcp.load_failed", error=str(e))
        return []
