"""Generic SELECT against a table in a connected external Supabase project."""

KEY = "supabase.query_table"
TITLE = "Query a Supabase project table"
DESCRIPTION = (
    "Run a SELECT against any table on a connected external Supabase "
    "project. Inputs: project (slug or label fragment, e.g. 'shoutout'), "
    "table (required), select (default '*'), filter (optional PostgREST "
    "filter, e.g. 'created_at=gte.2025-01-01'), order (default "
    "'created_at.desc'), limit (default 50). Use for 'how many users does "
    "shoutout have', 'recent signups in shoutout', 'shoutout stats'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["supabase"]

SOURCE = r"""
import os, json
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
target = (inputs.get("project") or "").strip().lower()
table = (inputs.get("table") or "").strip()
select = (inputs.get("select") or "*").strip()
filter_clause = (inputs.get("filter") or "").strip()
order = (inputs.get("order") or "").strip()
limit = int(inputs.get("limit") or 50)
count_only = bool(inputs.get("count_only"))

if not table:
    print(json.dumps({"status": "error", "error": "Missing required input: table"}))
    raise SystemExit(0)

projects = json.loads(os.environ.get("SUPABASE_PROJECTS_JSON") or "[]")
if not projects:
    print(json.dumps({"status": "error",
        "error": "No external Supabase projects connected. Add one in Settings → Data sources."}))
    raise SystemExit(0)

if target:
    proj = next((p for p in projects
                 if target in p["slug"].lower() or target in p["label"].lower()), None)
    if not proj:
        print(json.dumps({"status": "error",
            "error": f"No connected project matches '{target}'. Available: " +
                     ", ".join(f"{p['label']} ({p['slug']})" for p in projects)}))
        raise SystemExit(0)
else:
    proj = projects[0]

base = proj["url"].rstrip("/") + "/rest/v1"
head = {"apikey": proj["key"], "Authorization": f"Bearer {proj['key']}"}
if count_only:
    head["Prefer"] = "count=exact"

q = [f"select={select}", f"limit={limit}"]
if order:
    q.append(f"order={order}")
if filter_clause:
    q.append(filter_clause)
url = f"{base}/{table}?{'&'.join(q)}"

try:
    r = httpx.get(url, headers=head, timeout=20.0)
    r.raise_for_status()
except httpx.HTTPStatusError as e:
    print(json.dumps({"status": "error",
        "error": f"Query failed ({e.response.status_code}): {e.response.text[:300]}"}))
    raise SystemExit(0)
except Exception as e:
    print(json.dumps({"status": "error", "error": f"Query failed: {str(e)[:300]}"}))
    raise SystemExit(0)

rows = r.json()
result = {
    "project": proj["label"],
    "slug": proj["slug"],
    "table": table,
    "row_count": len(rows),
    "rows": rows[:50],
}
if count_only:
    crange = r.headers.get("content-range") or ""
    if "/" in crange:
        result["total_in_table"] = crange.split("/")[-1]

print(json.dumps({"status": "ok", "result": result}))
"""
