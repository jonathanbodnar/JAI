"""Search JAI notes by free-text query."""

KEY = "jai.search_notes"
TITLE = "Search my notes"
DESCRIPTION = (
    "Search JAI notes by free-text query (matches title and body). Inputs: "
    "query (optional — empty returns most recent), limit (default 20). Use "
    "for 'find my note about X', 'recent notes', 'what did I write about Y'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["jai"]

SOURCE = r"""
import os, json
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
query = (inputs.get("query") or "").strip()
limit = int(inputs.get("limit") or 20)

base = os.environ["JAI_SUPABASE_URL"].rstrip("/") + "/rest/v1"
head = {
    "apikey": os.environ["JAI_SUPABASE_KEY"],
    "Authorization": f"Bearer {os.environ['JAI_SUPABASE_KEY']}",
}
uid = os.environ["JAI_USER_ID"]

params = [
    f"user_id=eq.{uid}",
    "archived=eq.false",
    f"limit={limit}",
    "order=updated_at.desc",
    "select=id,title,body,tags,updated_at,created_at",
]
if query:
    # PostgREST `or=` with ilike on title+body. Single quotes around %q% are required.
    q = query.replace("*", "%").replace("'", "''")
    params.append(f"or=(title.ilike.*{q}*,body.ilike.*{q}*)")

url = f"{base}/notes?{'&'.join(params)}"
r = httpx.get(url, headers=head, timeout=15.0)
r.raise_for_status()
rows = r.json()

# Trim bodies for readability.
for row in rows:
    body = (row.get("body") or "")
    if len(body) > 800:
        row["body"] = body[:800] + "…"

print(json.dumps({"status": "ok", "result": {
    "query": query or None,
    "count": len(rows),
    "notes": rows,
}}))
"""
