"""Count unread messages per Gmail account."""

KEY = "gmail.unread_count"
TITLE = "Unread email count"
DESCRIPTION = (
    "Return the number of unread INBOX emails per connected Gmail account. "
    "Use for 'how many unread emails do I have', 'inbox zero status', "
    "'am I behind on email'."
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

counts = {}
total = 0
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        lbl = svc.users().labels().get(userId="me", id="INBOX").execute()
        unread = int(lbl.get("messagesUnread", 0))
        total_msgs = int(lbl.get("messagesTotal", 0))
        counts[a["email"]] = {"unread": unread, "inbox_total": total_msgs}
        total += unread
    except Exception as e:
        counts[a["email"]] = {"error": str(e)[:200]}

print(json.dumps({"status": "ok", "result": {
    "total_unread": total,
    "by_account": counts,
}}))
"""
