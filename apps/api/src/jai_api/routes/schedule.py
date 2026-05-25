"""CRUD routes for user-defined scheduled actions (/schedule)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..auth import CurrentUserDep
from ..db import supabase_admin

log = structlog.get_logger()
router = APIRouter()

VALID_FREQ = {"hourly", "daily", "weekdays", "weekly", "monthly"}


class ScheduleIn(BaseModel):
    description: str
    frequency: str = "daily"
    hour_utc: int = Field(default=6, ge=0, le=23)
    day_of_week: int | None = Field(default=None, ge=0, le=6)  # 0=Sun..6=Sat
    skill_id: str | None = None
    builtin_name: str | None = None
    skill_inputs: dict[str, Any] = {}
    enabled: bool = True


class SchedulePatch(BaseModel):
    description: str | None = None
    frequency: str | None = None
    hour_utc: int | None = Field(default=None, ge=0, le=23)
    day_of_week: int | None = None
    enabled: bool | None = None
    skill_inputs: dict[str, Any] | None = None


def _next_run_at(frequency: str, hour_utc: int, day_of_week: int | None) -> datetime:
    """Compute the next scheduled fire time (UTC)."""
    now = datetime.now(timezone.utc)

    if frequency == "hourly":
        return now + timedelta(hours=1)

    # Anchor to target hour today; if already past, move to tomorrow.
    candidate = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)

    if frequency in ("daily",):
        return candidate

    if frequency == "weekdays":
        # Skip weekends (Mon=0 ... Fri=4, Sat=5, Sun=6 in Python's weekday())
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    if frequency == "weekly":
        target_dow = day_of_week if day_of_week is not None else 1  # Monday default
        # Python weekday(): Mon=0...Sun=6.  Our schema: 0=Sun..6=Sat
        target_py = (target_dow - 1) % 7  # convert Sun=0 → Sun=6 in Python
        while candidate.weekday() != target_py:
            candidate += timedelta(days=1)
        return candidate

    if frequency == "monthly":
        # First of next month at target hour
        if now.month == 12:
            return now.replace(year=now.year + 1, month=1, day=1,
                               hour=hour_utc, minute=0, second=0, microsecond=0)
        return now.replace(month=now.month + 1, day=1,
                           hour=hour_utc, minute=0, second=0, microsecond=0)

    return candidate


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_actions(user: CurrentUserDep) -> list[dict]:
    """List all scheduled actions for the current user."""
    sb = supabase_admin()
    res = (
        sb.table("scheduled_actions")
        .select("*")
        .eq("user_id", user.user_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


@router.post("")
async def create_action(user: CurrentUserDep, body: ScheduleIn) -> dict:
    """Create a new scheduled action."""
    if body.frequency not in VALID_FREQ:
        raise HTTPException(400, f"frequency must be one of: {', '.join(sorted(VALID_FREQ))}")

    sb = supabase_admin()
    next_run = _next_run_at(body.frequency, body.hour_utc, body.day_of_week)

    res = (
        sb.table("scheduled_actions")
        .insert({
            "user_id": user.user_id,
            "description": body.description.strip(),
            "frequency": body.frequency,
            "hour_utc": body.hour_utc,
            "day_of_week": body.day_of_week,
            "skill_id": body.skill_id,
            "builtin_name": body.builtin_name,
            "skill_inputs": body.skill_inputs,
            "enabled": body.enabled,
            "next_run_at": next_run.isoformat(),
        })
        .execute()
    )
    row = res.data[0] if res.data else {}
    log.info("schedule.created", id=row.get("id"), description=body.description,
             frequency=body.frequency, user=user.user_id)
    return row


@router.patch("/{action_id}")
async def update_action(user: CurrentUserDep, action_id: str, body: SchedulePatch) -> dict:
    """Update a scheduled action."""
    sb = supabase_admin()

    # Verify ownership first
    existing = (
        sb.table("scheduled_actions")
        .select("id, frequency, hour_utc, day_of_week")
        .eq("id", action_id)
        .eq("user_id", user.user_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(404, "not found")

    row = existing.data[0]
    update: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if body.description is not None:
        update["description"] = body.description.strip()
    if body.enabled is not None:
        update["enabled"] = body.enabled
    if body.skill_inputs is not None:
        update["skill_inputs"] = body.skill_inputs

    freq = body.frequency or row["frequency"]
    hour = body.hour_utc if body.hour_utc is not None else row["hour_utc"]
    dow = body.day_of_week if body.day_of_week is not None else row["day_of_week"]

    if body.frequency is not None:
        if body.frequency not in VALID_FREQ:
            raise HTTPException(400, f"frequency must be one of: {', '.join(sorted(VALID_FREQ))}")
        update["frequency"] = freq
        update["hour_utc"] = hour
        update["day_of_week"] = dow
        update["next_run_at"] = _next_run_at(freq, hour, dow).isoformat()

    res = (
        sb.table("scheduled_actions")
        .update(update)
        .eq("id", action_id)
        .eq("user_id", user.user_id)
        .execute()
    )
    return res.data[0] if res.data else {}


@router.delete("/{action_id}")
async def delete_action(user: CurrentUserDep, action_id: str) -> dict:
    """Delete a scheduled action."""
    sb = supabase_admin()
    sb.table("scheduled_actions").delete().eq("id", action_id).eq("user_id", user.user_id).execute()
    log.info("schedule.deleted", id=action_id, user=user.user_id)
    return {"ok": True}


@router.post("/{action_id}/run")
async def run_action_now(user: CurrentUserDep, action_id: str) -> dict:
    """Trigger an immediate (out-of-schedule) run of one action."""
    sb = supabase_admin()
    existing = (
        sb.table("scheduled_actions")
        .select("*")
        .eq("id", action_id)
        .eq("user_id", user.user_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(404, "not found")

    from ..jobs.scheduled import run_one_action  # avoid circular at module level
    result = await run_one_action(existing.data[0], sb)
    return result
