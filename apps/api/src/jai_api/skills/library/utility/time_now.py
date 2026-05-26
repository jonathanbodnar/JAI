"""Current time in any timezone, plus useful day-of-week metadata."""

KEY = "utility.time_now"
TITLE = "Current time"
DESCRIPTION = (
    "Return the current time in any timezone (defaults to UTC) plus "
    "day-of-week, day-of-year, week number. Use for 'what time is it', "
    "'what's the date in tokyo', 'what day of the week is it'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["utility"]

SOURCE = r"""
import os, json
from datetime import datetime, timezone

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
tz_name = (inputs.get("timezone") or "UTC").strip()

try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_name)
except Exception:
    tz = timezone.utc
    tz_name = "UTC"

now = datetime.now(tz)
print(json.dumps({"status": "ok", "result": {
    "timezone": tz_name,
    "iso": now.isoformat(),
    "date": now.date().isoformat(),
    "time": now.strftime("%H:%M:%S"),
    "day_of_week": now.strftime("%A"),
    "day_of_year": now.timetuple().tm_yday,
    "week_number": int(now.strftime("%V")),
    "unix": int(now.timestamp()),
}}))
"""
