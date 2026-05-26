"""Send an existing Gmail draft (after the user approved it)."""

KEY = "gmail.send_draft"
TITLE = "Send drafted email"
DESCRIPTION = (
    "Send a Gmail draft that was previously composed by gmail.compose "
    "or gmail.refine_draft. Inputs: draft_id (optional — defaults to "
    "the most recent draft on the chosen account), account (optional "
    "Gmail address; default primary). Use when the user says 'send "
    "it', 'send the draft', 'go ahead', or 'looks good, send'."
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
draft_id = (inputs.get("draft_id") or "").strip()
account_in = (inputs.get("account") or "").strip().lower()

accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts:
    print(json.dumps({"status":"error","error":
        "No Gmail account connected."}))
    raise SystemExit(0)

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def _account_for(email):
    if email:
        m = next((a for a in accounts if (a.get("email") or "").lower() == email.lower()), None)
        if m:
            return m
    return next((a for a in accounts if a.get("is_default")), accounts[0])

chosen = _account_for(account_in)
svc = _svc(chosen["token_json"])

if not draft_id:
    drafts = svc.users().drafts().list(userId="me", maxResults=1).execute().get("drafts", [])
    if not drafts:
        print(json.dumps({"status":"error","error":
            "No draft to send on " + chosen.get("email", "this account") + "."}))
        raise SystemExit(0)
    draft_id = drafts[0]["id"]

# Pull the draft to surface what we sent in the response, then send it.
draft = svc.users().drafts().get(userId="me", id=draft_id, format="metadata").execute()
headers = {h["name"]: h["value"] for h in
           draft.get("message", {}).get("payload", {}).get("headers", [])}

sent = svc.users().drafts().send(userId="me", body={"id": draft_id}).execute()

print(json.dumps({"status":"ok","result":{
    "kind": "email_sent",
    "to": headers.get("To"),
    "subject": headers.get("Subject"),
    "account": chosen.get("email"),
    "message_id": sent.get("id"),
    "thread_id": sent.get("threadId"),
    "label_ids": sent.get("labelIds") or [],
}}))
"""
