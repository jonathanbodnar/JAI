"""List today's and upcoming calendar events across every connected calendar."""

KEY = "calendar.agenda"
TITLE = "Show calendar agenda"
DESCRIPTION = (
    "List calendar events for a given window (default: today + next 7 days) "
    "across every connected Google Calendar. Use for 'what's on my calendar', "
    "'what do I have today', 'this week's meetings', 'upcoming events'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["calendar"]

SOURCE = r"""
import os, json
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = {}
try:
    inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
except Exception:
    pass

# Window: default = now → +7 days. Inputs can override with ISO strings.
now = datetime.now(timezone.utc)
start = inputs.get("start") or now.isoformat()
end = inputs.get("end") or (now + timedelta(days=7)).isoformat()
max_per_cal = int(inputs.get("max_results") or 25)

def _svc(token_json):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)

accounts = json.loads(os.environ.get("CALENDAR_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("CALENDAR_OAUTH_JSON"):
    accounts = [{"email": "default", "token_json": json.loads(os.environ["CALENDAR_OAUTH_JSON"])}]

events_by_account = {}
total = 0
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        cal_list = svc.calendarList().list().execute().get("items", [])
        per_cal = []
        for c in cal_list:
            if c.get("hidden"):
                continue
            res = svc.events().list(
                calendarId=c["id"],
                timeMin=start, timeMax=end,
                singleEvents=True, orderBy="startTime",
                maxResults=max_per_cal,
            ).execute()
            for e in res.get("items", []):
                per_cal.append({
                    "id": e.get("id"),
                    "calendar": c.get("summary"),
                    "summary": e.get("summary"),
                    "start": (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"),
                    "end": (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date"),
                    "location": e.get("location"),
                    "attendees": [{"email": x.get("email"), "responseStatus": x.get("responseStatus")}
                                  for x in (e.get("attendees") or [])[:8]],
                    "hangout": e.get("hangoutLink") or (e.get("conferenceData") or {}).get("conferenceId"),
                })
        events_by_account[a["email"]] = per_cal
        total += len(per_cal)
    except Exception as e:
        events_by_account[a["email"]] = {"error": str(e)[:200]}

print(json.dumps({"status": "ok", "result": {
    "window": {"start": start, "end": end},
    "total": total,
    "by_account": events_by_account,
}}))
"""
