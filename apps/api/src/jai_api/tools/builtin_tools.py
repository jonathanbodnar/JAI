"""Built-in tools that are always available to the agent (and exposed via our
internal MCP server). These wrap our own tables — tasks, notes, skills,
memory — so the agent can read & write its own second brain."""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import tool

from ..db import supabase_admin
from . import supabase_inproc

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

    # --- Connected Supabase projects (in-process MCP-style) -----------
    # These tools let the ReAct agent query the user's OTHER Supabase
    # projects (Shoutout, etc.) directly in the FastAPI process. No
    # codegen, no sandbox boot — ~500ms per call vs ~15s for the old
    # skill path. Same pattern Cursor/Claude Desktop use over MCP.

    @tool
    async def db_list_projects() -> list[dict[str, Any]]:
        """List the user's connected Supabase projects (slugs and labels).

        Use this FIRST when the user asks about data in a project by name
        ("shoutout", "production db", etc.) — the returned `slug` is what
        you pass to the other db_* tools.
        """
        return await supabase_inproc.list_projects(user_id)

    @tool
    async def db_describe_schema(project_slug: str) -> dict[str, Any]:
        """Describe the table+column structure of a connected Supabase project.

        Returns {project, tables: {table_name: [{name, type}, ...]}}.
        Use this BEFORE writing queries against an unfamiliar project so
        you pick real table and column names. Cached for 10 min in-process.
        """
        return await supabase_inproc.describe_schema(user_id, project_slug)

    @tool
    async def db_query_table(
        project_slug: str,
        table: str,
        select: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int = 50,
        exact_count: bool = False,
    ) -> dict[str, Any]:
        """Query a single table in a connected Supabase project (PostgREST).

        Args:
          project_slug: project slug from db_list_projects (e.g. "shoutout").
          table: table name.
          select: PostgREST select string. Supports aggregations:
            "count" — total count
            "amount.sum()" — sum of amount column
            "status, count()" — group-by-like (returns one row per status)
          filters: column -> PostgREST operator value, e.g.:
            {"created_at": "gte.2026-04-01"} — created_at >= '2026-04-01'
            {"created_at": "lt.2026-05-01"} — created_at <  '2026-05-01'
            {"status": "eq.completed"} — status = 'completed'
            {"type": "neq.wallet_credit"} — type != 'wallet_credit'
            {"amount": "gt.0"} — amount > 0
          order: "column.asc" or "column.desc".
          limit: max rows (cap 1000).
          exact_count: if True, also returns total matching count.

        Returns: {rows: [...], count: int | None, error: str | None}.
        Each row is a dict keyed by column name. For aggregations the
        rows array has a single dict with the aggregate values.
        """
        return await supabase_inproc.query_table(
            user_id=user_id,
            slug=project_slug,
            table=table,
            select=select,
            filters=filters,
            order=order,
            limit=limit,
            exact_count=exact_count,
        )

    return [
        add_note,
        add_task,
        list_tasks,
        list_notes,
        search_memory,
        list_skills,
        db_list_projects,
        db_describe_schema,
        db_query_table,
    ]
