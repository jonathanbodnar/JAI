"""Skill executor — built-in fast path, then match, then build & run.

After a skill produces structured data we hand it to Kimi (RESPOND role)
to write the actual reply. Without that step the user just sees a raw
Python dict dump and has to mentally parse it, which defeats the whole
point of an assistant.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ...models.registry import Role, chat_for
from ...skills import registry
from ...skills.runner import run_intent
from ..state import JaiState

log = structlog.get_logger()

_CRED_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]{1,63})\s*=\s*(.+?)\s*$", re.MULTILINE)


async def skill_executor(state: JaiState) -> dict:
    user_id = state["user_id"]
    text = (state.get("input_text") or "").strip()
    conversation_id = state.get("conversation_id")

    # 0. Credential capture fast-path. If the message is mostly `KEY=value`
    #    lines, treat it as the user filling in credentials we asked for.
    creds = _parse_credentials(text)
    if creds:
        for k, v in creds.items():
            await registry.set_credential(user_id=user_id, key=k, value=v)
        msg = (
            f"Saved {len(creds)} credential{'s' if len(creds) > 1 else ''}. "
            "Want me to try that action again?"
        )
        return {
            "final_text": msg,
            "messages": [AIMessage(content=msg)],
            "role_used": "skill_executor",
        }

    try:
        outcome = await run_intent(
            user_id=user_id, conversation_id=conversation_id, intent=text
        )
    except Exception as e:
        log.exception("skill_executor.run_intent_failed", error=str(e))
        msg = (
            "I tried to run that as a skill but something failed before it "
            f"could complete: {str(e)[:240]}. "
            "Want me to try a different approach, or check the connection?"
        )
        return {
            "final_text": msg,
            "messages": [AIMessage(content=msg)],
            "role_used": "skill_executor",
        }

    final_text = outcome.final_text
    raw = outcome.raw or {}
    result = raw.get("result")
    skill_name = raw.get("skill_name")

    # Build a canvas payload BEFORE synthesizing the chat reply. If we
    # know the artifact will live on the canvas, we tell the LLM to keep
    # the chat bubble to a tight 1-2 line headline instead of trying to
    # squeeze the whole draft into the message.
    canvas = _build_canvas(result, skill_name=skill_name)

    # If the skill returned structured data, hand it to Kimi so the user
    # gets a real answer instead of a dict dump. Errors / credential asks
    # keep the runner's already-formatted text.
    if raw.get("status") == "ok" and _is_structured(result):
        try:
            final_text = await _synthesize_result(
                user_ask=text,
                skill_name=skill_name,
                result=result,
                first_run=bool(raw.get("first_run")),
                canvas=canvas,
            )
        except Exception as e:
            log.warning("skill_executor.synthesize_failed", error=str(e))
            # Fall through to the runner's raw preview rather than dropping
            # the result entirely.

    out: dict = {
        "final_text": final_text,
        "messages": [AIMessage(content=final_text)],
        "role_used": "skill_executor",
        "skill_id": outcome.skill_id,
        "skill_name": skill_name,
        "skill_output": result if isinstance(result, dict) else {"value": result},
        "skill_output_at": datetime.now(timezone.utc).isoformat(),
        "skill_output_summary": final_text,
    }
    if canvas:
        out["canvas"] = canvas
    return out


# --- Canvas extraction ------------------------------------------------------
#
# Skills that produce long-form artifacts (drafts, docs, plans, code) flag
# them by returning a `kind` field in their result. We turn that into a
# canvas payload here so the chat client can render the full content in a
# side panel — like ChatGPT Canvas — without burning chat real-estate on a
# 40-line email body.

_CANVAS_KINDS = {"email_draft", "document", "code", "plan", "list"}


def _build_canvas(result, *, skill_name: str | None) -> dict | None:
    """If the skill emitted a canvas-worthy artifact, return a normalized
    payload. Otherwise return None.

    We bias toward declaring less rather than more: only known `kind`
    values get a canvas, and we always require enough content to be
    worth opening a side panel (>= 240 chars or a multi-field record).
    """
    if not isinstance(result, dict):
        return None
    kind = (result.get("kind") or "").strip().lower()
    if kind not in _CANVAS_KINDS:
        return None

    if kind == "email_draft":
        body = (result.get("body") or "").strip()
        subject = (result.get("subject") or "").strip()
        if not body and not subject:
            return None
        return {
            "kind": "email_draft",
            "title": f"Email to {result.get('to') or 'recipient'}",
            "content": body,
            "language": "markdown",
            "metadata": {
                "to": result.get("to"),
                "from": result.get("account"),
                "subject": subject,
                "tone": result.get("tone"),
                "draft_id": result.get("draft_id"),
                "message_id": result.get("message_id"),
                "saved_to": result.get("saved_to"),
            },
            "actions": [
                {"id": "send", "label": "Send", "prompt": "send the draft"},
                {
                    "id": "refine",
                    "label": "Refine",
                    "prompt": "make these edits to the draft: ",
                    "is_template": True,
                },
            ],
            "source_skill": skill_name,
        }

    if kind == "document":
        content = (result.get("content") or result.get("body") or "").strip()
        if len(content) < 80:
            return None
        return {
            "kind": "document",
            "title": (result.get("title") or "Document").strip() or "Document",
            "content": content,
            "language": (result.get("language") or "markdown"),
            "metadata": result.get("metadata") or {},
            "actions": [],
            "source_skill": skill_name,
        }

    if kind == "code":
        content = (result.get("content") or result.get("source") or "").strip()
        if len(content) < 40:
            return None
        return {
            "kind": "code",
            "title": (result.get("title") or "Code").strip() or "Code",
            "content": content,
            "language": (result.get("language") or "python"),
            "metadata": result.get("metadata") or {},
            "actions": [],
            "source_skill": skill_name,
        }

    if kind == "plan":
        content = (result.get("content") or result.get("body") or "").strip()
        if len(content) < 120:
            return None
        return {
            "kind": "plan",
            "title": (result.get("title") or "Plan").strip() or "Plan",
            "content": content,
            "language": "markdown",
            "metadata": result.get("metadata") or {},
            "actions": [],
            "source_skill": skill_name,
        }

    if kind == "list":
        items = result.get("items") or []
        if not isinstance(items, list) or len(items) < 5:
            return None
        # Render as a markdown bullet list so the canvas has a single
        # source of truth.
        lines = []
        for it in items:
            if isinstance(it, str):
                lines.append(f"- {it}")
            elif isinstance(it, dict):
                head = it.get("title") or it.get("name") or it.get("text") or ""
                body = it.get("description") or it.get("body") or ""
                lines.append(f"- **{head}**" + (f" — {body}" if body else ""))
        content = "\n".join(lines).strip()
        if not content:
            return None
        return {
            "kind": "list",
            "title": (result.get("title") or "List").strip() or "List",
            "content": content,
            "language": "markdown",
            "metadata": result.get("metadata") or {},
            "actions": [],
            "source_skill": skill_name,
        }

    return None


def _trim_for_synthesis(value, depth: int = 0):
    """Shrink long string fields recursively so Kimi sees the structure
    without burning tokens on full email bodies, repeated metadata, etc.

    The key invariant we protect: every dict KEY is preserved (so the
    LLM can see all accounts/projects/groups exist), only field VALUES
    get trimmed.
    """
    if depth > 6:
        return "…"
    if isinstance(value, dict):
        return {k: _trim_for_synthesis(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        # For large lists, keep the first ~10 items but show the count.
        if len(value) > 12:
            head = [_trim_for_synthesis(v, depth + 1) for v in value[:10]]
            head.append(f"…({len(value) - 10} more)")
            return head
        return [_trim_for_synthesis(v, depth + 1) for v in value]
    if isinstance(value, str):
        # Snippets/bodies routinely arrive at 500-2000 chars each. The
        # LLM doesn't need that much to summarize.
        if len(value) > 240:
            return value[:240].rstrip() + "…"
    return value


def _is_structured(result) -> bool:
    """Worth synthesizing through an LLM?

    Skip when the skill returned nothing or just a short status string —
    those don't benefit from rephrasing and we'd just be burning a Kimi
    call to say "done."
    """
    if result is None:
        return False
    if isinstance(result, (dict, list)):
        return True
    if isinstance(result, str) and len(result) > 80:
        return True
    return False


_SYNTHESIZE_SYSTEM = """You are JAI talking to the user in chat.

