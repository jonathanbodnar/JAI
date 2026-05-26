"""Aggregate week-level calendar stats: hours booked, meeting count, top people."""

KEY = "calendar.week_summary"
TITLE = "This week's calendar summary"
DESCRIPTION = (
    "Summarize the upcoming (or current) week's calendar: total meeting "
    "hours, count, busiest day, top recurring attendees. Use for 'how "
    "booked am I this week', 'meeting load summary', 'who am I seeing "
    "the most'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["calendar"]

SOURCE = r"""
import os, json
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
days = int(inputs.get("days") or 7)
now = datetime.now(timezone.utc)
start = now
end = now + timedelta(days=days)

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

total_min = 0
event_count = 0
by_day = defaultdict(float)  # day -> hours
attendee_counts = Counter()
longest = None

for a in accounts:
    try:
        svc = _svc(a["token_json"])
        cals = svc.calendarList().list().execute().get("items", [])
        for c in cals:
            if c.get("hidden"):
                continue
            events = svc.events().list(
                calendarId=c["id"],
                timeMin=start.isoformat(), timeMax=end.isoformat(),
                singleEvents=True, orderBy="startTime", maxResults=200,
            ).execute().get("items", [])
            for e in events:
                s = (e.get("start") or {}).get("dateTime")
                en = (e.get("end") or {}).get("dateTime")
                if not s or not en:
                    continue  # all-day events skipped from totals
                try:
                    s_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    e_dt = datetime.fromisoformat(en.replace("Z", "+00:00"))
                except Exception:
                    continue
                dur_min = (e_dt - s_dt).total_seconds() / 60.0
                if dur_min <= 0 or dur_min > 12 * 60:
                    continue
                total_min += dur_min
                event_count += 1
                by_day[s_dt.strftime("%a %b %d")] += dur_min / 60.0
                if not longest or dur_min > longest["minutes"]:
                    longest = {
                        "summary": e.get("summary"),
                        "minutes": dur_min,
                        "start": s,
                    }
                for at in (e.get("attendees") or []):
                    em = at.get("email")
                    if em and not em.endswith(".calendar.google.com"):
                        attendee_counts[em] += 1
    except Exception:
        continue

by_day_sorted = sorted(by_day.items(), key=lambda x: x[1], reverse=True)
top_attendees = [{"email": e, "meetings": n} for e, n in attendee_counts.most_common(8)]

print(json.dumps({"status": "ok", "result": {
    "window_days": days,
    "total_hours": round(total_min / 60.0, 1),
    "event_count": event_count,
    "by_day_hours": {d: round(h, 1) for d, h in by_day_sorted},
    "busiest_day": by_day_sorted[0][0] if by_day_sorted else None,
    "longest_event": longest,
    "top_attendees": top_attendees,
}}))
"""
