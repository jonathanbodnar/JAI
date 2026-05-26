"""Search Drive by name, content, or mime type."""

KEY = "drive.search_files"
TITLE = "Search Drive files"
DESCRIPTION = (
    "Search every connected Drive for files matching a name fragment, "
    "MIME type, or full-text content. Inputs: query (required, free text), "
    "mime (optional, e.g. 'application/vnd.google-apps.document'), max_results "
    "(default 25). Use for 'find the Q3 budget doc', 'search drive for "
    "marketing plan', 'all sheets about runway'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["drive"]

SOURCE = r"""
import os, json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
query = (inputs.get("query") or "").strip()
mime = inputs.get("mime")
max_results = int(inputs.get("max_results") or 25)

if not query:
    print(json.dumps({"status": "error", "error": "Missing required input: query"}))
    raise SystemExit(0)

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)

# Drive query: match name OR full-text content, plus optional mime filter.
safe_q = query.replace("'", "\\'")
drive_q = f"(name contains '{safe_q}' or fullText contains '{safe_q}') and trashed = false"
if mime:
    drive_q += f" and mimeType = '{mime}'"

accounts = json.loads(os.environ.get("DRIVE_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("DRIVE_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["DRIVE_OAUTH_JSON"])}]

by_account = {}
total = 0
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        res = svc.files().list(
            q=drive_q,
            orderBy="modifiedTime desc",
            pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,owners(emailAddress),webViewLink)",
        ).execute()
        files = res.get("files", [])
        by_account[a["email"]] = [{
            "name": f["name"],
            "type": f.get("mimeType", "").rsplit(".", 1)[-1],
            "modified": f.get("modifiedTime"),
            "owner": ((f.get("owners") or [{}])[0]).get("emailAddress"),
            "link": f.get("webViewLink"),
        } for f in files]
        total += len(files)
    except Exception as e:
        by_account[a["email"]] = {"error": str(e)[:200]}

print(json.dumps({"status": "ok", "result": {
    "query": query,
    "total": total,
    "by_account": by_account,
}}))
"""
