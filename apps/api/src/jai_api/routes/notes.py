"""Notes CRUD (Google Keep-style)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUserDep
from ..db import supabase_admin

router = APIRouter()


class NoteIn(BaseModel):
    title: str | None = None
    body: str | None = None
    color: str | None = "default"
    pinned: bool | None = False
    archived: bool | None = False
    labels: list[str] | None = None
    checklist: list[dict] | None = None


@router.get("")
async def list_notes(user: CurrentUserDep, include_archived: bool = False) -> list[dict[str, Any]]:
    sb = supabase_admin()
    q = (
        sb.table("notes")
        .select("*")
        .eq("user_id", user.user_id)
        .order("pinned", desc=True)
        .order("updated_at", desc=True)
    )
    if not include_archived:
        q = q.eq("archived", False)
    return q.execute().data or []


@router.post("")
async def create_note(user: CurrentUserDep, body: NoteIn) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("notes")
        .insert({"user_id": user.user_id, **body.model_dump(exclude_none=True)})
        .execute()
    )
    return res.data[0]


@router.patch("/{note_id}")
async def patch_note(user: CurrentUserDep, note_id: str, body: NoteIn) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("notes")
        .update(body.model_dump(exclude_none=True))
        .eq("user_id", user.user_id)
        .eq("id", note_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "note not found")
    return res.data[0]


@router.delete("/{note_id}")
async def delete_note(user: CurrentUserDep, note_id: str) -> dict:
    sb = supabase_admin()
    sb.table("notes").delete().eq("user_id", user.user_id).eq("id", note_id).execute()
    return {"ok": True}
