"""List the most recent inbox emails across every connected Gmail account."""

KEY = "gmail.read_inbox"
TITLE = "Read recent emails"
DESCRIPTION = (
    "List the 10 most recent INBOX emails from every connected Gmail account. "
    "Use for queries like 'read my emails', 'what's in my inbox', "
    "'show me recent mail', 'overview of emails today'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["gmail"]

SOURCE = r"""
import os, json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("GMAIL_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["GMAIL_OAUTH_JSON"])}]

per_account = {}
all_emails = []
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        ids = svc.users().messages().list(userId="me", maxResults=10, labelIds=["INBOX"]).execute().get("messages", [])
        rows = []
        for m in ids:
            full = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            h = {x["name"]: x["value"] for x in full["payload"].get("headers", [])}
            rows.append({
                "from": h.get("From"),
                "subject": h.get("Subject"),
                "date": h.get("Date"),
                "snippet": (full.get("snippet") or "")[:200],
                "unread": "UNREAD" in (full.get("labelIds") or []),
            })
        per_account[a["email"]] = rows
        all_emails.extend(rows)
    except Exception as e:
        per_account[a["email"]] = {"error": str(e)[:200]}

print(json.dumps({"status": "ok", "result": {
    "total": len(all_emails),
    "by_account": per_account,
}}))
"""
