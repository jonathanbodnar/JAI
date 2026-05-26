"""Create a new task in JAI's task list."""

KEY = "jai.create_task"
TITLE = "Create task"
DESCRIPTION = (
    "Add a new task to JAI's task list. Inputs: title (required), notes "
    "(optional), due_at (optional ISO datetime). Use for 'add a task to', "
    "'remind me to', 'create a todo for'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["jai"]

SOURCE = r"""
import os, json
import httpx

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
title = (inputs.get("title") or "").strip()
notes = (inputs.get("notes") or "").strip() or None
due_at = inputs.get("due_at") or None

if not title:
    # Last resort: pull from the raw intent if the orchestrator didn't extract one.
    intent = os.environ.get("JAI_USER_INTENT", "").strip()
    # Strip common task verbs from the front so the title isn't "remind me to ..." literally.
    import re
    title = re.sub(r"^\s*(?:add a task( to)?|remind me to|create a todo (for|to)?|todo:?)\s*",
                   "", intent, flags=re.IGNORECASE).strip().rstrip(".")
if not title:
    print(json.dumps({"status": "error", "error": "Missing required input: title"}))
    raise SystemExit(0)

base = os.environ["JAI_SUPABASE_URL"].rstrip("/") + "/rest/v1"
head = {
    "apikey": os.environ["JAI_SUPABASE_KEY"],
    "Authorization": f"Bearer {os.environ['JAI_SUPABASE_KEY']}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

body = {
    "user_id": os.environ["JAI_USER_ID"],
    "title": title,
    "is_complete": False,
}
if notes:
    body["notes"] = notes
if due_at:
    body["due_at"] = due_at

r = httpx.post(f"{base}/tasks", headers=head, json=body, timeout=15.0)
r.raise_for_status()
row = (r.json() or [{}])[0]

print(json.dumps({"status": "ok", "result": {
    "id": row.get("id"),
    "title": row.get("title"),
    "due_at": row.get("due_at"),
    "created_at": row.get("created_at"),
}}))
"""
