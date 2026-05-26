"""List every connected external Supabase project + a quick health probe."""

KEY = "supabase.list_projects"
TITLE = "List connected Supabase projects"
DESCRIPTION = (
    "Show every external Supabase project the user has connected to JAI "
    "(Shoutout, etc.) and ping each one to confirm the credentials still "
    "work. Use for 'what supabase projects am I connected to', 'is my "
    "shoutout connection healthy', 'list data sources'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["supabase"]

SOURCE = r"""
import os, json
import httpx

projects = json.loads(os.environ.get("SUPABASE_PROJECTS_JSON") or "[]")
if not projects:
    print(json.dumps({"status": "ok", "result": {
        "count": 0,
        "projects": [],
        "note": "No external Supabase projects connected. Add one in Settings → Data sources."
    }}))
    raise SystemExit(0)

out = []
for p in projects:
    info = {"slug": p["slug"], "label": p["label"], "url": p["url"]}
    try:
        r = httpx.get(
            p["url"].rstrip("/") + "/rest/v1/",
            headers={"apikey": p["key"], "Authorization": f"Bearer {p['key']}"},
            timeout=10.0,
        )
        info["status"] = "ok" if r.status_code < 400 else f"http_{r.status_code}"
        # The swagger spec lists every available table in `definitions`.
        if r.headers.get("content-type", "").startswith("application/openapi+json") \
                or "definitions" in (r.text or "")[:200]:
            try:
                spec = r.json()
                info["tables"] = sorted(list((spec.get("definitions") or {}).keys()))[:40]
            except Exception:
                pass
    except Exception as e:
        info["status"] = "unreachable"
        info["error"] = str(e)[:200]
    out.append(info)

print(json.dumps({"status": "ok", "result": {"count": len(out), "projects": out}}))
"""
