"""Tasks CRUD (Google Tasks-style; sync via MCP coming later)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUserDep
from ..db import supabase_admin

router = APIRouter()


class TaskListIn(BaseModel):
    title: str
    position: int | None = 0


class TaskIn(BaseModel):
    list_id: str
    title: str
    notes: str | None = None
    due: str | None = None
    parent_id: str | None = None
    status: str | None = "needsAction"


@router.get("/lists")
async def get_lists(user: CurrentUserDep) -> list[dict[str, Any]]:
    sb = supabase_admin()
    res = (
        sb.table("task_lists")
        .select("*")
        .eq("user_id", user.user_id)
        .order("position")
        .execute()
    )
    if not res.data:
        # bootstrap a default list on first hit
        ins = (
            sb.table("task_lists")
            .insert({"user_id": user.user_id, "title": "My Tasks", "position": 0})
            .execute()
        )
        return ins.data
    return res.data


@router.post("/lists")
async def create_list(user: CurrentUserDep, body: TaskListIn) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("task_lists")
        .insert({"user_id": user.user_id, **body.model_dump(exclude_none=True)})
        .execute()
    )
    return res.data[0]


@router.get("")
async def list_tasks(user: CurrentUserDep, list_id: str) -> list[dict[str, Any]]:
    sb = supabase_admin()
    res = (
        sb.table("tasks")
        .select("*")
        .eq("user_id", user.user_id)
        .eq("list_id", list_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


@router.post("")
async def create_task(user: CurrentUserDep, body: TaskIn) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("tasks")
        .insert({"user_id": user.user_id, **body.model_dump(exclude_none=True)})
        .execute()
    )
    return res.data[0]


class TaskPatch(BaseModel):
    title: str | None = None
    notes: str | None = None
    due: str | None = None
    status: str | None = None
    parent_id: str | None = None


@router.patch("/{task_id}")
async def patch_task(user: CurrentUserDep, task_id: str, body: TaskPatch) -> dict:
    sb = supabase_admin()
    patch = body.model_dump(exclude_none=True)
    if body.status == "completed":
        patch["completed_at"] = "now()"
    res = (
        sb.table("tasks")
        .update(patch)
        .eq("user_id", user.user_id)
        .eq("id", task_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "task not found")
    return res.data[0]


@router.delete("/{task_id}")
async def delete_task(user: CurrentUserDep, task_id: str) -> dict:
    sb = supabase_admin()
    sb.table("tasks").delete().eq("user_id", user.user_id).eq("id", task_id).execute()
    return {"ok": True}
