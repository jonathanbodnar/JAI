"""Google OAuth routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from ..auth import CurrentUserDep
from ..config import get_settings
from ..db import supabase_admin
from ..oauth.google import (
    Service,
    auth_url,
    credential_key_for,
    decode_state,
    exchange_code,
)
from ..skills.registry import set_credential

router = APIRouter()


@router.get("/google/start")
async def google_start(
    user: CurrentUserDep,
    service: Service = Query(..., description="gmail | calendar | drive"),
    return_to: str | None = None,
) -> dict:
    s = get_settings()
    rt = return_to or f"{s.jai_frontend_url}/settings?connected={service}"
    return {"auth_url": auth_url(user_id=user.user_id, service=service, return_to=rt)}


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    s = get_settings()
    if error:
        return RedirectResponse(f"{s.jai_frontend_url}/settings?error={error}")
    if not (code and state):
        raise HTTPException(400, "missing code or state")

    payload = decode_state(state)
    user_id = payload["u"]
    service: Service = payload["s"]
    return_to: str = payload["r"]

    tokens = exchange_code(service=service, code=code)
    await set_credential(
        user_id=user_id,
        key=credential_key_for(service),
        value=json.dumps(tokens),
        metadata={"provider": "google", "service": service},
    )

    # Auto-create an mcp_connections row so the user sees the integration immediately.
    sb = supabase_admin()
    sb.table("mcp_connections").upsert(
        {
            "user_id": user_id,
            "name": service,
            "transport": "stdio",
            "url": None,
            "config": {
                "provider": "google",
                "credential_key": credential_key_for(service),
                "note": "Used by JAI's built-in skills; no external MCP server required.",
            },
            "is_active": True,
        },
        on_conflict="user_id,name",
    ).execute()

    # Audit
    sb.table("audit_log").insert(
        {
            "user_id": user_id,
            "actor": "user",
            "action": f"oauth.{service}.connected",
            "target": f"google:{service}",
            "ok": True,
            "payload": {"scopes": tokens.get("scopes", [])},
        }
    ).execute()

    sep = "&" if "?" in return_to else "?"
    return RedirectResponse(f"{return_to}{sep}connected={service}&ok=true")
