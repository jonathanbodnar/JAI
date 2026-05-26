"""Upsert (create or update) a living KPI shown in JAI's header strip.

Use this any time the user tells JAI a number worth tracking — MRR,
active users, deal stage counts, weight, sleep, anything. Skills that
run on a schedule (cron) should also call this to keep the header
pills fresh automatically.
"""

KEY = "jai.kpi_upsert"
TITLE = "Track or update a KPI"
DESCRIPTION = (
    "Create or update one of the living KPIs shown across the top of the "
    "JAI header. Inputs: key (slug like 'mrr' or 'active_users'), label "
    "(human title), value (any string — '$48,250', '12.4%', '34', '3d 4h'), "
    "format (one of raw/number/currency/percent/duration), unit (optional, "
    "e.g. 'users'), icon (optional lucide name), source (default 'skill'). "
    "Use when the user says 'track X = N' or after a skill computes a "
    "metric you want pinned to the top of the app."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["jai"]

SOURCE = r"""
import os, json, re
from datetime import datetime, timezone
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
intent = (os.environ.get("JAI_USER_INTENT") or "").strip()

def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", s.strip().lower()).strip("_")
    return s or "kpi"

def coerce(v):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        return str(v)
    return str(v).strip() or "—"

key = (inputs.get("key") or "").strip().lower()
label = (inputs.get("label") or "").strip()
value = coerce(inputs.get("value"))
fmt = (inputs.get("format") or "raw").strip().lower()
if fmt not in ("raw", "number", "currency", "percent", "duration"):
    fmt = "raw"
unit = inputs.get("unit")
icon = inputs.get("icon")
source = inputs.get("source") or "skill"

# If the caller didn't structure inputs, try to pull "label = value"
# pairs out of the intent itself.
if not key and intent:
    m = re.search(r"([A-Za-z][A-Za-z0-9 _-]+?)\s*(?:=|:|to|->)\s*([\$%]?[\d.,]+[%kKmMbB]?)", intent)
    if m:
        label = label or m.group(1).strip()
        value = coerce(m.group(2))
if not key and label:
    key = slugify(label)
if not label and key:
    label = key.replace("_", " ").title()
if not key:
    print(json.dumps({"status": "error", "error": "Need a key (slug) and label for the KPI."}))
    raise SystemExit(0)

base = os.environ["JAI_SUPABASE_URL"].rstrip("/") + "/rest/v1"
auth = {
    "apikey": os.environ["JAI_SUPABASE_KEY"],
    "Authorization": f"Bearer {os.environ['JAI_SUPABASE_KEY']}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}
uid = os.environ["JAI_USER_ID"]

now = datetime.now(timezone.utc).isoformat()

found = httpx.get(
    f"{base}/kpis?user_id=eq.{uid}&key=eq.{key}",
    headers=auth, timeout=15.0,
).json()

if found:
    cur = found[0]
    history = list(cur.get("history") or [])
    history.append({"value": value, "at": now})
    history = history[-30:]
    payload = {
        "label": label or cur["label"],
        "value": value,
        "previous": cur.get("value"),
        "format": fmt,
        "unit": unit if unit is not None else cur.get("unit"),
        "icon": icon if icon is not None else cur.get("icon"),
        "source": source,
        "history": history,
        "last_updated_at": now,
    }
    r = httpx.patch(
        f"{base}/kpis?id=eq.{cur['id']}&user_id=eq.{uid}",
        headers=auth, json=payload, timeout=15.0,
    )
    r.raise_for_status()
    row = r.json()[0]
    action = "updated"
else:
    payload = {
        "user_id": uid,
        "key": key,
        "label": label,
        "value": value,
        "format": fmt,
        "unit": unit,
        "icon": icon,
        "source": source,
        "history": [{"value": value, "at": now}],
        "last_updated_at": now,
    }
    r = httpx.post(f"{base}/kpis", headers=auth, json=payload, timeout=15.0)
    r.raise_for_status()
    row = r.json()[0]
    action = "created"

print(json.dumps({"status": "ok", "result": {
    "action": action,
    "key": row["key"],
    "label": row["label"],
    "value": row["value"],
    "previous": row.get("previous"),
    "format": row.get("format"),
}}))
"""
