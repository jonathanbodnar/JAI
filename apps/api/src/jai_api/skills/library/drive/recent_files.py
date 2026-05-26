"""List recently modified Google Drive files."""

KEY = "drive.recent_files"
TITLE = "Recent Drive files"
DESCRIPTION = (
    "List the most recently modified Google Drive files across every "
    "connected Drive account. Use for 'what files have I been working on', "
    "'recent docs', 'my last spreadsheets'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["drive"]

SOURCE = r"""
import os, json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = {}
try:
    inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
except Exception:
    pass
max_results = int(inputs.get("max_results") or 25)
query_filter = inputs.get("query")  # e.g. "name contains 'budget'"

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)

accounts = json.loads(os.environ.get("DRIVE_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("DRIVE_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["DRIVE_OAUTH_JSON"])}]

by_account = {}
total = 0
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        q = "trashed = false"
        if query_filter:
            q += f" and ({query_filter})"
        res = svc.files().list(
            q=q,
            orderBy="modifiedTime desc",
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,owners(emailAddress),webViewLink,size)",
        ).execute()
        files = res.get("files", [])
        by_account[a["email"]] = [{
            "name": f.get("name"),
            "type": f.get("mimeType", "").rsplit(".", 1)[-1],
            "modified": f.get("modifiedTime"),
            "owner": ((f.get("owners") or [{}])[0]).get("emailAddress"),
            "link": f.get("webViewLink"),
            "size": f.get("size"),
        } for f in files]
        total += len(files)
    except Exception as e:
        by_account[a["email"]] = {"error": str(e)[:200]}

print(json.dumps({"status": "ok", "result": {
    "total": total,
    "by_account": by_account,
}}))
"""
