"""Draft an email via the JAI voice (Kimi K2.6) and save it as a
Gmail draft (NOT sent). Returns a preview the user can iterate on.

The draft lives in the user's actual Gmail Drafts folder so it
survives server restarts and shows up in the Gmail UI. We keep the
Gmail draft_id and recipient + the account it was saved on in the
skill output so follow-up turns can refine or send it.
"""

KEY = "gmail.compose"
TITLE = "Draft an email"
DESCRIPTION = (
    "Draft an email in the user's voice and save it to Gmail Drafts "
    "WITHOUT sending it. Inputs: to (recipient email), subject "
    "(optional — JAI writes one if missing), brief (the user's intent "
    "for the email, free text), account (optional Gmail address to "
    "draft from; default is the primary account), tone (optional: "
    "casual / formal / direct, default casual). Use for any 'draft "
    "an email', 'write an email', 'compose a message', 'reply to X' "
    "request. Returns a preview the user can iterate on; pair with "
    "gmail.send_draft to actually send."
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

# --- Resolve recipient + subject + brief from inputs OR intent text. ---
def _parse_intent_email(text):
    m = re.search(r"\b([\w.+\-]+@[\w\-]+\.[\w\-.]+)\b", text or "")
    return m.group(1) if m else None

to_addr = (inputs.get("to") or "").strip() or _parse_intent_email(intent) or ""
subject = (inputs.get("subject") or "").strip()
brief = (inputs.get("brief") or intent or "").strip()
account = (inputs.get("account") or "").strip().lower()
tone = (inputs.get("tone") or "casual").strip().lower()

if not to_addr:
    print(json.dumps({"status":"error","error":
        "I need a recipient email address — include one in the request "
        "(e.g. 'draft an email to lisa@acme.com about ...')."}))
    raise SystemExit(0)
if not brief:
    print(json.dumps({"status":"error","error":
        "I need a brief — tell me what the email should say or accomplish."}))
    raise SystemExit(0)

# --- Pick the account. Default = is_default OR first. ---
accounts = json.loads(os.environ.get("GMAIL_ACCOUNTS_JSON") or "[]")
if not accounts:
    print(json.dumps({"status":"error","error":
        "No Gmail account connected. Open Settings → Connections to link one."}))
    raise SystemExit(0)
chosen = None
if account:
    chosen = next((a for a in accounts if (a.get("email") or "").lower() == account), None)
if chosen is None:
    chosen = next((a for a in accounts if a.get("is_default")), accounts[0])

# --- Ask Kimi for the body (and a subject if not provided). ---
or_key = os.environ.get("OPENROUTER_API_KEY")
if not or_key:
    print(json.dumps({"status":"error","error":
        "OpenRouter key is not available — can't draft the body."}))
    raise SystemExit(0)

prompt = f'''You are JAI, drafting an email on behalf of the user.

User brief:
{brief}

Recipient: {to_addr}
Sender: {chosen.get("email")}
Tone: {tone}
{"Subject hint: " + subject if subject else "(no subject provided — write one)"}

Write a complete email. Return STRICT JSON with keys:
  subject  – short subject line (sentence case)
  body     – the full email body, plain text, with line breaks
  signoff  – the closer line you used (e.g. "Best,")

Rules:
- Match the requested tone. Casual = warm, contractions, short
  paragraphs. Formal = full sentences, more structure. Direct = bullet
  or numbered structure only when it actually helps.
- Never invent specifics the user didn't give you (no fake dates,
  numbers, or names). When unsure, leave a [bracketed placeholder].
- Sign off as the user — use their first name from the sender email
  if obvious (e.g. "jb@acme.com" -> "JB"). Don't add titles.
- Output JSON ONLY. No prose around it.'''

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
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    },
    timeout=45.0,
)
r.raise_for_status()
raw = r.json()["choices"][0]["message"]["content"]
try:
    draft = json.loads(raw)
except Exception:
    m = re.search(r"\{[\s\S]*\}", raw)
    draft = json.loads(m.group(0)) if m else {"subject": subject or "(no subject)", "body": raw, "signoff": ""}

final_subject = (draft.get("subject") or subject or "(no subject)").strip()
final_body = (draft.get("body") or "").strip()

# --- Save to Gmail drafts on the chosen account. ---
def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

svc = _svc(chosen["token_json"])
msg = EmailMessage()
msg["To"] = to_addr
msg["From"] = chosen.get("email")
msg["Subject"] = final_subject
msg.set_content(final_body)
raw_bytes = base64.urlsafe_b64encode(msg.as_bytes()).decode()

resp = svc.users().drafts().create(
    userId="me", body={"message": {"raw": raw_bytes}}
).execute()

print(json.dumps({"status":"ok","result":{
    "kind": "email_draft",
    "draft_id": resp["id"],
    "message_id": resp["message"]["id"],
    "account": chosen.get("email"),
    "to": to_addr,
    "subject": final_subject,
    "body": final_body,
    "tone": tone,
    "saved_to": "Gmail Drafts (not sent)",
    "next_actions": [
        "Reply with edits to refine the draft",
        "Say 'send it' to send",
    ],
}}))
"""
