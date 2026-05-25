"""Built-in fast-path skills.

These bypass the LLM-based skill builder for obvious intents that don't need
external creds or sandboxed execution. Patterns are matched against the user's
incoming text; if any matches, we execute directly against Supabase.

Currently supported:
  - add_note   ("add a note: <body>", "note: <body>", "take a note: <body>")
  - add_task   ("remind me to <thing>", "add to my todo: <thing>", "todo: <thing>")
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


_NOTE_RE = re.compile(
    r"^\s*(?:add\s+a\s+note|take\s+a\s+note|note|jot\s+down|save\s+as\s+a?\s*note)\s*[:\-]\s*(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_TASK_RE = re.compile(
    r"^\s*(?:remind\s+me\s+to|todo|to-?do|add\s+(?:a\s+)?(?:task|todo)|put\s+on\s+my\s+(?:list|todo))\s*[:\-]?\s*(?P<title>.+)$",
    re.IGNORECASE | re.DOTALL,
)


async def try_builtin(*, user_id: str, text: str) -> BuiltinHit | None:
    m = _NOTE_RE.match(text)
    if m:
        return await _add_note(user_id=user_id, body=m.group("body").strip())
    m = _TASK_RE.match(text)
    if m:
        return await _add_task(user_id=user_id, title=m.group("title").strip())
    return None


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
