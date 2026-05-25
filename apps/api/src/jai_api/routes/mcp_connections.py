"""CRUD for MCP connection configs (Gmail, Calendar, Linear, etc.).

The connection metadata lives in `public.mcp_connections`. Secrets for the
connection (like OAuth tokens) live in `skill_credentials` and are referenced
by `config.env_keys`.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUserDep
from ..db import supabase_admin

router = APIRouter()


class ConnectionIn(BaseModel):
    name: str
    transport: Literal["stdio", "http", "sse"]
    url: str | None = None
    config: dict[str, Any] | None = None


@router.get("")
async def list_connections(user: CurrentUserDep) -> list[dict]:
    sb = supabase_admin()
    res = (
        sb.table("mcp_connections")
        .select("*")
        .eq("user_id", user.user_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


@router.post("")
async def create_connection(user: CurrentUserDep, body: ConnectionIn) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("mcp_connections")
        .upsert(
            {"user_id": user.user_id, **body.model_dump(exclude_none=True), "is_active": True},
            on_conflict="user_id,name",
        )
        .execute()
    )
    return res.data[0]


@router.delete("/{name}")
async def delete_connection(user: CurrentUserDep, name: str) -> dict:
    sb = supabase_admin()
    sb.table("mcp_connections").update({"is_active": False}).eq("user_id", user.user_id).eq("name", name).execute()
    return {"ok": True}
