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
    # Drop a trailing question mark — "add a task to X?" is still a task.
    stripped = stripped.rstrip("?!. ").strip() or stripped
    m = _NOTE_RE.match(stripped)
    if m:
        body = _clean_title(m.group("body"))
        if body:
            return await _add_note(user_id=user_id, body=body)
    m = _TASK_RE.match(stripped)
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
