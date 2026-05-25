"""Status + renewals routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..auth import CurrentUserDep
from ..db import supabase_admin
from ..status.aggregator import fetch_all

router = APIRouter()


@router.get("")
async def status(user: CurrentUserDep) -> dict[str, Any]:
    return await fetch_all(user.user_id)


class RenewalIn(BaseModel):
    service: str
    display_name: str
    monthly_cost_usd: float | None = None
    renews_at: str | None = None
    dashboard_url: str | None = None
    notes: str | None = None


@router.post("/renewals")
async def upsert_renewal(user: CurrentUserDep, body: RenewalIn) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("service_renewals")
        .upsert(
            {"user_id": user.user_id, **body.model_dump(exclude_none=True)},
            on_conflict="user_id,service",
        )
        .execute()
    )
    return res.data[0] if res.data else {"ok": True}


@router.delete("/renewals/{service}")
async def delete_renewal(user: CurrentUserDep, service: str) -> dict:
    sb = supabase_admin()
    sb.table("service_renewals").delete().eq("user_id", user.user_id).eq("service", service).execute()
    return {"ok": True}
