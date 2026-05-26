"""Fetch the plain-text content of a Google Doc, Sheet, or Slides file."""

KEY = "drive.read_doc"
TITLE = "Read Drive document"
DESCRIPTION = (
    "Pull the text content of a Google Doc / Sheet / Slides. Inputs: "
    "either file_id (preferred) OR name (we'll search and pick the most "
    "recently modified match). Use for 'read my Q3 plan doc', 'what's in "
    "the budget spreadsheet', 'open notes from yesterday'."
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
file_id = inputs.get("file_id")
name = inputs.get("name")

if not file_id and not name:
    print(json.dumps({"status": "error", "error": "Provide either file_id or name"}))
    raise SystemExit(0)

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)

# Maps Google MIME types to plain-text export MIME types.
EXPORT_AS = {
    "application/vnd.google-apps.document":     "text/plain",
    "application/vnd.google-apps.spreadsheet":  "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

accounts = json.loads(os.environ.get("DRIVE_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("DRIVE_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["DRIVE_OAUTH_JSON"])}]

for a in accounts:
    try:
        svc = _svc(a["token_json"])

        resolved_id = file_id
        meta = None
        if not resolved_id:
            safe = (name or "").replace("'", "\\'")
            res = svc.files().list(
                q=f"name contains '{safe}' and trashed = false",
                orderBy="modifiedTime desc", pageSize=5,
                fields="files(id,name,mimeType,webViewLink)",
            ).execute().get("files", [])
            if not res:
                continue
            meta = res[0]
            resolved_id = meta["id"]
        else:
            meta = svc.files().get(
                fileId=resolved_id,
                fields="id,name,mimeType,webViewLink",
            ).execute()

        mime = meta.get("mimeType")
        export_mime = EXPORT_AS.get(mime)
        if export_mime:
            content = svc.files().export(fileId=resolved_id, mimeType=export_mime).execute()
            text = content.decode("utf-8", errors="replace") if isinstance(content, (bytes, bytearray)) else str(content)
        else:
            # Non-Google native file — try a download. If binary, skip
            # and just return metadata.
            try:
                buf = svc.files().get_media(fileId=resolved_id).execute()
                text = buf.decode("utf-8", errors="replace") if isinstance(buf, (bytes, bytearray)) else str(buf)
            except Exception:
                text = ""

        text = (text or "")
        if len(text) > 30000:
            text = text[:30000] + "\n…(truncated)"

        print(json.dumps({"status": "ok", "result": {
            "account": a["email"],
            "id": resolved_id,
            "name": meta.get("name"),
            "type": (mime or "").rsplit(".", 1)[-1],
            "link": meta.get("webViewLink"),
            "content": text,
            "content_length": len(text),
        }}))
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        continue

print(json.dumps({"status": "error", "error": "Document not found in any connected Drive"}))
"""
