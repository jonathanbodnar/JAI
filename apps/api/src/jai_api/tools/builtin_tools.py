"""Built-in tools that are always available to the agent (and exposed via our
internal MCP server). These wrap our own tables — tasks, notes, skills,
memory — so the agent can read & write its own second brain."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import tool

from ..db import supabase_admin

log = structlog.get_logger()


def builtin_tools_for(user_id: str) -> list:
    """Closure-bound built-in tools scoped to a user. Returns LangChain tools."""

    @tool
    async def add_note(title: str | None = None, body: str | None = None) -> dict:
        """Save a note to JAI. Returns the new note's id."""
        sb = supabase_admin()
        res = sb.table("notes").insert(
            {"user_id": user_id, "title": title, "body": body, "source": "agent"}
        ).execute()
        return {"id": res.data[0]["id"]}

    @tool
    async def add_task(title: str, due: str | None = None, notes: str | None = None) -> dict:
        """Add a task to the user's primary task list. Returns task id."""
        sb = supabase_admin()
        lists = sb.table("task_lists").select("id").eq("user_id", user_id).limit(1).execute()
        if lists.data:
            list_id = lists.data[0]["id"]
        else:
            list_id = sb.table("task_lists").insert(
                {"user_id": user_id, "title": "My Tasks"}
            ).execute().data[0]["id"]
        res = sb.table("tasks").insert(
            {
                "user_id": user_id,
                "list_id": list_id,
                "title": title,
                "due": due,
                "notes": notes,
                "source": "agent",
            }
        ).execute()
        return {"id": res.data[0]["id"]}

    @tool
    async def list_tasks(only_open: bool = True) -> list[dict[str, Any]]:
        """List the user's tasks. Defaults to open (uncompleted) only."""
        sb = supabase_admin()
        q = sb.table("tasks").select("id,title,due,status,notes").eq("user_id", user_id)
        if only_open:
            q = q.eq("status", "needsAction")
        return q.order("created_at", desc=True).limit(100).execute().data or []

    @tool
    async def list_notes(query: str | None = None) -> list[dict[str, Any]]:
        """List notes. If `query` is given, do a substring match on title+body."""
        sb = supabase_admin()
        q = (
            sb.table("notes")
            .select("id,title,body,labels,updated_at")
            .eq("user_id", user_id)
            .eq("archived", False)
        )
        if query:
            q = q.or_(f"title.ilike.%{query}%,body.ilike.%{query}%")
        return q.order("updated_at", desc=True).limit(50).execute().data or []

    @tool
    async def search_memory(query: str) -> list[dict[str, Any]]:
        """Search the user's full memory (Mem0 identity + Qdrant semantic).
        Returns a merged list of hits with `text` and `source`."""
        from ..config import get_settings
        from ..memory.mem0 import JaiMem0
        from ..memory.qdrant import JaiQdrant

        s = get_settings()
        mem0 = JaiMem0(s)
        qdrant = JaiQdrant(s)
        try:
            mhits = await mem0.search(user_id, query)
            qhits = await qdrant.search(user_id, query)
            return (
                [{"text": h["text"], "source": "mem0", "score": h.get("score", 0)} for h in mhits]
                + [{"text": h["text"], "source": "qdrant", "score": h.get("score", 0)} for h in qhits]
            )
        finally:
            await qdrant.close()

    @tool
    async def list_skills() -> list[dict[str, Any]]:
        """List the user's saved skills."""
        sb = supabase_admin()
        res = (
            sb.table("skills")
            .select("id,title,description,language,run_count,last_run_at,last_run_status")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .execute()
        )
        return res.data or []

    return [add_note, add_task, list_tasks, list_notes, search_memory, list_skills]