The user asked a question, and a backend skill just ran and returned
some data. Your job is to turn that data into a clear, useful, scannable
answer in your own voice. NOT a dict dump, NOT a JSON blob, NOT a
preamble like "Here is your data:".

Rules:
- Be specific. Use the actual values from the data (names, numbers,
  dates, subjects). Don't summarize the *structure*, summarize the
  *content*.
- For lists of items (emails, tasks, events): show the top 3-6 per
  group as a short bulleted list, one line each, most important first.
  Add a one-sentence takeaway if there's something worth flagging.
- For single records: lead with the headline, follow with 1-3 useful
  details.
- For metrics/counts: state the number plainly, then any context.
- CRITICAL: When the data is grouped (`by_account`, `by_calendar`,
  `by_project`, etc.) you MUST include EVERY key in your output, even
  if only a one-line summary per group. Dropping an entire account
  because the response is getting long is the worst failure mode —
  trim the per-item details first, never skip a group. Use H3 headers
  or short section labels per group so the user can scan.
- If a group has an `error` field instead of items, mention the
  failure: e.g. "Lunarpay — couldn't fetch (token error)" — never
  silently omit it.
- Skip junk: unsubscribe links, full message IDs, raw thread IDs,
  internal tokens, mass marketing emails (Express, Printful,
  newsletters) unless they're the only thing in the list.
