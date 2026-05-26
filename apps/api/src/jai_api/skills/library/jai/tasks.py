"""List the user's tasks from JAI's own Supabase."""

KEY = "jai.list_tasks"
TITLE = "List my tasks"
DESCRIPTION = (
    "Return the user's open tasks from JAI's task list. Inputs: status "
    "(open/done/all, default 'open'), limit (default 50). Use for 'what's "
    "on my todo list', 'show my tasks', 'what do I need to do'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["jai"]

SOURCE = r"""
import os, json
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
status_filter = (inputs.get("status") or "open").lower()
limit = int(inputs.get("limit") or 50)

base = os.environ["JAI_SUPABASE_URL"].rstrip("/") + "/rest/v1"
head = {
    "apikey": os.environ["JAI_SUPABASE_KEY"],
    "Authorization": f"Bearer {os.environ['JAI_SUPABASE_KEY']}",
}
uid = os.environ["JAI_USER_ID"]

params = [f"user_id=eq.{uid}", f"limit={limit}", "order=created_at.desc"]
if status_filter == "open":
    params.append("is_complete=eq.false")
elif status_filter == "done":
    params.append("is_complete=eq.true")
# 'all' adds no filter

url = f"{base}/tasks?{'&'.join(params)}&select=id,title,notes,is_complete,due_at,created_at,updated_at"
r = httpx.get(url, headers=head, timeout=15.0)
r.raise_for_status()
rows = r.json()

print(json.dumps({"status": "ok", "result": {
    "filter": status_filter,
    "count": len(rows),
    "tasks": rows,
}}))
"""
