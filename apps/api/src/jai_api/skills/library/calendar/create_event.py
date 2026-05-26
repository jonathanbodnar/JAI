"""Book a calendar event on the default calendar."""

KEY = "calendar.create_event"
TITLE = "Create calendar event"
DESCRIPTION = (
    "Create a new event on the user's default Google Calendar. "
    "Inputs: title (required), start (ISO datetime, required), end (ISO datetime, "
    "required), attendees (list of emails, optional), description (optional), "
    "location (optional). Use for 'schedule a meeting', 'book a call', 'add to calendar'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["calendar"]

SOURCE = r"""
import os, json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
title = inputs.get("title") or inputs.get("summary")
start = inputs.get("start")
end = inputs.get("end")
attendees = inputs.get("attendees") or []
description = inputs.get("description") or ""
location = inputs.get("location") or ""
from_account = (inputs.get("from") or "").lower().strip()

if not title or not start or not end:
    print(json.dumps({"status": "error", "error": "Missing required input(s): title, start, end (ISO datetime)"}))
    raise SystemExit(0)

accounts = json.loads(os.environ.get("CALENDAR_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("CALENDAR_OAUTH_JSON"):
    accounts = [{"email": "default", "is_default": True, "token_json": json.loads(os.environ["CALENDAR_OAUTH_JSON"])}]

acct = None
if from_account:
    acct = next((a for a in accounts if from_account in a["email"].lower()), None)
if not acct:
    acct = next((a for a in accounts if a.get("is_default")), None) or (accounts[0] if accounts else None)
if not acct:
    print(json.dumps({"status": "error", "error": "No Google Calendar account connected"}))
    raise SystemExit(0)

info = dict(acct["token_json"])
info["token"] = info.get("token") or info.get("access_token")
creds = Credentials.from_authorized_user_info(info)
if not creds.valid:
    creds.refresh(Request())
svc = build("calendar", "v3", credentials=creds, cache_discovery=False)

body = {
    "summary": title,
    "start": {"dateTime": start},
    "end": {"dateTime": end},
}
if attendees:
    if isinstance(attendees, str):
        attendees = [a.strip() for a in attendees.split(",") if a.strip()]
    body["attendees"] = [{"email": e} for e in attendees]
if description:
    body["description"] = description
if location:
    body["location"] = location

created = svc.events().insert(
    calendarId="primary",
    body=body,
    sendUpdates="all" if attendees else "none",
).execute()

print(json.dumps({"status": "ok", "result": {
    "id": created.get("id"),
    "html_link": created.get("htmlLink"),
    "calendar": acct["email"],
    "summary": created.get("summary"),
    "start": (created.get("start") or {}).get("dateTime"),
    "end": (created.get("end") or {}).get("dateTime"),
    "attendees": [a.get("email") for a in (created.get("attendees") or [])],
}}))
"""
