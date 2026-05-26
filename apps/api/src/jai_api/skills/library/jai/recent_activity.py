"""High-level summary of recent JAI activity: messages, skill runs, tasks, notes."""

KEY = "jai.recent_activity"
TITLE = "Recent JAI activity"
DESCRIPTION = (
    "Return a snapshot of what's happened in JAI lately: recent chat "
    "messages, skill runs, new tasks/notes, document ingest. Use for "
    "'what have I been working on', 'JAI usage this week', 'recent activity'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["jai"]

SOURCE = r"""
import os, json
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
days = int(inputs.get("days") or 7)

base = os.environ["JAI_SUPABASE_URL"].rstrip("/") + "/rest/v1"
head = {
    "apikey": os.environ["JAI_SUPABASE_KEY"],
    "Authorization": f"Bearer {os.environ['JAI_SUPABASE_KEY']}",
}
uid = os.environ["JAI_USER_ID"]

from datetime import datetime, timedelta, timezone
since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

def _q(table, extra=""):
    url = f"{base}/{table}?user_id=eq.{uid}&created_at=gte.{since}&{extra}"
    return httpx.get(url, headers=head, timeout=15.0).json()

result = {
    "window_days": days,
    "messages": len(_q("messages", "select=id,limit=500")),
    "skill_runs": _q("skill_runs", "select=skill_id,status,started_at&order=started_at.desc&limit=10"),
    "new_tasks": _q("tasks", "select=id,title,is_complete,created_at&order=created_at.desc&limit=10"),
    "new_notes": _q("notes", "select=id,title,updated_at&order=updated_at.desc&limit=10"),
    "new_documents": _q("documents", "select=title,status,created_at&order=created_at.desc&limit=10"),
}

# Skill usage summary
try:
    runs = httpx.get(
        f"{base}/skill_runs?user_id=eq.{uid}&started_at=gte.{since}&select=skill_id,status",
        headers=head, timeout=15.0,
    ).json()
    from collections import Counter
    by_skill = Counter([r["skill_id"] for r in runs])
    result["skill_run_count_by_id"] = dict(by_skill.most_common(10))
    result["total_skill_runs"] = len(runs)
    result["failed_skill_runs"] = sum(1 for r in runs if r.get("status") == "error")
except Exception:
    pass

print(json.dumps({"status": "ok", "result": result}))
"""
