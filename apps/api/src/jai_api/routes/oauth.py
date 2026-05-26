"""Google OAuth routes — multi-account aware.

A single JAI user can connect any number of Google accounts per service
(e.g. several Gmail mailboxes). The canonical source of truth is the
`connected_accounts` table, keyed by `(user_id, provider, service,
account_email)`. The legacy `skill_credentials` row keyed only on service
is kept in sync with whichever account is marked default so existing
skills that look up `GMAIL_OAUTH_JSON` continue to work unchanged.
"""

from __future__ import annotations

import json

import structlog
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
    fetch_userinfo,
)
from ..skills.credentials import encrypt
from ..skills.registry import set_credential

log = structlog.get_logger()

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

    # Identify the connected account.
    account_email = ""
    name = None
    picture = None
    try:
        info = fetch_userinfo(tokens["access_token"])
        account_email = (info.get("email") or "").lower()
        name = info.get("name")
        picture = info.get("picture")
    except Exception as e:
        log.warning("oauth.userinfo_failed", error=str(e))

    if not account_email:
        # Fall back to a placeholder so we still upsert something usable.
        account_email = f"unknown-{tokens.get('access_token', '')[:8]}@google.local"

    sb = supabase_admin()

    # Upsert into connected_accounts.
    existing = (
        sb.table("connected_accounts")
        .select("id,is_default")
        .eq("user_id", user_id)
        .eq("provider", "google")
        .eq("service", service)
        .execute()
        .data
        or []
    )
    is_first = len(existing) == 0  # first account of this service becomes default
    enc_token = encrypt(json.dumps(tokens)).decode("ascii")
    row = {
        "user_id": user_id,
        "provider": "google",
        "service": service,
        "account_email": account_email,
        "value_encrypted": enc_token,
        "scopes": tokens.get("scopes") or [],
        "metadata": {"name": name, "picture": picture},
        "is_active": True,
    }
    if is_first:
        row["is_default"] = True
    sb.table("connected_accounts").upsert(
        row,
        on_conflict="user_id,provider,service,account_email",
    ).execute()

    # Mirror the default into skill_credentials so existing skills/key lookups
    # keep finding GMAIL_OAUTH_JSON, etc.
    if is_first:
        await set_credential(
            user_id=user_id,
            key=credential_key_for(service),
            value=json.dumps(tokens),
            metadata={
                "provider": "google",
                "service": service,
                "account_email": account_email,
            },
        )

    # Keep the surface-level mcp_connections row for the service so the
    # existing "active integrations" UI still shows it.
    sb.table("mcp_connections").upsert(
        {
            "user_id": user_id,
            "name": service,
            "transport": "stdio",
            "url": None,
            "config": {
                "provider": "google",
                "credential_key": credential_key_for(service),
                "note": "Used by JAI's built-in skills; managed accounts live in connected_accounts.",
            },
            "is_active": True,
        },
        on_conflict="user_id,name",
    ).execute()

    sb.table("audit_log").insert(
        {
            "user_id": user_id,
            "actor": "user",
            "action": f"oauth.{service}.connected",
            "target": f"google:{service}:{account_email}",
            "ok": True,
            "payload": {
                "scopes": tokens.get("scopes", []),
                "account_email": account_email,
            },
        }
    ).execute()

    sep = "&" if "?" in return_to else "?"
    return RedirectResponse(
        f"{return_to}{sep}connected={service}&account={account_email}&ok=true"
    )


@router.get("/accounts")
async def list_accounts(user: CurrentUserDep) -> list[dict]:
    """List all OAuth-connected accounts for this user.

    Returns one row per (provider, service, account_email).
    """
    sb = supabase_admin()
    res = (
        sb.table("connected_accounts")
        .select(
            "id, provider, service, account_email, label, scopes, metadata,"
            " is_default, is_active, created_at, updated_at"
        )
        .eq("user_id", user.user_id)
        .eq("is_active", True)
        .order("service")
        .order("created_at")
        .execute()
    )
    return res.data or []


