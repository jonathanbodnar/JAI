"""Built-in fast-path skills.

These bypass the LLM-based skill builder for obvious intents that don't need
external creds or sandboxed execution. Patterns are matched against the user's
incoming text; if any matches, we execute directly against Supabase.

Currently supported:
  - add_note       ("add a note: <body>", "note: <body>", etc.)
  - add_task       ("remind me to <thing>", "add to my todo: <thing>", etc.)
  - morning_brief  ("good morning", "what's on today?", etc.)
  - schedule       ("remind me daily about X", "every Monday check X", etc.)

Polite/conversational lead-ins ("can you", "could you", "please", "hey jai",
etc.) are stripped before matching so the user doesn't have to talk like a
CLI parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from ..db import supabase_admin

log = structlog.get_logger()


@dataclass
class BuiltinHit:
    kind: str
    response: str
    record_id: str | None


# Strip a polite preamble so "Can you add a task to X" still hits add_task.
_MORNING_RE = re.compile(
    r"^\s*(?:"
    r"good\s*morning|morning|gm|good\s*day|"
    r"(?:hey|hi|hello|sup)(?:\s+jai)?|"
    r"what['\u2019]?s?\s+up|"
    # "what's on today/this week/my plate/my agenda"
    r"what(?:['\u2019]s|\s+is)\s+(?:on\s+)?(?:my\s+)?(?:today|agenda|schedule|calendar|todo|to-?do|plate)|"
    r"what\s+do\s+i\s+have\s+(?:today|on|planned)|"
    r"(?:show|give|tell)\s+me\s+my\s+(?:tasks?|todos?|agenda|schedule|day|list)|"
    r"what(?:['\u2019]s|\s+should|\s+do)\s+i\s+(?:need\s+to\s+)?(?:do|focus\s+on)\s+today|"
    r"(?:any|what)\s+tasks?\s+(?:for\s+)?today"
    r")[\s?!.]*$",
    re.IGNORECASE,
)

_LEAD_RE = re.compile(
    r"^\s*(?:"
    r"hey\s+(?:jai|j[ae])\s*[,\-:!.]*\s*|"
    r"(?:please\s+)?(?:can|could|would|will|do)\s+you\s+(?:please\s+)?|"
    r"please\s+|pls\s+|"
    r"i\s+(?:need|want|would\s+like)\s+(?:you\s+)?to\s+|"
    r"go\s+ahead\s+and\s+|"
    r"(?:would|can)\s+you\s+mind(?:\s+if\s+i\s+ask\s+you)?\s+to\s+"
    r")",
    re.IGNORECASE,
)

# After stripping politeness, match if the text begins with any of these.
# We accept "to" or "that" as a soft connector ("add a task to check on X").
_NOTE_RE = re.compile(
    r"^\s*(?:add\s+a\s+note|take\s+a\s+note|note|jot\s+down|save\s+as\s+a?\s*note|"
    r"make\s+a\s+note(?:\s+of)?|write\s+(?:that\s+)?down|capture\s+(?:this|that))"
    r"(?:\s+(?:that|about|on|of|for))?\s*[:\-,]?\s*(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_TASK_RE = re.compile(
    r"^\s*(?:remind\s+me\s+to|todo|to-?do|add\s+(?:a\s+)?(?:task|todo|to-?do)|"
    r"put\s+on\s+my\s+(?:list|todo)|"
    r"create\s+(?:a\s+)?(?:task|todo)|new\s+(?:task|todo))"
    r"(?:\s+(?:to|that|about|for))?\s*[:\-,]?\s*(?P<title>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Detect explicit "schedule a recurring action" intent.
# Groups: freq_word (daily/weekly/etc.), dow (monday/etc.), hour (8am/etc.), body (what to do)
_SCHEDULE_RE = re.compile(
    r"^\s*(?:"
    # "remind me daily/weekly/every morning/every Monday about/to X"
    r"remind\s+me\s+(?P<freq1>(?:every\s+)?(?:day|daily|morning|night|week|weekly|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday))\s+(?:about|to|with|when|at\s+\S+\s+(?:about|to))?\s*(?P<body1>.+)|"
    # "every morning/day/Monday do/check/send/show/run X"
    r"every\s+(?P<freq2>day|morning|night|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday)\s+(?:(?:at\s+\S+)\s+)?(?:please\s+)?(?:do|check|send|show|run|pull|get|summarize|fetch|remind|report)\s+(?P<body2>.+)|"
    # "schedule a daily/weekly X"
    r"schedule\s+(?:a\s+)?(?P<freq3>daily|weekly|hourly|monthly|weekday)\s+(?P<body3>.+)|"
    # "set up a daily reminder/check/summary for X"
    r"set\s+(?:up\s+)?(?:a\s+)?(?P<freq4>daily|weekly|hourly|monthly|weekday)\s+(?:reminder|check|summary|report|task)\s+(?:for|about|on)?\s*(?P<body4>.+)"
    r")\s*$",
    re.IGNORECASE | re.DOTALL,
)

_FREQ_MAP = {
    "day": "daily", "daily": "daily",
    "morning": "daily", "night": "daily",
    "week": "weekly", "weekly": "weekly",
    "weekday": "weekdays", "weekdays": "weekdays",
    "hourly": "hourly", "monthly": "monthly",
    "monday": "weekly", "tuesday": "weekly", "wednesday": "weekly",
    "thursday": "weekly", "friday": "weekly",
    "saturday": "weekly", "sunday": "weekly",
}
_DOW_MAP = {
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}
_HOUR_MAP = {
    "morning": 13, "night": 2, "day": 13,  # UTC: 8am CST ≈ 13 UTC
    "weekly": 13, "daily": 13, "weekday": 13, "weekdays": 13,
    "hourly": None, "monthly": 13,
    "monday": 13, "tuesday": 13, "wednesday": 13,
    "thursday": 13, "friday": 13, "saturday": 13, "sunday": 13,
}


def _strip_lead(text: str) -> str:
    """Peel one polite preamble (or two — 'please can you...')."""
    prev = None
    cur = text.strip()
    for _ in range(3):  # at most "please can you please" type chains
        prev = cur
        cur = _LEAD_RE.sub("", cur, count=1).strip()
        if cur == prev:
            break
    return cur


async def try_builtin(*, user_id: str, text: str) -> BuiltinHit | None:
    stripped = _strip_lead(text)
    stripped_clean = stripped.rstrip("?!. ").strip() or stripped

    # Morning briefing — "good morning", "what's on today?", etc.
    if _MORNING_RE.match(text.strip()):
        return await _morning_briefing(user_id=user_id, text=text.strip())

    # Scheduling intent — "remind me daily about X", "every Monday check X", etc.
    m = _SCHEDULE_RE.match(stripped_clean)
    if m:
        return await _create_schedule(user_id=user_id, match=m)

    m = _NOTE_RE.match(stripped_clean)
    if m:
        body = _clean_title(m.group("body"))
        if body:
            return await _add_note(user_id=user_id, body=body)
    m = _TASK_RE.match(stripped_clean)
    if m:
        title = _clean_title(m.group("title"))
        if title:
            return await _add_task(user_id=user_id, title=title)
    return None


def _clean_title(s: str) -> str:
    s = s.strip().rstrip("?!.,;: ").strip()
    # Drop a leading "to " left over after the connector was consumed.
    if s.lower().startswith("to "):
        s = s[3:].strip()
    return s


async def _create_schedule(*, user_id: str, match: re.Match) -> BuiltinHit:
    """Parse a scheduling intent and write a row to scheduled_actions."""
    # Extract freq word and body from whichever group matched
    freq_word = (
        match.group("freq1") or match.group("freq2") or
        match.group("freq3") or match.group("freq4") or "daily"
    ).lower().strip()
    body = (
        match.group("body1") or match.group("body2") or
        match.group("body3") or match.group("body4") or ""
    ).strip()

    freq_key = freq_word.split()[-1]  # "every morning" → "morning"
    frequency = _FREQ_MAP.get(freq_key, "daily")
    day_of_week = _DOW_MAP.get(freq_key)
    hour_utc = _HOUR_MAP.get(freq_key, 13)

    description = _clean_title(body) or f"Scheduled {frequency} action"

    from datetime import datetime, timedelta, timezone
    sb = supabase_admin()

    # Compute next_run_at
    now = datetime.now(timezone.utc)
    if hour_utc is None:
        next_run = now + timedelta(hours=1)
    else:
        candidate = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        next_run = candidate

    res = sb.table("scheduled_actions").insert({
        "user_id": user_id,
        "description": description,
        "frequency": frequency,
        "hour_utc": hour_utc or 13,
        "day_of_week": day_of_week,
        "builtin_name": "task_summary" if "task" in description.lower() else None,
        "skill_inputs": {},
        "enabled": True,
        "next_run_at": next_run.isoformat(),
    }).execute()
    row = res.data[0] if res.data else {}

    freq_label = {"daily": "every day", "weekly": f"every {freq_key.capitalize()}",
                  "weekdays": "every weekday", "hourly": "every hour",
                  "monthly": "every month"}.get(frequency, frequency)

    log.info("builtin.schedule.created", id=row.get("id"), description=description,
             frequency=frequency, user=user_id)

    return BuiltinHit(
        kind="schedule_created",
        response=(
            f"Done. I've set up a **{freq_label}** automation: \"{description}\".\n\n"
            f"It'll run automatically in the background. You can manage all your automations "
            f"under Settings → Automations."
        ),
        record_id=row.get("id"),
    )


async def _morning_briefing(*, user_id: str, text: str) -> BuiltinHit:
    """Fetch open tasks + overnight scheduled results for a morning rundown."""
    from datetime import datetime, timedelta, timezone
    sb = supabase_admin()

    # Open tasks (across all lists)
    tasks_res = (
        sb.table("tasks")
        .select("title, due, notes")
        .eq("user_id", user_id)
        .neq("status", "completed")
        .order("due", desc=False, nullsfirst=False)
        .limit(20)
        .execute()
    )
    tasks = tasks_res.data or []

    # Overnight scheduled action results (last 12 hours)
    since = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    sched_res = (
        sb.table("scheduled_actions")
        .select("description, last_result, last_status, last_run_at")
        .eq("user_id", user_id)
        .eq("enabled", True)
        .eq("last_status", "ok")
        .gte("last_run_at", since)
        .execute()
    )
    overnight = sched_res.data or []

    now = datetime.now(timezone.utc)
    greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 18 else "Hey")

    lines: list[str] = []

    # --- Overnight automation results ---
    if overnight:
        lines.append("**Overnight automations**")
        for a in overnight:
            lines.append(f"- **{a['description']}** ran ✓")
        lines.append("")

    # --- Task rundown ---
    if not tasks:
        lines.append("Your task list is clear — nothing open right now.")
    else:
        overdue, due_today, upcoming = [], [], []
        today_str = now.date().isoformat()
        for t in tasks:
            due = (t.get("due") or "")[:10]
            if due and due < today_str:
                overdue.append(t)
            elif due == today_str:
                due_today.append(t)
            else:
                upcoming.append(t)

        total = len(tasks)
        lines.append(f"**Tasks ({total} open)**")
        if overdue:
            lines.append(f"*Overdue ({len(overdue)})*")
            for t in overdue:
                lines.append(f"- {t['title']}")
        if due_today:
            lines.append(f"*Due today ({len(due_today)})*")
            for t in due_today:
                lines.append(f"- {t['title']}")
        if upcoming:
            lines.append(f"*Upcoming ({len(upcoming)})*")
            for t in upcoming[:8]:
                label = t["title"]
                if t.get("due"):
                    label += f" — {t['due'][:10]}"
                lines.append(f"- {label}")

    response = f"{greeting}. Here's your rundown:\n\n" + "\n".join(lines)
    return BuiltinHit(kind="morning_briefing", response=response, record_id=None)


async def _add_note(*, user_id: str, body: str) -> BuiltinHit:
    sb = supabase_admin()
    title, body_text = _split_title(body)
    res = (
        sb.table("notes")
        .insert(
            {
                "user_id": user_id,
                "title": title,
                "body": body_text,
                "source": "voice",
            }
        )
        .execute()
    )
    nid = res.data[0]["id"] if res.data else None
    return BuiltinHit(
        kind="add_note",
        response=f"Got it. Saved as a note.{' Title: “' + title + '”.' if title else ''}",
        record_id=nid,
    )


async def _add_task(*, user_id: str, title: str) -> BuiltinHit:
    sb = supabase_admin()
    # Ensure the user has at least one task list (the trigger doesn't create one).
    lists = (
        sb.table("task_lists")
        .select("id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if lists.data:
        list_id = lists.data[0]["id"]
    else:
        ins = (
            sb.table("task_lists")
            .insert({"user_id": user_id, "title": "My Tasks"})
            .execute()
        )
        list_id = ins.data[0]["id"]

    res = (
        sb.table("tasks")
        .insert(
            {
                "user_id": user_id,
                "list_id": list_id,
                "title": title,
                "source": "voice",
            }
        )
        .execute()
    )
    tid = res.data[0]["id"] if res.data else None
    return BuiltinHit(
        kind="add_task",
        response=f"Added to your tasks: “{title}”.",
        record_id=tid,
    )


def _split_title(body: str) -> tuple[str | None, str]:
    """Heuristic: first line becomes title if it's short and there's a newline."""
    body = body.strip()
    if "\n" in body:
        head, rest = body.split("\n", 1)
        head = head.strip()
        rest = rest.strip()
        if 0 < len(head) <= 80 and rest:
            return head, rest
    if len(body) <= 80:
        return body, ""
    return None, body
