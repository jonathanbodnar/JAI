"""Fetch a full Gmail thread (all messages, headers, snippets)."""

KEY = "gmail.thread"
TITLE = "Read full email thread"
DESCRIPTION = (
    "Pull every message in a Gmail thread, including all replies. "
    "Inputs: either thread_id OR subject (we'll find the most recent thread "
    "with a matching subject). Use for 'show me the full conversation', "
    "'what did Bob say in that thread', 'pull the thread about X'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["gmail"]

SOURCE = r"""
import os, json, re, base64
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
thread_id = inputs.get("thread_id")
subject = inputs.get("subject")

if not thread_id and not subject:
    print(json.dumps({"status": "error", "error": "Provide either thread_id or subject"}))
    raise SystemExit(0)

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def _extract_text(payload):
    if not payload:
        return ""
    if payload.get("body", {}).get("data"):
        try:
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        except Exception:
            return ""
    for p in payload.get("parts", []):
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            try:
                return base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", errors="replace")
            except Exception:
                continue
    # Fall back to first part with text/html (strip tags crudely).
    for p in payload.get("parts", []):
        if p.get("mimeType") == "text/html" and p.get("body", {}).get("data"):
            try:
                raw = base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", errors="replace")
                return re.sub(r"<[^>]+>", " ", raw)
            except Exception:
                continue
    return ""

accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("GMAIL_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["GMAIL_OAUTH_JSON"])}]

# Walk accounts until one of them owns the thread.
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        tid = thread_id
        if not tid:
            res = svc.users().messages().list(
                userId="me", q=f'subject:"{subject}"', maxResults=5,
            ).execute().get("messages", [])
            if not res:
                continue
            tid = res[0]["threadId"]

        thread = svc.users().threads().get(userId="me", id=tid, format="full").execute()
        messages = []
        for m in thread.get("messages", []):
            h = {x["name"]: x["value"] for x in m["payload"].get("headers", [])}
            body = _extract_text(m["payload"])
            messages.append({
                "from": h.get("From"),
                "to": h.get("To"),
                "date": h.get("Date"),
                "subject": h.get("Subject"),
                "body": (body or "").strip()[:3000],
            })
        print(json.dumps({"status": "ok", "result": {
            "account": a["email"],
            "thread_id": tid,
            "message_count": len(messages),
            "messages": messages,
        }}))
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        continue

print(json.dumps({"status": "error", "error": "Thread not found in any connected account"}))
"""
