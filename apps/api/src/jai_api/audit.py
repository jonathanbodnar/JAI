"""Audit log writer. Best-effort; never raises."""

from __future__ import annotations

import structlog

from .db import supabase_admin

log = structlog.get_logger()


async def write(
    *,
    user_id: str,
    actor: str,
    action: str,
    target: str | None = None,
    payload: dict | None = None,
    ok: bool = True,
    error: str | None = None,
) -> None:
    try:
        sb = supabase_admin()
        sb.table("audit_log").insert(
            {
                "user_id": user_id,
                "actor": actor,
                "action": action,
                "target": target,
                "payload": payload or {},
                "ok": ok,
                "error": error,
            }
        ).execute()
    except Exception as e:
        log.warning("audit.write_failed", action=action, error=str(e))
