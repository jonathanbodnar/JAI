"""Read the user's audit log."""

from __future__ import annotations

from fastapi import APIRouter

from ..auth import CurrentUserDep
from ..db import supabase_admin

router = APIRouter()


@router.get("")
async def list_audit(user: CurrentUserDep, limit: int = 100) -> list[dict]:
    sb = supabase_admin()
    res = (
        sb.table("audit_log")
        .select("id,actor,action,target,payload,ok,error,created_at")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
        .limit(min(max(limit, 1), 500))
        .execute()
    )
    return res.data or []
