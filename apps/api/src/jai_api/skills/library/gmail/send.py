"""Compose and send an email through the default Gmail account."""

KEY = "gmail.send"
TITLE = "Send email"
DESCRIPTION = (
    "Compose and send an email from the user's default Gmail account. "
    "Inputs: to (string or list), subject, body (plain text), optional cc/bcc. "
    "Use for 'send an email to ...', 'reply to ...', 'draft and send ...'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["gmail"]

SOURCE = r"""
import os, json, base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
to_field = inputs.get("to")
subject = inputs.get("subject") or "(no subject)"
body = inputs.get("body") or ""
cc = inputs.get("cc")
bcc = inputs.get("bcc")
from_account = (inputs.get("from") or "").lower().strip()

if not to_field:
    print(json.dumps({"status": "error", "error": "Missing required input: to"}))
    raise SystemExit(0)

if isinstance(to_field, list):
    to_field = ", ".join(to_field)
if isinstance(cc, list):
    cc = ", ".join(cc)
if isinstance(bcc, list):
    bcc = ", ".join(bcc)

accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("GMAIL_OAUTH_JSON"):
    accounts = [{"email": "default", "is_default": True, "token_json": json.loads(os.environ["GMAIL_OAUTH_JSON"])}]

# Pick the requested account by email substring, else the default,
# else the first available.
acct = None
if from_account:
    acct = next((a for a in accounts if from_account in a["email"].lower()), None)
if not acct:
    acct = next((a for a in accounts if a.get("is_default")), None) or (accounts[0] if accounts else None)

if not acct:
    print(json.dumps({"status": "error", "error": "No Gmail account connected"}))
    raise SystemExit(0)

info = dict(acct["token_json"])
info["token"] = info.get("token") or info.get("access_token")
creds = Credentials.from_authorized_user_info(info)
if not creds.valid:
    creds.refresh(Request())
svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

msg = MIMEText(body)
msg["to"] = to_field
msg["from"] = acct["email"]
msg["subject"] = subject
if cc:
    msg["cc"] = cc
if bcc:
    msg["bcc"] = bcc

raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()

print(json.dumps({"status": "ok", "result": {
    "id": sent.get("id"),
    "thread_id": sent.get("threadId"),
    "from": acct["email"],
    "to": to_field,
    "subject": subject,
}}))
"""
