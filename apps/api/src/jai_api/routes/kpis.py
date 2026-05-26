"""Living KPIs that pin to the header of the chat.

The values can be set three ways:
  1. Manual edit in the header UI (PATCH / POST below)
  2. A skill writing to the `kpis` table via the auto-injected JAI
     Supabase credentials (preferred for anything recurring)
  3. The convenience `/kpis/upsert` endpoint below — same effect as #2
     but reachable from a skill that doesn't want to handle Supabase
     REST directly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUserDep
from ..db import supabase_admin

log = structlog.get_logger()
router = APIRouter()


_KEY_PATTERN = re.compile(r"[^a-z0-9_]+")
_HISTORY_KEEP = 30  # last N samples retained per KPI


def _slugify(label: str) -> str:
    slug = _KEY_PATTERN.sub("_", label.strip().lower()).strip("_")
    return slug or "kpi"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


Format = Literal["raw", "number", "currency", "percent", "duration"]


class KpiIn(BaseModel):
    key: str | None = None
    label: str
    value: str
    format: Format = "raw"
    unit: str | None = None
    icon: str | None = None
    color: str | None = None
    source: str | None = "manual"
    sort_order: int | None = None
    is_visible: bool | None = True


class KpiPatch(BaseModel):
    label: str | None = None
    value: str | None = None
    format: Format | None = None
    unit: str | None = None
    icon: str | None = None
    color: str | None = None
    sort_order: int | None = None
    is_visible: bool | None = None
    # When `record_history` is true, the new value is also appended to
    # the rolling history. The UI uses this for the spark/trend.
    record_history: bool | None = True


class KpiUpsert(BaseModel):
    """Skill-friendly endpoint payload — `key` is required so multiple
    runs idempotently update the same KPI."""

    key: str
    label: str | None = None
    value: str
    format: Format | None = None
    unit: str | None = None
    icon: str | None = None
    source: str | None = None


def _bump_history(current: list[Any] | None, new_value: str) -> list[dict[str, str]]:
    history = list(current or [])
    history.append({"value": new_value, "at": _now_iso()})
    # Cap so the row doesn't grow unbounded.
    return history[-_HISTORY_KEEP:]


@router.get("")
async def list_kpis(user: CurrentUserDep, include_hidden: bool = False) -> list[dict[str, Any]]:
    sb = supabase_admin()
    q = (
        sb.table("kpis")
        .select("*")
        .eq("user_id", user.user_id)
        .order("sort_order")
        .order("created_at")
    )
    if not include_hidden:
        q = q.eq("is_visible", True)
    return q.execute().data or []


@router.post("")
async def create_kpi(user: CurrentUserDep, body: KpiIn) -> dict:
    sb = supabase_admin()
    key = (body.key or _slugify(body.label)).strip().lower()
    payload = body.model_dump(exclude_none=True)
    payload["key"] = key
    payload["user_id"] = user.user_id
    payload["history"] = [{"value": body.value, "at": _now_iso()}]
    payload["last_updated_at"] = _now_iso()
    try:
        res = sb.table("kpis").insert(payload).execute()
    except Exception as e:  # likely unique-constraint violation on (user, key)
        log.warning("kpis.insert_failed", error=str(e))
        raise HTTPException(409, f"a KPI with key '{key}' already exists")
    return res.data[0]


@router.patch("/{kpi_id}")
async def patch_kpi(user: CurrentUserDep, kpi_id: str, body: KpiPatch) -> dict:
    sb = supabase_admin()
    cur = (
        sb.table("kpis")
        .select("*")
        .eq("user_id", user.user_id)
        .eq("id", kpi_id)
        .single()
        .execute()
        .data
    )
    if not cur:
        raise HTTPException(404, "kpi not found")

    patch = body.model_dump(exclude_none=True, exclude={"record_history"})
    if "value" in patch:
        patch["previous"] = cur.get("value")
        if body.record_history is not False:
            patch["history"] = _bump_history(cur.get("history"), patch["value"])
        patch["last_updated_at"] = _now_iso()

    res = (
        sb.table("kpis")
        .update(patch)
        .eq("user_id", user.user_id)
        .eq("id", kpi_id)
        .execute()
    )
    return res.data[0]


@router.delete("/{kpi_id}")
async def delete_kpi(user: CurrentUserDep, kpi_id: str) -> dict:
    sb = supabase_admin()
    sb.table("kpis").delete().eq("user_id", user.user_id).eq("id", kpi_id).execute()
    return {"ok": True}


@router.post("/upsert")
async def upsert_kpi(user: CurrentUserDep, body: KpiUpsert) -> dict:
    """Skill-friendly idempotent upsert keyed by `key`. Records history.

    Skills can call this with just user JWT or directly write to the
    table — this is just a convenience layer that handles history + the
    previous-value bookkeeping in one round trip.
    """
    sb = supabase_admin()
    key = body.key.strip().lower()
    existing = (
        sb.table("kpis")
        .select("*")
        .eq("user_id", user.user_id)
        .eq("key", key)
        .execute()
        .data
    )
    now = _now_iso()
    if existing:
        cur = existing[0]
        update_patch: dict[str, Any] = {
            "value": body.value,
            "previous": cur.get("value"),
            "history": _bump_history(cur.get("history"), body.value),
            "last_updated_at": now,
        }
        if body.label is not None:
            update_patch["label"] = body.label
        if body.format is not None:
            update_patch["format"] = body.format
        if body.unit is not None:
            update_patch["unit"] = body.unit
        if body.icon is not None:
            update_patch["icon"] = body.icon
        if body.source is not None:
            update_patch["source"] = body.source
        res = (
            sb.table("kpis")
            .update(update_patch)
            .eq("user_id", user.user_id)
            .eq("id", cur["id"])
            .execute()
        )
        return res.data[0]

    insert_payload: dict[str, Any] = {
        "user_id": user.user_id,
        "key": key,
        "label": body.label or key.replace("_", " ").title(),
        "value": body.value,
        "format": body.format or "raw",
        "unit": body.unit,
        "icon": body.icon,
        "source": body.source or "skill",
        "history": [{"value": body.value, "at": now}],
        "last_updated_at": now,
    }
    res = sb.table("kpis").insert(insert_payload).execute()
    return res.data[0]


class ReorderPayload(BaseModel):
    ids: list[str] = Field(default_factory=list)


@router.post("/reorder")
async def reorder_kpis(user: CurrentUserDep, body: ReorderPayload) -> dict:
    sb = supabase_admin()
    for idx, kid in enumerate(body.ids):
        sb.table("kpis").update({"sort_order": idx}).eq("user_id", user.user_id).eq("id", kid).execute()
    return {"ok": True, "count": len(body.ids)}
