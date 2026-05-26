"""Archive messages matching a Gmail query (removes INBOX label, no delete)."""

KEY = "gmail.archive"
TITLE = "Archive emails by query"
DESCRIPTION = (
    "Archive emails matching a Gmail search query (removes INBOX label, "
    "does NOT delete). Inputs: query (required, e.g. 'from:noreply older_than:7d'), "
    "max_results (default 50), dry_run (default true). Use for 'clean up "
    "newsletters', 'archive old promotions', 'mass archive'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["gmail"]

SOURCE = r"""
import os, json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
query = (inputs.get("query") or "").strip()
max_results = int(inputs.get("max_results") or 50)
# Default to dry-run so users don't accidentally archive in bulk on
# their first call. They can pass dry_run=false to actually execute.
dry_run = inputs.get("dry_run")
dry_run = True if dry_run is None else bool(dry_run)

if not query:
    print(json.dumps({"status": "error", "error": "Missing required input: query (Gmail search syntax)"}))
    raise SystemExit(0)

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
total_archived = 0
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        ids = [m["id"] for m in svc.users().messages().list(
            userId="me", q=f"{query} in:inbox", maxResults=max_results,
        ).execute().get("messages", [])]
        if not ids:
            per_account[a["email"]] = {"matched": 0, "archived": 0}
            continue
        if dry_run:
            # Just describe what we would have done.
            samples = []
            for m_id in ids[:5]:
                meta = svc.users().messages().get(
                    userId="me", id=m_id, format="metadata",
                    metadataHeaders=["From", "Subject"],
                ).execute()
                h = {x["name"]: x["value"] for x in meta["payload"].get("headers", [])}
                samples.append({"from": h.get("From"), "subject": h.get("Subject")})
            per_account[a["email"]] = {
                "matched": len(ids), "archived": 0,
                "preview": samples, "note": "dry-run; pass dry_run=false to archive",
            }
        else:
            svc.users().messages().batchModify(userId="me", body={
                "ids": ids, "removeLabelIds": ["INBOX"],
            }).execute()
            per_account[a["email"]] = {"matched": len(ids), "archived": len(ids)}
            total_archived += len(ids)
    except Exception as e:
        per_account[a["email"]] = {"error": str(e)[:200]}

print(json.dumps({"status": "ok", "result": {
    "query": query,
    "dry_run": dry_run,
    "total_archived": total_archived,
    "by_account": per_account,
}}))
"""
