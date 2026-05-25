"""Execution engine for user-defined scheduled actions.

Called from:
  - consolidate_for_user()  (nightly cron)
  - POST /schedule/{id}/run (immediate trigger from UI)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

log = structlog.get_logger()


def _next_run_at(frequency: str, hour_utc: int, day_of_week: int | None) -> datetime:
    """Compute next fire time after a successful run."""
    now = datetime.now(timezone.utc)

    if frequency == "hourly":
        return now + timedelta(hours=1)

    candidate = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)

    if frequency == "daily":
        return candidate

    if frequency == "weekdays":
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    if frequency == "weekly":
        target_dow = day_of_week if day_of_week is not None else 1
        target_py = (target_dow - 1) % 7
        while candidate.weekday() != target_py:
            candidate += timedelta(days=1)
        return candidate

    if frequency == "monthly":
        if now.month == 12:
            return now.replace(year=now.year + 1, month=1, day=1,
                               hour=hour_utc, minute=0, second=0, microsecond=0)
        return now.replace(month=now.month + 1, day=1,
                           hour=hour_utc, minute=0, second=0, microsecond=0)

    return candidate


async def run_due_actions(user_id: str, sb: Any) -> list[dict]:
    """Find and execute all due scheduled actions for a user.

    Returns a list of result dicts (one per action that ran).
    """
    now = datetime.now(timezone.utc)
    due = (
        sb.table("scheduled_actions")
        .select("*")
        .eq("user_id", user_id)
        .eq("enabled", True)
        .lte("next_run_at", now.isoformat())
        .execute()
    )
    results: list[dict] = []
    for action in (due.data or []):
        r = await run_one_action(action, sb)
        results.append(r)
    return results


async def run_one_action(action: dict, sb: Any) -> dict:
    """Execute a single scheduled action and update the row."""
    action_id = action["id"]
    user_id = action["user_id"]
    description = action.get("description", "")
    frequency = action.get("frequency", "daily")
    hour_utc = action.get("hour_utc", 6)
    day_of_week = action.get("day_of_week")
    builtin_name = action.get("builtin_name")
    skill_id = action.get("skill_id")
    skill_inputs = action.get("skill_inputs") or {}

    status = "ok"
    result_text: str | None = None

    try:
        if builtin_name == "task_summary":
            from ..skills.builtin import _morning_briefing
            hit = await _morning_briefing(user_id=user_id, text="task summary")
            result_text = hit.response

        elif skill_id:
            result_text = await _run_skill(user_id, skill_id, skill_inputs, sb)

        else:
            # Description-only action: generate a brief AI summary
            result_text = f"Scheduled action ran: {description}"

        next_run = _next_run_at(frequency, hour_utc, day_of_week)
        sb.table("scheduled_actions").update({
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "next_run_at": next_run.isoformat(),
            "last_result": (result_text or "")[:2000],
            "last_status": "ok",
            "run_count": (action.get("run_count") or 0) + 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", action_id).execute()

        log.info("scheduled_action.ran", id=action_id, description=description,
                 status="ok", user=user_id)

    except Exception as exc:
        status = "error"
        result_text = str(exc)[:500]
        log.warning("scheduled_action.failed", id=action_id, error=result_text, user=user_id)
        try:
            sb.table("scheduled_actions").update({
                "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_result": result_text,
                "last_status": "error",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", action_id).execute()
        except Exception:
            pass

    return {
        "action_id": action_id,
        "description": description,
        "status": status,
        "result": result_text,
    }


async def _run_skill(user_id: str, skill_id: str, inputs: dict, sb: Any) -> str:
    """Execute a saved skill via the sandbox runner."""
    # Fetch the skill source from DB
    skill_res = (
        sb.table("skills")
        .select("id,title,language,source,required_credentials")
        .eq("id", skill_id)
        .limit(1)
        .execute()
    )
    if not skill_res.data:
        return f"skill {skill_id} not found"

    skill = skill_res.data[0]
    from ..skills.runner import run_skill
    outcome = await run_skill(
        user_id=user_id,
        skill=skill,
        inputs=inputs,
        conversation_id=None,
    )
    return outcome.get("final_text") or outcome.get("stdout") or "done"
