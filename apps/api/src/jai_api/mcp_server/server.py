"""Expose JAI's second brain as an MCP server.

Other tools (Claude Desktop, Cursor, custom agents) can connect and call:
  - search_memory(query, limit)
  - list_tasks(only_open=True)
  - add_task(title, due?)
  - list_notes(query?)
  - add_note(title?, body?)
  - list_skills()
  - run_skill_intent(intent)
  - get_graph(limit=200)

Authentication: bearer token (`JAI_MCP_SERVER_TOKEN`). One-tenant for now —
the configured token grants access on behalf of `JAI_USER_ID`. To open this
up multi-tenant later, swap the token for the Supabase JWT and pull the
user id from claims.
"""

from __future__ import annotations

from typing import Any

import structlog

from ..config import get_settings
from ..db import supabase_admin
from .context import current_user_id

log = structlog.get_logger()

try:
    from mcp.server.fastmcp import FastMCP
    _HAS_MCP = True
except Exception:  # pragma: no cover
    FastMCP = None  # type: ignore
    _HAS_MCP = False


def build_mcp_server():
    """Construct the FastMCP app. Returns None if the mcp package is missing."""
    if not _HAS_MCP:
        log.warning("internal_mcp.unavailable", reason="mcp not installed")
        return None

    settings = get_settings()
    mcp = FastMCP("jai", instructions="JAI — second brain MCP. Read & write the user's memory, tasks, notes, and skills.")

    def _user() -> str:
        return current_user_id()

    @mcp.tool()
    async def search_memory(query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search the user's full memory (identity facts + semantic notes)."""
        from ..memory.mem0 import JaiMem0
        from ..memory.qdrant import JaiQdrant

        mem0 = JaiMem0(settings)
        qdrant = JaiQdrant(settings)
        try:
            mhits = await mem0.search(_user(), query)
            qhits = await qdrant.search(_user(), query)
            merged = (
                [{"text": h["text"], "source": "mem0", "score": h.get("score", 0)} for h in mhits]
                + [{"text": h["text"], "source": "qdrant", "score": h.get("score", 0)} for h in qhits]
            )
            return merged[:limit]
        finally:
            await qdrant.close()

    @mcp.tool()
    async def list_tasks(only_open: bool = True) -> list[dict[str, Any]]:
        """List the user's tasks. By default, only open (uncompleted)."""
        sb = supabase_admin()
        q = sb.table("tasks").select("id,title,due,status,notes").eq("user_id", _user())
        if only_open:
            q = q.eq("status", "needsAction")
        return q.order("created_at", desc=True).limit(100).execute().data or []

    @mcp.tool()
    async def add_task(title: str, due: str | None = None, notes: str | None = None) -> dict:
        """Add a task to the user's primary task list."""
        sb = supabase_admin()
        uid = _user()
        lists = sb.table("task_lists").select("id").eq("user_id", uid).limit(1).execute()
        if lists.data:
            list_id = lists.data[0]["id"]
        else:
            list_id = sb.table("task_lists").insert({"user_id": uid, "title": "My Tasks"}).execute().data[0]["id"]
        res = sb.table("tasks").insert({
            "user_id": uid, "list_id": list_id, "title": title, "due": due, "notes": notes, "source": "agent",
        }).execute()
        return res.data[0]

    @mcp.tool()
    async def list_notes(query: str | None = None) -> list[dict[str, Any]]:
        """List notes. If `query` is given, substring match on title+body."""
        sb = supabase_admin()
        q = sb.table("notes").select("id,title,body,labels,updated_at").eq("user_id", _user()).eq("archived", False)
        if query:
            q = q.or_(f"title.ilike.%{query}%,body.ilike.%{query}%")
        return q.order("updated_at", desc=True).limit(50).execute().data or []

    @mcp.tool()
    async def add_note(title: str | None = None, body: str | None = None) -> dict:
        """Save a note."""
        sb = supabase_admin()
        res = sb.table("notes").insert(
            {"user_id": _user(), "title": title, "body": body, "source": "agent"}
        ).execute()
        return res.data[0]

    @mcp.tool()
    async def list_skills() -> list[dict[str, Any]]:
        """List the user's saved skills."""
        sb = supabase_admin()
        return (
            sb.table("skills")
            .select("id,title,description,language,run_count,last_run_at,last_run_status")
            .eq("user_id", _user())
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .execute()
            .data or []
        )

    @mcp.tool()
    async def run_skill_intent(intent: str) -> dict[str, Any]:
        """Run an intent through JAI's skill engine (match → build → execute)."""
        from ..skills.runner import run_intent
        out = await run_intent(user_id=_user(), conversation_id=None, intent=intent)
        return {
            "final_text": out.final_text,
            "skill_id": out.skill_id,
            "needs_credentials": out.needs_credentials or [],
        }

    @mcp.tool()
    async def get_graph(limit: int = 200) -> dict[str, Any]:
        """Return the user's identity graph (nodes + edges)."""
        from ..memory.neo4j_client import JaiNeo4j
        neo = JaiNeo4j(settings)
        try:
            return await neo.graph_dump(_user(), limit=limit)
        finally:
            await neo.close()

    return mcp


_token_singleton: str | None = None


def expected_token() -> str | None:
    global _token_singleton
    if _token_singleton is None:
        _token_singleton = get_settings().jai_mcp_server_token or None
    return _token_singleton
