"""Per-service status providers. Each is independent + safe to fail."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from ..config import get_settings
from .types import ServiceStatus

log = structlog.get_logger()

# Common httpx config
_TIMEOUT = httpx.Timeout(8.0, connect=3.0)


async def openrouter_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="openrouter",
        display_name="OpenRouter",
        category="llm",
        configured=bool(s.openrouter_api_key),
        dashboard_url="https://openrouter.ai/credits",
    )
    if not base.configured:
        base.notes = "OPENROUTER_API_KEY not set"
        base.healthy = False
        return base
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(
                "https://openrouter.ai/api/v1/credits",
                headers={"authorization": f"Bearer {s.openrouter_api_key}"},
            )
            r.raise_for_status()
            d = (r.json() or {}).get("data") or {}
            total = float(d.get("total_credits", 0) or 0)
            used = float(d.get("total_usage", 0) or 0)
            base.used_usd = round(used, 4)
            base.balance_usd = round(max(total - used, 0), 4)
    except Exception as e:
        base.healthy = False
        base.error = str(e)
    return base


async def qdrant_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="qdrant",
        display_name="Qdrant Cloud",
        category="memory",
        configured=bool(s.qdrant_url),
        dashboard_url="https://cloud.qdrant.io/",
    )
    if not base.configured:
        base.healthy = False
        base.notes = "QDRANT_URL not set"
        return base
    headers = {"api-key": s.qdrant_api_key} if s.qdrant_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            # Collection count + storage
            cinfo = await c.get(f"{s.qdrant_url.rstrip('/')}/collections/{s.qdrant_collection}", headers=headers)
            if cinfo.status_code == 200:
                d = (cinfo.json() or {}).get("result") or {}
                base.usage = {
                    "points": d.get("points_count", 0),
                    "vectors": d.get("vectors_count", 0),
                    "segments": d.get("segments_count", 0),
                }
            elif cinfo.status_code == 404:
                base.notes = f"collection '{s.qdrant_collection}' not created yet"
            else:
                base.healthy = False
                base.error = f"HTTP {cinfo.status_code}"
    except Exception as e:
        base.healthy = False
        base.error = str(e)
    return base


async def groq_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="groq",
        display_name="Groq",
        category="voice",
        configured=bool(s.groq_api_key),
        dashboard_url="https://console.groq.com/",
        notes="STT (Whisper). No usage API — see headers per request.",
    )
    if not base.configured:
        base.healthy = False
        return base
    # Ping the models endpoint to confirm the key works and surface rate limits.
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(
                "https://api.groq.com/openai/v1/models",
                headers={"authorization": f"Bearer {s.groq_api_key}"},
            )
            r.raise_for_status()
            limits: dict[str, Any] = {}
            for k in ("x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
                      "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens"):
                if k in r.headers:
                    limits[k] = r.headers[k]
            if limits:
                base.usage = limits
    except Exception as e:
        base.healthy = False
        base.error = str(e)
    return base


async def supabase_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="supabase",
        display_name="Supabase",
        category="infra",
        configured=bool(s.supabase_url and s.supabase_service_role_key),
        dashboard_url="https://supabase.com/dashboard/projects",
        notes="No public usage API. Use dashboard for plan + storage.",
    )
    if not base.configured:
        base.healthy = False
        return base
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(
                f"{s.supabase_url.rstrip('/')}/rest/v1/",
                headers={"apikey": s.supabase_service_role_key},
            )
            base.healthy = r.status_code < 500
    except Exception as e:
        base.healthy = False
        base.error = str(e)
    return base


async def neo4j_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="neo4j",
        display_name="Neo4j Aura",
        category="memory",
        configured=bool(s.neo4j_uri and s.neo4j_password),
        dashboard_url="https://console.neo4j.io/",
        notes="No public usage API — manage in console.",
    )
    if not base.configured:
        base.healthy = False
        return base
    # Light driver ping
    try:
        from neo4j import AsyncGraphDatabase
        drv = AsyncGraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
        async with drv.session(database=s.neo4j_database) as sess:
            res = await sess.run("RETURN 1 AS ok")
            await res.consume()
        await drv.close()
    except Exception as e:
        base.healthy = False
        base.error = str(e)
    return base


async def mem0_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="mem0",
        display_name="Mem0",
        category="memory",
        configured=bool(s.mem0_api_key),
        dashboard_url="https://app.mem0.ai/",
        notes="No public usage API — track in Mem0 dashboard.",
    )
    base.healthy = base.configured
    return base


async def elevenlabs_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="elevenlabs",
        display_name="ElevenLabs",
        category="voice",
        configured=bool(s.elevenlabs_api_key),
        dashboard_url="https://elevenlabs.io/app/usage",
        notes="Optional TTS fallback.",
    )
    if not base.configured:
        return base
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": s.elevenlabs_api_key},
            )
            r.raise_for_status()
            d = r.json() or {}
            limit = int(d.get("character_limit", 0) or 0)
            used = int(d.get("character_count", 0) or 0)
            base.usage = {"characters_used": used, "characters_limit": limit}
            if d.get("next_character_count_reset_unix"):
                from datetime import datetime, timezone
                base.period_end = datetime.fromtimestamp(
                    int(d["next_character_count_reset_unix"]), tz=timezone.utc
                ).isoformat()
    except Exception as e:
        base.healthy = False
        base.error = str(e)
    return base


async def cloudflare_status() -> ServiceStatus:
    s = get_settings()
    base = ServiceStatus(
        service="cloudflare",
        display_name="Cloudflare",
        category="infra",
        configured=bool(s.cloudflare_api_token and s.cloudflare_account_id),
        dashboard_url="https://dash.cloudflare.com/",
        notes="Workers + Pages + Sandbox + R2.",
    )
    if not base.configured:
        return base
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"authorization": f"Bearer {s.cloudflare_api_token}"},
            )
            r.raise_for_status()
    except Exception as e:
        base.healthy = False
        base.error = str(e)
    return base


async def fly_status() -> ServiceStatus:
    # We don't have a Fly token in config; rely on user adding it to the
    # renewals table. Surface as configured=False to hint they can add manually.
    base = ServiceStatus(
        service="fly",
        display_name="Fly.io",
        category="infra",
        configured=False,
        dashboard_url="https://fly.io/dashboard",
        notes="Add FLY_API_TOKEN to env for live machine + billing stats.",
    )
    return base


ALL_PROVIDERS = [
    openrouter_status,
    groq_status,
    elevenlabs_status,
    qdrant_status,
    neo4j_status,
    mem0_status,
    supabase_status,
    cloudflare_status,
    fly_status,
]
