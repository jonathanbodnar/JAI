"""Internal cron-callable endpoints. Auth via JAI_MCP_SERVER_TOKEN."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ..config import get_settings
from ..jobs.consolidate import consolidate_all_users, consolidate_for_user

router = APIRouter()


def _check(auth: str | None) -> None:
    s = get_settings()
    expected = s.jai_mcp_server_token
    if not expected:
        return  # dev mode: open
    got = (auth or "").removeprefix("Bearer ").strip()
    if got != expected:
        raise HTTPException(401, "unauthorized")


@router.post("/consolidate")
async def consolidate(
    authorization: str | None = Header(default=None),
    user_id: str | None = None,
) -> dict:
    """Nightly consolidation.

    With no `user_id` query param, runs for every active user. Pass
    `?user_id=<uuid>` to consolidate a single user (useful for manual
    re-runs or testing).
    """
    _check(authorization)
    if user_id:
        return await consolidate_for_user(user_id)
    # Multi-tenant default. Used to require `JAI_USER_ID` env which
    # silently meant "JB only" — fixed so any user signing up gets
    # their nightly summary.
    return await consolidate_all_users()