@router.patch("/accounts/{account_id}")
async def update_account(
    user: CurrentUserDep,
    account_id: str,
    body: dict,
) -> dict:
    """Update label or default flag for a connected account."""
    sb = supabase_admin()
    allowed = {}
    if "label" in body:
        allowed["label"] = (body.get("label") or "").strip() or None
    if "is_default" in body:
        allowed["is_default"] = bool(body.get("is_default"))
    if not allowed:
        raise HTTPException(400, "nothing to update")
    res = (
        sb.table("connected_accounts")
        .update(allowed)
        .eq("id", account_id)
        .eq("user_id", user.user_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "account not found")
    row = res.data[0]

    # If we just made this account the default, mirror its token into the
    # legacy skill_credentials key so existing skills target the new default.
    if allowed.get("is_default"):
        try:
            from ..skills.credentials import decrypt as _decrypt
            full = (
                sb.table("connected_accounts")
                .select("value_encrypted, service")
                .eq("id", account_id)
                .single()
                .execute()
                .data
            )
            if full:
                token_str = _decrypt(full["value_encrypted"].encode("ascii"))
                await set_credential(
                    user_id=user.user_id,
                    key=credential_key_for(full["service"]),
                    value=token_str,
                    metadata={
                        "provider": "google",
                        "service": full["service"],
                        "account_email": row["account_email"],
                    },
                )
        except Exception as e:
            log.warning("oauth.default_mirror_failed", error=str(e))
    return row


@router.delete("/accounts/{account_id}")
async def delete_account(user: CurrentUserDep, account_id: str) -> dict:
    """Disconnect a single OAuth account."""
    sb = supabase_admin()
    target = (
        sb.table("connected_accounts")
        .select("id, service, account_email, is_default")
        .eq("id", account_id)
        .eq("user_id", user.user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not target:
        raise HTTPException(404, "account not found")
    row = target[0]
    sb.table("connected_accounts").delete().eq("id", account_id).eq(
        "user_id", user.user_id
    ).execute()

    # If we just deleted the default and there's still another account left,
    # promote the oldest remaining one and resync the legacy key.
    if row.get("is_default"):
        remaining = (
            sb.table("connected_accounts")
            .select("id, value_encrypted, account_email, service")
            .eq("user_id", user.user_id)
            .eq("service", row["service"])
            .eq("is_active", True)
            .order("created_at")
            .limit(1)
            .execute()
            .data
            or []
        )
        if remaining:
            new_default = remaining[0]
            sb.table("connected_accounts").update({"is_default": True}).eq(
                "id", new_default["id"]
            ).eq("user_id", user.user_id).execute()
            try:
                from ..skills.credentials import decrypt as _decrypt
                token_str = _decrypt(new_default["value_encrypted"].encode("ascii"))
                await set_credential(
                    user_id=user.user_id,
                    key=credential_key_for(new_default["service"]),
                    value=token_str,
                    metadata={
                        "provider": "google",
                        "service": new_default["service"],
                        "account_email": new_default["account_email"],
                    },
                )
            except Exception as e:
                log.warning("oauth.promote_default_failed", error=str(e))
        else:
            # Nothing left — clear the legacy key and deactivate the mcp_connections row.
            sb.table("skill_credentials").delete().eq("user_id", user.user_id).eq(
                "key", credential_key_for(row["service"])
            ).execute()
            sb.table("mcp_connections").update({"is_active": False}).eq(
                "user_id", user.user_id
            ).eq("name", row["service"]).execute()

    sb.table("audit_log").insert(
        {
            "user_id": user.user_id,
            "actor": "user",
            "action": f"oauth.{row['service']}.disconnected",
            "target": f"google:{row['service']}:{row['account_email']}",
            "ok": True,
            "payload": {"account_email": row["account_email"]},
        }
    ).execute()
    return {"ok": True}