- No preamble, no "Done!", no "I found...". Just the answer.

If the data is empty or the user's question can't be answered from it,
say so in one short sentence and suggest the next thing to try.
"""


_SYNTHESIZE_CANVAS_SYSTEM = """You are JAI replying in chat. A skill just
produced a long-form artifact (email draft, document, code, plan) that
the UI is rendering in a side **canvas** the user can already see and
edit.

Your reply lives in the chat bubble next to it. Keep it tight:
- 1-2 sentences MAX. Headline-only.
- Lead with what you did + key context the canvas doesn't already show
  on the surface (e.g. recipient + subject for emails, language for code).
- Don't repeat the full body. The canvas IS the body.
- End with a soft pointer to the canvas actions ("Hit Send or tell me
  what to change.") only when there are user-facing actions.
- No "Here's...", no preamble, no markdown headings.

If the skill explicitly returned an error or the artifact is empty,
say that plainly instead.
"""


async def _synthesize_result(
    *,
    user_ask: str,
    skill_name: str | None,
    result,
    first_run: bool,
    canvas: dict | None = None,
) -> str:
    """Have Kimi (RESPOND role) rewrite the skill's structured data.

    When the skill emitted a canvas-worthy artifact, we switch to a
    short headline-style reply because the full content lives in the
    canvas panel next to the bubble.
    """
    trimmed = _trim_for_synthesis(result)
    try:
        payload = json.dumps(trimmed, default=str, indent=2)
    except Exception:
        payload = str(trimmed)
    if len(payload) > 12000:
        payload = payload[:12000] + "\n…(truncated)"

    skill_hint = f" (via skill: {skill_name})" if skill_name else ""

    if canvas:
        system = _SYNTHESIZE_CANVAS_SYSTEM
        canvas_meta = {
            "kind": canvas.get("kind"),
            "title": canvas.get("title"),
            "metadata": canvas.get("metadata"),
            "actions": [a.get("label") for a in (canvas.get("actions") or [])],
        }
        human_content = (
            f"User asked: {user_ask}\n\n"
            f"The skill ran successfully{skill_hint} and produced a canvas:\n\n"
            f"```json\n{json.dumps(canvas_meta, default=str, indent=2)}\n```\n\n"
            "Raw skill result (FYI only — DO NOT paste it into the reply):\n\n"
            f"```json\n{payload}\n```\n\n"
            "Write the chat-bubble reply now. Remember: 1-2 sentences, "
            "the canvas already shows the body."
        )
    else:
        system = _SYNTHESIZE_SYSTEM
        human_content = (
            f"User asked: {user_ask}\n\n"
            f"The skill ran successfully{skill_hint}. Here is what it returned:\n\n"
            f"```json\n{payload}\n```\n\n"
            "Write the user-facing answer now."
        )

    llm = chat_for(Role.RESPOND, temperature=0.4, streaming=False)
    res = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=human_content),
    ])
    text = res.content if isinstance(res.content, str) else str(res.content)
    text = (text or "").strip()
    if not text:
        return "Got the data back but couldn't summarize it. Want me to show the raw result?"
    if first_run:
        text += "\n\n*(saved as a reusable skill)*"
    return text


def _parse_credentials(text: str) -> dict[str, str]:
    """Detect lines that look like KEY=value. Only treat as creds if at least
    one match and the message is dominated by them (so we don't misfire on
    natural language)."""
    matches = _CRED_LINE.findall(text)
    if not matches:
        return {}
    # Heuristic: total cred-bytes must cover >= 60% of the non-whitespace text.
    raw_total = sum(len(k) + 1 + len(v) for k, v in matches)
    if raw_total < 0.6 * len(text.replace(" ", "").replace("\n", "")):
        return {}
    return {k: v for k, v in matches}
