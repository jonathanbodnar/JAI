"""List the user's living KPIs from JAI's `kpis` table."""

KEY = "jai.kpi_list"
TITLE = "List my KPIs"
DESCRIPTION = (
    "Return the user's living KPIs (label, value, format, trend) from "
    "JAI's database. Use for 'show my KPIs', 'what numbers am I "
    "tracking', 'what's my MRR'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["jai"]

SOURCE = r"""
import os, json
import httpx

base = os.environ["JAI_SUPABASE_URL"].rstrip("/") + "/rest/v1"
head = {
    "apikey": os.environ["JAI_SUPABASE_KEY"],
    "Authorization": f"Bearer {os.environ['JAI_SUPABASE_KEY']}",
}
uid = os.environ["JAI_USER_ID"]

url = (
    f"{base}/kpis?user_id=eq.{uid}&is_visible=eq.true"
    "&select=key,label,value,previous,format,unit,source,last_updated_at"
    "&order=sort_order.asc,created_at.asc"
)
r = httpx.get(url, headers=head, timeout=15.0)
r.raise_for_status()
rows = r.json()

print(json.dumps({"status": "ok", "result": {
    "count": len(rows),
    "kpis": rows,
}}))
"""
