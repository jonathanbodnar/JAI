"""External data sources — other Supabase projects (and eventually other DBs).

The user adds e.g. "Shoutout" with a project URL + service role key. JAI
encrypts the key, stores it in `data_sources`, and injects every active
source into the skill sandbox as part of `SUPABASE_PROJECTS_JSON`. Skills
then look up the project by slug and query its REST API directly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

import httpx
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from ..auth import CurrentUserDep
from ..db import supabase_admin
from ..skills.credentials import decrypt, encrypt

log = structlog.get_logger()
router = APIRouter()


SUPPORTED_KINDS = {"supabase"}


class DataSourceCreate(BaseModel):
    kind: Literal["supabase"] = "supabase"
    label: str = Field(min_length=1, max_length=80)
    url: HttpUrl
    key: str = Field(min_length=20, description="Service role key (encrypted at rest)")
    metadata: dict = Field(default_factory=dict)


class DataSourceUpdate(BaseModel):
    label: str | None = None
    url: HttpUrl | None = None
    key: str | None = Field(default=None, min_length=20)
    is_active: bool | None = None


def _slugify(label: str) -> str:
    """Turn 'Shoutout v2' into 'shoutout_v2'."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip().lower()).strip("_")
    return s or "source"


async def _probe_supabase(url: str, key: str) -> tuple[bool, str]:
    """Issue a tiny REST API call to confirm url + key are usable.

    Hits `${url}/rest/v1/?apikey=...` which Supabase responds to with
    swagger JSON when creds are valid. Anything 4xx → broken credentials.
    """
    target = url.rstrip("/") + "/rest/v1/"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as c:
            r = await c.get(target, headers=headers)
        if r.status_code < 400:
            return True, "ok"
        return False, f"HTTP {r.status_code}: {(r.text or '')[:200]}"
    except Exception as e:
        return False, f"unreachable: {e}"


@router.get("/")
async def list_data_sources(user: CurrentUserDep) -> list[dict]:
    sb = supabase_admin()
    res = (
        sb.table("data_sources")
        .select(
            "id, kind, slug, label, url, metadata, is_active,"
            " last_tested_at, last_test_ok, created_at, updated_at"
        )
        .eq("user_id", user.user_id)
        .order("created_at")
        .execute()
    )
    return res.data or []


@router.post("/")
async def create_data_source(user: CurrentUserDep, body: DataSourceCreate) -> dict:
    if body.kind not in SUPPORTED_KINDS:
        raise HTTPException(400, f"unsupported kind: {body.kind}")

    url_str = str(body.url).rstrip("/")

    # Test the credentials before storing them so the user gets immediate
    # feedback in the UI instead of a mysterious skill failure later.
    ok, detail = await _probe_supabase(url_str, body.key)

    sb = supabase_admin()
    slug = _slugify(body.label)

    # If slug collides, append a numeric suffix.
    existing = (
        sb.table("data_sources")
        .select("slug")
        .eq("user_id", user.user_id)
        .eq("kind", body.kind)
        .execute()
        .data
        or []
    )
    used = {r["slug"] for r in existing}
    final_slug = slug
    i = 2
    while final_slug in used:
        final_slug = f"{slug}_{i}"
        i += 1

    enc = encrypt(body.key).decode("ascii")
    row = {
        "user_id": user.user_id,
        "kind": body.kind,
        "slug": final_slug,
        "label": body.label.strip(),
        "url": url_str,
        "key_encrypted": enc,
        "metadata": body.metadata or {},
        "is_active": True,
        "last_tested_at": datetime.now(timezone.utc).isoformat(),
        "last_test_ok": ok,
    }
    ins = sb.table("data_sources").insert(row).execute()
    if not ins.data:
        raise HTTPException(500, "failed to insert data source")

    saved = ins.data[0]
    saved.pop("key_encrypted", None)  # never return secret material
    saved["test_detail"] = detail
    return saved


@router.patch("/{source_id}")
async def update_data_source(
    user: CurrentUserDep, source_id: str, body: DataSourceUpdate
) -> dict:
    sb = supabase_admin()
    existing = (
        sb.table("data_sources")
        .select("*")
        .eq("id", source_id)
        .eq("user_id", user.user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not existing:
        raise HTTPException(404, "data source not found")
    row = existing[0]

    updates: dict = {}
    if body.label is not None:
        updates["label"] = body.label.strip()
    if body.url is not None:
        updates["url"] = str(body.url).rstrip("/")
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.key is not None:
        updates["key_encrypted"] = encrypt(body.key).decode("ascii")

    # Re-probe if creds changed
    if body.url is not None or body.key is not None:
        key = body.key or decrypt(row["key_encrypted"].encode("ascii"))
        url = updates.get("url", row["url"])
        ok, detail = await _probe_supabase(url, key)
        updates["last_tested_at"] = datetime.now(timezone.utc).isoformat()
        updates["last_test_ok"] = ok
    else:
        detail = "no creds changed"

    if not updates:
        raise HTTPException(400, "nothing to update")

    res = (
        sb.table("data_sources")
        .update(updates)
        .eq("id", source_id)
        .eq("user_id", user.user_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "data source not found")
    out = res.data[0]
    out.pop("key_encrypted", None)
    out["test_detail"] = detail
    return out


@router.post("/{source_id}/test")
async def test_data_source(user: CurrentUserDep, source_id: str) -> dict:
    """Re-probe an existing source's credentials without changing anything."""
    sb = supabase_admin()
    row = (
        sb.table("data_sources")
        .select("id, url, key_encrypted, kind")
        .eq("id", source_id)
        .eq("user_id", user.user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not row:
        raise HTTPException(404, "data source not found")
    r = row[0]
    if r["kind"] != "supabase":
        raise HTTPException(400, f"test not implemented for kind={r['kind']}")
    key = decrypt(r["key_encrypted"].encode("ascii"))
    ok, detail = await _probe_supabase(r["url"], key)
    sb.table("data_sources").update(
        {
            "last_tested_at": datetime.now(timezone.utc).isoformat(),
            "last_test_ok": ok,
        }
    ).eq("id", source_id).eq("user_id", user.user_id).execute()
    return {"ok": ok, "detail": detail}


@router.delete("/{source_id}")
async def delete_data_source(user: CurrentUserDep, source_id: str) -> dict:
    sb = supabase_admin()
    sb.table("data_sources").delete().eq("id", source_id).eq(
        "user_id", user.user_id
    ).execute()
    return {"ok": True}
