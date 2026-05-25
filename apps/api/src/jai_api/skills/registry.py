"""CRUD over the skills + skill_runs + skill_credentials tables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from ..db import supabase_admin
from ..models.openrouter import openrouter_embeddings
from .credentials import decrypt, encrypt

log = structlog.get_logger()


async def save_skill(
    *,
    user_id: str,
    title: str,
    description: str,
    language: str,
    source: str,
    required_credentials: list[str],
    required_tools: list[str] | None = None,
    inputs_schema: dict[str, Any] | None = None,
) -> dict:
    embed = openrouter_embeddings()
    [emb] = await embed.aembed_documents([f"{title}\n{description}"])
    sb = supabase_admin()
    res = (
        sb.table("skills")
        .insert(
            {
                "user_id": user_id,
                "title": title,
                "description": description,
                "description_emb": emb,
                "language": language,
                "source": source,
                "required_credentials": required_credentials,
                "required_tools": required_tools or [],
                "inputs_schema": inputs_schema or {},
            }
        )
        .execute()
    )
    return res.data[0]


async def get_skill(*, user_id: str, skill_id: str) -> dict | None:
    sb = supabase_admin()
    res = (
        sb.table("skills")
        .select("*")
        .eq("user_id", user_id)
        .eq("id", skill_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


async def record_run(
    *,
    user_id: str,
    skill_id: str,
    conversation_id: str | None,
    inputs: dict | None,
    output: dict | None,
    status: str,
    stdout: str | None,
    stderr: str | None,
    error: str | None,
    duration_ms: int | None,
) -> dict:
    sb = supabase_admin()
    started = datetime.now(timezone.utc).isoformat()
    res = (
        sb.table("skill_runs")
        .insert(
            {
                "user_id": user_id,
                "skill_id": skill_id,
                "conversation_id": conversation_id,
                "inputs": inputs or {},
                "output": output or {},
                "status": status,
                "stdout": stdout,
                "stderr": stderr,
                "error": error,
                "duration_ms": duration_ms,
                "started_at": started,
                "finished_at": started,
            }
        )
        .execute()
    )
    # bump skill counters
    sb.table("skills").update(
        {
            "run_count": (await _current_run_count(user_id, skill_id)) + 1,
            "last_run_at": started,
            "last_run_status": status,
        }
    ).eq("user_id", user_id).eq("id", skill_id).execute()
    return res.data[0]


async def _current_run_count(user_id: str, skill_id: str) -> int:
    sb = supabase_admin()
    res = (
        sb.table("skills")
        .select("run_count")
        .eq("user_id", user_id)
        .eq("id", skill_id)
        .limit(1)
        .execute()
    )
    return (res.data[0]["run_count"] if res.data else 0) or 0


async def get_credentials(*, user_id: str, keys: list[str]) -> dict[str, str]:
    """Return {key: plaintext} for the credentials the skill needs."""
    if not keys:
        return {}
    sb = supabase_admin()
    res = (
        sb.table("skill_credentials")
        .select("key,value_encrypted")
        .eq("user_id", user_id)
        .in_("key", keys)
        .execute()
    )
    out: dict[str, str] = {}
    for row in res.data or []:
        try:
            blob = row["value_encrypted"]
            # Supabase returns bytea as base64 string or memoryview depending on
            # client version; normalize.
            if isinstance(blob, str):
                import base64
                blob = base64.b64decode(blob.removeprefix("\\x").encode()) if blob.startswith("\\x") else base64.b64decode(blob)
            out[row["key"]] = decrypt(bytes(blob))
        except Exception as e:
            log.error("credential.decrypt_failed", key=row["key"], error=str(e))
    return out


async def set_credential(*, user_id: str, key: str, value: str, metadata: dict | None = None) -> None:
    sb = supabase_admin()
    enc = encrypt(value)
    sb.table("skill_credentials").upsert(
        {
            "user_id": user_id,
            "key": key,
            "value_encrypted": enc,
            "metadata": metadata or {},
        },
        on_conflict="user_id,key",
    ).execute()


async def missing_credentials(*, user_id: str, required: list[str]) -> list[str]:
    if not required:
        return []
    sb = supabase_admin()
    res = (
        sb.table("skill_credentials")
        .select("key")
        .eq("user_id", user_id)
        .in_("key", required)
        .execute()
    )
    have = {r["key"] for r in (res.data or [])}
    return [k for k in required if k not in have]
