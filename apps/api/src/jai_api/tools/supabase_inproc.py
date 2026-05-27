"""In-process Supabase project query — the MCP-style fast path.

Why this exists: the user's connected Supabase projects (Shoutout, etc.)
were being queried via the codegen + sandbox path, which costs ~15-20s
per turn (Qwen draft → ast.parse → Cloudflare sandbox boot → pip install
→ HTTP call → JSON synthesis). Same query in-process is ~500ms-2s.

This module exposes a small surface (list projects, describe schema,
query a table, aggregate a table) that the LangGraph tool_router's
ReAct agent can call directly via LangChain tools. The model picks
the right tool, fills the args, gets rows back, and synthesizes — same
loop as Cursor/Claude Desktop's MCP integration, just running in our
own FastAPI process.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from ..db import supabase_admin
from ..skills.credentials import decrypt

log = structlog.get_logger()


# Project lookup is cached for 60s — the data_sources table changes
# rarely and a single chat turn often makes 3-5 calls against the same
# project (list tables → describe → query → aggregate). Re-decrypting
# the service key on every call is wasteful.
_PROJECT_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_PROJECT_TTL_S = 60.0

# Schema cache lasts longer — schemas rarely change mid-session and
# the OpenAPI spec fetch is the slowest single call (~300-600ms on a
# big project). 10 minutes balances freshness vs latency.
_SCHEMA_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_SCHEMA_TTL_S = 600.0


async def _project(user_id: str, slug: str) -> dict | None:
    """Look up a connected Supabase project by slug. Returns decrypted creds."""
    cache_key = (user_id, slug)
    cached = _PROJECT_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _PROJECT_TTL_S:
        return cached[1]

    sb = supabase_admin()
    res = (
        sb.table("data_sources")
        .select("id, slug, label, url, key_encrypted, is_active, kind")
        .eq("user_id", user_id)
        .eq("slug", slug)
        .eq("is_active", True)
        .eq("kind", "supabase")
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    try:
        key = decrypt(row["key_encrypted"].encode("ascii"))
    except Exception as e:
        log.error("supabase_inproc.decrypt_failed", slug=slug, error=str(e))
        return None
    proj = {
        "slug": slug,
        "label": row.get("label"),
        "url": row["url"].rstrip("/"),
        "key": key,
    }
    _PROJECT_CACHE[(user_id, slug)] = (time.time(), proj)
    return proj


async def list_projects(user_id: str) -> list[dict]:
    """List the user's connected Supabase projects."""
    sb = supabase_admin()
    res = (
        sb.table("data_sources")
        .select("slug, label, url, last_test_ok")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .eq("kind", "supabase")
        .order("created_at")
        .execute()
    )
    return res.data or []


async def describe_schema(user_id: str, slug: str) -> dict:
    """Return {table: [{name, type, required}, ...]} for the project's PostgREST schema.

    Uses Supabase's auto-generated OpenAPI spec at /rest/v1/. Cached
    in-process for 10 min so repeated calls in the same turn don't
    re-fetch a 200KB JSON blob.
    """
    cache_key = (user_id, slug)
    cached = _SCHEMA_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _SCHEMA_TTL_S:
        return cached[1]

    proj = await _project(user_id, slug)
    if not proj:
        return {"error": f"project '{slug}' not found or inactive"}

    target = f"{proj['url']}/rest/v1/"
    headers = {"apikey": proj["key"], "Authorization": f"Bearer {proj['key']}"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as c:
            r = await c.get(target, headers=headers)
    except Exception as e:
        return {"error": f"schema fetch failed: {e}"}
    if r.status_code >= 400:
        return {"error": f"HTTP {r.status_code}: {(r.text or '')[:200]}"}

    try:
        spec = r.json()
    except Exception as e:
        return {"error": f"bad OpenAPI response: {e}"}

    schema: dict[str, list[dict]] = {}
    definitions = spec.get("definitions") or {}
    for path in (spec.get("paths") or {}).keys():
        if not path.startswith("/") or path in ("/", "/rpc/"):
            continue
        # PostgREST paths look like "/orders" for table=orders.
        table = path.lstrip("/").split("/")[0]
        if not table or table == "rpc":
            continue
        defn = definitions.get(table) or {}
        props = (defn.get("properties") or {}) if isinstance(defn, dict) else {}
        cols: list[dict] = []
        for col_name, col_def in props.items():
            if not isinstance(col_def, dict):
                continue
            col_type = col_def.get("format") or col_def.get("type") or "unknown"
            cols.append({"name": col_name, "type": col_type})
        if cols and table not in schema:
            schema[table] = cols

    out = {"project": slug, "tables": schema}
    _SCHEMA_CACHE[cache_key] = (time.time(), out)
    return out


def _build_url(
    base: str,
    table: str,
    select: str,
    filters: dict[str, str] | None,
    order: str | None,
    limit: int | None,
) -> str:
    from urllib.parse import quote

    params: list[str] = [f"select={quote(select, safe=',()*.')}"]
    if filters:
        for k, v in filters.items():
            # PostgREST operators like "gte.2026-04-01" or "eq.live"
            # are already URL-safe enough, but we still encode the
            # value to be defensive against weird user input.
            params.append(f"{k}={quote(str(v), safe='.,():*')}")
    if order:
        params.append(f"order={quote(order, safe=',.()')}")
    if limit:
        params.append(f"limit={int(limit)}")
    return f"{base}/rest/v1/{table}?{'&'.join(params)}"


async def query_table(
    user_id: str,
    slug: str,
    table: str,
    select: str = "*",
    filters: dict[str, str] | None = None,
    order: str | None = None,
    limit: int = 50,
    exact_count: bool = False,
) -> dict:
    """Run a PostgREST query against a connected Supabase project.

    Args:
      slug: the project slug (e.g. "shoutout").
      table: the table name (e.g. "orders").
      select: PostgREST select string. Supports aggregations like
        "count" or "amount.sum()" or "status,count()".
      filters: dict of column -> PostgREST operator value. Examples:
        {"created_at": "gte.2026-04-01"}, {"status": "eq.completed"},
        {"type": "neq.wallet_credit"}.
      order: "<column>.<asc|desc>" e.g. "created_at.desc".
      limit: max rows. Capped at 1000 for safety.
      exact_count: if True, also return the total row count in the
        result (uses Prefer: count=exact).

    Returns: {rows: [...], count: int | None, error: str | None}.
    """
    proj = await _project(user_id, slug)
    if not proj:
        return {"error": f"project '{slug}' not found or inactive"}

    limit = max(1, min(int(limit), 1000))
    url = _build_url(proj["url"], table, select, filters, order, limit)
    headers = {
        "apikey": proj["key"],
        "Authorization": f"Bearer {proj['key']}",
    }
    if exact_count:
        headers["Prefer"] = "count=exact"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as c:
            r = await c.get(url, headers=headers)
    except Exception as e:
        return {"error": f"request failed: {e}"}

    if r.status_code >= 400:
        return {
            "error": f"HTTP {r.status_code}: {(r.text or '')[:400]}",
            "url": url.replace(proj["key"], "***"),
        }

    try:
        rows = r.json()
    except Exception as e:
        return {"error": f"bad JSON: {e}"}

    out: dict[str, Any] = {"rows": rows if isinstance(rows, list) else [rows]}
    if exact_count:
        cr = r.headers.get("content-range") or ""
        if "/" in cr:
            tail = cr.split("/")[-1]
            if tail.isdigit():
                out["count"] = int(tail)
    return out
