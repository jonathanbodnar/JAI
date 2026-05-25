"""Internal cron-callable endpoints. Auth via JAI_MCP_SERVER_TOKEN."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from ..config import get_settings
from ..jobs.consolidate import consolidate_for_user

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
async def consolidate(authorization: str | None = Header(default=None)) -> dict:
    _check(authorization)
    s = get_settings()
    if not s.jai_user_id:
        raise HTTPException(400, "JAI_USER_ID not set")
    return await consolidate_for_user(s.jai_user_id)
