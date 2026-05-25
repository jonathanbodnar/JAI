"""Run all status providers in parallel + merge in service_renewals data."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from ..db import supabase_admin
from .providers import ALL_PROVIDERS
from .types import ServiceStatus

log = structlog.get_logger()


async def fetch_all(user_id: str) -> dict[str, Any]:
    statuses = await asyncio.gather(*(p() for p in ALL_PROVIDERS), return_exceptions=True)
    out: list[dict] = []
    for s in statuses:
        if isinstance(s, Exception):
            log.warning("status.provider.exception", error=str(s))
            continue
        out.append(s.model_dump())

    # Merge user-specific renewal info
    sb = supabase_admin()
    renewals = (
        sb.table("service_renewals").select("*").eq("user_id", user_id).execute().data or []
    )
    by_service = {r["service"]: r for r in renewals}
    for entry in out:
        r = by_service.pop(entry["service"], None)
        if r:
            entry["monthly_cost_usd"] = r.get("monthly_cost_usd")
            entry["renews_at"] = r.get("renews_at")
            if r.get("notes") and not entry.get("notes"):
                entry["notes"] = r["notes"]
            if r.get("dashboard_url"):
                entry["dashboard_url"] = r["dashboard_url"]
    # Any manual-only services without a provider — append as bare entries
    for service, r in by_service.items():
        out.append(
            ServiceStatus(
                service=service,
                display_name=r.get("display_name") or service,
                category="platform",
                configured=True,
                dashboard_url=r.get("dashboard_url"),
                notes=r.get("notes"),
            ).model_dump()
            | {
                "monthly_cost_usd": r.get("monthly_cost_usd"),
                "renews_at": r.get("renews_at"),
            }
        )

    monthly_total = sum(float(e.get("monthly_cost_usd") or 0) for e in out)
    return {"services": out, "monthly_run_rate_usd": round(monthly_total, 2)}
