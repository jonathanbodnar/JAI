"""Refine an existing Gmail draft using the user's edit instructions.

Picks up the most recent draft from skill_output (carried forward in
the LangGraph state) so the user can say things like "make it shorter"
or "add a closing line about the timeline" without restating the whole
email. Updates the Gmail draft in place and returns the new preview.
"""

KEY = "gmail.refine_draft"
TITLE = "Refine email draft"
DESCRIPTION = (
    "Update an existing Gmail draft based on the user's edits. Inputs: "
    "draft_id (Gmail draft ID — defaults to the most recent draft), "
    "instructions (the user's edit request), account (optional Gmail "
    "address). Use when the user gave instructions like 'make it "
    "shorter', 'add a line about X', 'less formal', 'rewrite the "
    "intro' AFTER gmail.compose has produced a draft."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["gmail"]

SOURCE = r"""
import os, json, re, base64
from email.message import EmailMessage
import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
intent = (os.environ.get("JAI_USER_INTENT") or "").strip()

draft_id = (inputs.get("draft_id") or "").strip()
instructions = (inputs.get("instructions") or intent or "").strip()
account_in = (inputs.get("account") or "").strip().lower()

accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts:
    print(json.dumps({"status":"error","error":
        "No Gmail account connected."}))
    raise SystemExit(0)

# Find the latest draft if not specified. Drafts are scoped per
# account, so we search the account most likely to own it.
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
    # No id given — grab the most recent draft on the chosen account.
    drafts = svc.users().drafts().list(userId="me", maxResults=1).execute().get("drafts", [])
    if not drafts:
        print(json.dumps({"status":"error","error":
            "No existing draft found on " + chosen.get("email", "this account") +
            ". Ask me to draft an email first."}))
        raise SystemExit(0)
    draft_id = drafts[0]["id"]

# Pull the existing draft's contents.
draft = svc.users().drafts().get(userId="me", id=draft_id, format="full").execute()
msg = draft.get("message", {})
headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
original_subject = headers.get("Subject", "")
original_to = headers.get("To", "")

# Body extraction — prefer text/plain, fall back to first text part.
def _extract_body(payload):
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    if mime.startswith("text/") and payload.get("body", {}).get("data"):
        try:
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
        except Exception:
            return ""
    for p in payload.get("parts") or []:
        if p.get("mimeType") == "text/plain":
            return _extract_body(p)
    for p in payload.get("parts") or []:
        b = _extract_body(p)
        if b:
            return b
    return ""

original_body = _extract_body(msg.get("payload")).strip()

# Ask Kimi to apply the edit.
or_key = os.environ.get("OPENROUTER_API_KEY")
if not or_key:
    print(json.dumps({"status":"error","error":
        "OpenRouter key is not available — can't refine the draft."}))
    raise SystemExit(0)

prompt = f'''You are JAI, revising an existing email draft.

Recipient: {original_to}
Current subject: {original_subject}

Current body:
---
{original_body}
---

User's edit instructions:
{instructions}

Apply the edits faithfully. Keep everything else the same unless the
user told you to change it. Don't invent details. If the user asked
for a different subject, update it; otherwise keep the current one.

Return STRICT JSON:
  subject – new (or unchanged) subject
  body    – the full revised body
Output JSON ONLY.'''

r = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {or_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://app.ftr.me",
        "X-Title": "JAI",
    },
    json={
        "model": "moonshotai/kimi-k2.6",
        "temperature": 0.35,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    },
    timeout=45.0,
)
r.raise_for_status()
raw = r.json()["choices"][0]["message"]["content"]
try:
    revised = json.loads(raw)
except Exception:
    m = re.search(r"\{[\s\S]*\}", raw)
    revised = json.loads(m.group(0)) if m else {"subject": original_subject, "body": raw}

new_subject = (revised.get("subject") or original_subject).strip()
new_body = (revised.get("body") or "").strip()

# Update the draft in place.
new_msg = EmailMessage()
new_msg["To"] = original_to
new_msg["From"] = chosen.get("email")
new_msg["Subject"] = new_subject
new_msg.set_content(new_body)
new_raw = base64.urlsafe_b64encode(new_msg.as_bytes()).decode()

svc.users().drafts().update(
    userId="me", id=draft_id,
    body={"message": {"raw": new_raw}},
).execute()

print(json.dumps({"status":"ok","result":{
    "kind": "email_draft",
    "draft_id": draft_id,
    "account": chosen.get("email"),
    "to": original_to,
    "subject": new_subject,
    "body": new_body,
    "previous_body": original_body,
    "applied": instructions[:200],
    "next_actions": [
        "More edits, or say 'send it' to send.",
    ],
}}))
"""
