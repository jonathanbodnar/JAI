"""Find open time slots across every connected calendar."""

KEY = "calendar.find_free_time"
TITLE = "Find free time slots"
DESCRIPTION = (
    "Find open time slots across every connected Google Calendar. Inputs: "
    "duration_minutes (default 30), days_ahead (default 5), business_hours "
    "(default 9-18 local), tz (default UTC). Use for 'when am I free this "
    "week', 'find an hour tomorrow', 'open slots for a call'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["calendar"]

SOURCE = r"""
import os, json
from datetime import datetime, timedelta, timezone, time as dtime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
duration_minutes = int(inputs.get("duration_minutes") or 30)
days_ahead = int(inputs.get("days_ahead") or 5)
biz_start = int(inputs.get("business_start_hour") or 9)
biz_end = int(inputs.get("business_end_hour") or 18)
tz_name = inputs.get("tz") or "UTC"

try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_name)
except Exception:
    tz = timezone.utc

now_local = datetime.now(tz)
start_window = now_local.replace(minute=0, second=0, microsecond=0)
end_window = start_window + timedelta(days=days_ahead)

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

# Use Calendar freeBusy to get aggregated busy blocks across all
# calendars on each account.
busy_blocks = []
for a in accounts:
    try:
        svc = _svc(a["token_json"])
        cal_ids = [c["id"] for c in svc.calendarList().list().execute().get("items", [])
                   if not c.get("hidden") and c.get("accessRole") in ("owner", "writer", "reader")]
        fb = svc.freebusy().query(body={
            "timeMin": start_window.astimezone(timezone.utc).isoformat(),
            "timeMax": end_window.astimezone(timezone.utc).isoformat(),
            "items": [{"id": cid} for cid in cal_ids[:50]],  # API caps at 50
        }).execute()
        for cid, slot in (fb.get("calendars") or {}).items():
            for b in slot.get("busy", []):
                busy_blocks.append((b["start"], b["end"]))
    except Exception:
        continue

# Merge overlapping busy blocks.
def _parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

intervals = sorted([(_parse(s), _parse(e)) for s, e in busy_blocks], key=lambda x: x[0])
merged = []
for s, e in intervals:
    if merged and s <= merged[-1][1]:
        merged[-1] = (merged[-1][0], max(merged[-1][1], e))
    else:
        merged.append((s, e))

# Generate candidate slots in business hours and exclude any that
# overlap a merged busy block.
free = []
needed = timedelta(minutes=duration_minutes)
cursor_day = start_window.date()
end_day = end_window.date()
while cursor_day <= end_day:
    day_start = datetime.combine(cursor_day, dtime(biz_start, 0), tzinfo=tz)
    day_end = datetime.combine(cursor_day, dtime(biz_end, 0), tzinfo=tz)
    if day_start < now_local:
        day_start = now_local + timedelta(minutes=15)
    cursor = day_start
    while cursor + needed <= day_end:
        slot_end = cursor + needed
        cs, ce = cursor.astimezone(timezone.utc), slot_end.astimezone(timezone.utc)
        conflict = any(not (ce <= bs or cs >= be) for bs, be in merged)
        if not conflict:
            free.append({"start": cursor.isoformat(), "end": slot_end.isoformat()})
        cursor += timedelta(minutes=30)
    cursor_day += timedelta(days=1)

print(json.dumps({"status": "ok", "result": {
    "duration_minutes": duration_minutes,
    "tz": tz_name,
    "window": {"start": start_window.isoformat(), "end": end_window.isoformat()},
    "free_slots": free[:30],
    "free_slot_count": len(free),
}}))
"""
