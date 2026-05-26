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
from concurrent.futures import ThreadPoolExecutor
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

def _fetch_one(svc, mid):
    full = svc.users().messages().get(
        userId="me", id=mid, format="metadata",
        metadataHeaders=["From", "Subject", "Date"],
    ).execute()
    h = {x["name"]: x["value"] for x in full["payload"].get("headers", [])}
    return {
        "from": h.get("From"),
        "subject": h.get("Subject"),
        "date": h.get("Date"),
        "snippet": (full.get("snippet") or "")[:200],
        "unread": "UNREAD" in (full.get("labelIds") or []),
    }

def _read_account(account):
    # Returns (email, rows) or (email, {"error": ...}).
    email = account.get("email") or "unknown"
    try:
        svc = _svc(account["token_json"])
        ids = svc.users().messages().list(
            userId="me", maxResults=10, labelIds=["INBOX"],
        ).execute().get("messages", [])
        if not ids:
            return email, []
        with ThreadPoolExecutor(max_workers=8) as ex:
            rows = list(ex.map(lambda m: _fetch_one(svc, m["id"]), ids))
        return email, rows
    except Exception as e:
        return email, {"error": str(e)[:200]}

accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("GMAIL_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["GMAIL_OAUTH_JSON"])}]

per_account = {}
total = 0
# Outer pool fans out across accounts in parallel; inner pool fans out
# across messages within each account. With 3 accounts × 10 messages
# we collapse what was ~30 sequential round-trips into ~2 batches.
with ThreadPoolExecutor(max_workers=max(1, len(accounts))) as ex:
    for email, result in ex.map(_read_account, accounts):
        per_account[email] = result
        if isinstance(result, list):
            total += len(result)

print(json.dumps({"status": "ok", "result": {
    "total": total,
    "by_account": per_account,
}}))
"""
