"""Recent activity feed — what JAI has been working on.

This powers the small "running list" overlay in the bottom-left of
the chat. We blend a few signal sources into a single time-ordered
stream so the feed reads like a coherent timeline rather than a
single table's last-N rows:

  - skill_runs   — every sandboxed skill execution (drafts, reads,
                   queries, etc.)
  - tasks        — task creations + completions
  - notes        — note creations + edits
  - kpis         — pinned KPI updates
  - canvas       — long-form artifacts (email drafts, docs) from
                   assistant message metadata

The endpoint is intentionally cheap — each source is capped at
limit × 3 rows so we have headroom for the time-merge without
pulling tens of thousands of rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Query

from ..auth import CurrentUserDep
from ..db import supabase_admin

log = structlog.get_logger()
router = APIRouter()


def _iso(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    return ""


def _parse(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


@router.get("/recent")
async def recent_activity(
    user: CurrentUserDep,
    limit: int = Query(default=5, ge=1, le=25),
) -> list[dict[str, Any]]:
    """Return the most recent `limit` activity items across all sources.

    Each item has the shape:
      {
        id:        str            # stable per source row
        kind:      "skill" | "task" | "note" | "kpi" | "canvas"
        title:     str            # one-line label ("Drafted email to JT")
        detail:    str | None     # second-line context
        status:    "ok" | "error" | None
        at:        ISO-8601 timestamp
        skill_id?: uuid           # only for kind = "skill"
        target_id?: uuid          # underlying row id
      }
    """
    try:
        sb = supabase_admin()
    except Exception as e:
        log.warning("supabase.unavailable", error=str(e))
        return []

    # Pull a generous slice from each source so we can time-merge below
    # without missing the newest items in any single feed.
    pull = max(limit * 3, 10)

    items: list[dict[str, Any]] = []

    # 1. Skill runs — annotate with the parent skill's title so the
    #    label reads as "Ran <skill>" rather than a UUID.
    try:
        runs = (
            sb.table("skill_runs")
            .select(
                "id, skill_id, status, started_at, output, error, "
                "skills!inner(title, metadata)"
            )
            .eq("user_id", user.user_id)
            .order("started_at", desc=True)
            .limit(pull)
            .execute()
            .data
            or []
        )
        for r in runs:
            sk = r.get("skills") or {}
            title = sk.get("title") or "Ran a skill"
            output = r.get("output") or {}
            detail = None
            if isinstance(output, dict):
                # Prefer the canvas-like kind/title if present.
                kind = output.get("kind")
                if kind == "email_draft":
                    detail = f"Email to {output.get('to') or '?'}"
                elif kind == "sheet_rows":
                    tab = output.get("tab")
                    rc = output.get("row_count")
                    detail = f"{tab} · {rc} rows" if tab else None
                elif kind in ("document", "plan", "list", "code"):
                    detail = output.get("title")
            items.append({
                "id": f"skill:{r['id']}",
                "kind": "skill",
                "title": title,
                "detail": detail,
                "status": r.get("status"),
                "at": _iso(r.get("started_at")),
                "skill_id": r.get("skill_id"),
                "target_id": r.get("id"),
            })
    except Exception as e:
        log.warning("activity.skill_runs.failed", error=str(e))

    # 2. Tasks — separate signal for "added" vs "completed".
    try:
        tasks = (
            sb.table("tasks")
            .select("id, title, status, created_at, completed_at, updated_at")
            .eq("user_id", user.user_id)
            .order("updated_at", desc=True)
            .limit(pull)
            .execute()
            .data
            or []
        )
        for t in tasks:
            completed = t.get("completed_at")
            created = t.get("created_at")
            # Emit two entries when the task was both created AND completed
            # inside the visible window — usually we just want the most
            # recent transition, so prefer "completed" when present.
            if completed:
                items.append({
                    "id": f"task_done:{t['id']}",
                    "kind": "task",
                    "title": f"Completed: {t.get('title') or 'task'}",
                    "detail": None,
                    "status": "ok",
                    "at": _iso(completed),
                    "target_id": t["id"],
                })
            elif created:
                items.append({
                    "id": f"task_new:{t['id']}",
                    "kind": "task",
                    "title": f"Added task: {t.get('title') or 'untitled'}",
                    "detail": None,
                    "status": None,
                    "at": _iso(created),
                    "target_id": t["id"],
                })
    except Exception as e:
        log.warning("activity.tasks.failed", error=str(e))

    # 3. Notes — creations only (edits are noisy and rarely worth
    #    surfacing in a "what did we work on" ribbon).
    try:
        notes = (
            sb.table("notes")
            .select("id, title, body, created_at")
            .eq("user_id", user.user_id)
            .eq("archived", False)
            .order("created_at", desc=True)
            .limit(pull)
            .execute()
            .data
            or []
        )
        for n in notes:
            title = (n.get("title") or "").strip()
            if not title:
                body = (n.get("body") or "").strip().splitlines()
                title = (body[0] if body else "Note") or "Note"
            items.append({
                "id": f"note:{n['id']}",
                "kind": "note",
                "title": f"Note: {title[:80]}",
                "detail": None,
                "status": None,
                "at": _iso(n.get("created_at")),
                "target_id": n["id"],
            })
    except Exception as e:
        log.warning("activity.notes.failed", error=str(e))

    # 4. KPI updates.
    try:
        kpis = (
            sb.table("kpis")
            .select("id, label, value, last_updated_at")
            .eq("user_id", user.user_id)
            .order("last_updated_at", desc=True)
            .limit(pull)
            .execute()
            .data
            or []
        )
        for k in kpis:
            label = (k.get("label") or "").strip() or "KPI"
            val = (k.get("value") or "").strip() or "—"
            items.append({
                "id": f"kpi:{k['id']}",
                "kind": "kpi",
                "title": f"{label}: {val}",
                "detail": None,
                "status": None,
                "at": _iso(k.get("last_updated_at")),
                "target_id": k["id"],
            })
    except Exception as e:
        log.warning("activity.kpis.failed", error=str(e))

    # Sort newest-first, drop anything with no timestamp, return top N.
    items = [it for it in items if it.get("at")]
    items.sort(key=lambda it: _parse(it["at"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items[:limit]
