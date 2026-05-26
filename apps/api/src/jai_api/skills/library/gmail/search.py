"""Search Gmail with a free-text query across every connected account."""

KEY = "gmail.search"
TITLE = "Search emails"
DESCRIPTION = (
    "Search every connected Gmail account using Gmail's standard search "
    "syntax (e.g. 'from:stripe', 'subject:invoice newer_than:7d', "
    "'has:attachment'). Use for queries like 'find emails from Bob', "
    "'show invoices', 'anything from acme.com this week'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["gmail"]

SOURCE = r"""
import os, json, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Inputs are passed via JAI_SKILL_INPUTS_JSON when the orchestrator
# specifies them; fall back to a generic recent-mail search otherwise.
inputs = {}
try:
    inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
except Exception:
    pass
query = (inputs.get("query") or "newer_than:7d").strip()
max_results = int(inputs.get("max_results") or 15)

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
total = 0
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        ids = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute().get("messages", [])
        rows = []
        for m in ids:
            full = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date", "To"],
            ).execute()
            h = {x["name"]: x["value"] for x in full["payload"].get("headers", [])}
            rows.append({
                "from": h.get("From"),
                "to": h.get("To"),
                "subject": h.get("Subject"),
                "date": h.get("Date"),
                "snippet": (full.get("snippet") or "")[:200],
            })
        per_account[a["email"]] = rows
        total += len(rows)
    except Exception as e:
        per_account[a["email"]] = {"error": str(e)[:200]}

print(json.dumps({"status": "ok", "result": {
    "query": query,
    "total": total,
    "by_account": per_account,
}}))
"""
