"""Built-in fast-path skills.

These bypass the LLM-based skill builder for obvious intents that don't need
external creds or sandboxed execution. Patterns are matched against the user's
incoming text; if any matches, we execute directly against Supabase.

Currently supported:
  - add_note   ("add a note: <body>", "note: <body>", "take a note: <body>")
  - add_task   ("remind me to <thing>", "add to my todo: <thing>", "todo: <thing>")

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


async def _morning_briefing(*, user_id: str, text: str) -> BuiltinHit:
    """Fetch open tasks and return a formatted morning rundown."""
    from datetime import datetime, timezone
    sb = supabase_admin()

    # Get open tasks (across all lists, not done, not deleted)
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

    now = datetime.now(timezone.utc)
    greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 18 else "Hey")

    if not tasks:
        response = (
            f"{greeting}. Your task list is clear — nothing open right now. "
            "Want to add something?"
        )
    else:
        lines = []
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

        if overdue:
            lines.append(f"**Overdue ({len(overdue)})**")
            for t in overdue:
                lines.append(f"- {t['title']}")
        if due_today:
            lines.append(f"**Due today ({len(due_today)})**")
            for t in due_today:
                lines.append(f"- {t['title']}")
        if upcoming:
            lines.append(f"**Upcoming ({len(upcoming)})**")
            for t in upcoming[:10]:
                label = t["title"]
                if t.get("due"):
                    label += f" — {t['due'][:10]}"
                lines.append(f"- {label}")

        total = len(tasks)
        response = (
            f"{greeting}. Here's your task rundown ({total} open):\n\n"
            + "\n".join(lines)
        )

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
