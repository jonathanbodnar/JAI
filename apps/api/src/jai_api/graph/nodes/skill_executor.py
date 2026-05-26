"""Skill executor — built-in fast path, then match, then build & run.

After a skill produces structured data we hand it to Kimi (RESPOND role)
to write the actual reply. Without that step the user just sees a raw
Python dict dump and has to mentally parse it, which defeats the whole
point of an assistant.
"""

from __future__ import annotations

import json
import re

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
            )
        except Exception as e:
            log.warning("skill_executor.synthesize_failed", error=str(e))
            # Fall through to the runner's raw preview rather than dropping
            # the result entirely.

    return {
        "final_text": final_text,
        "messages": [AIMessage(content=final_text)],
        "role_used": "skill_executor",
        "skill_id": outcome.skill_id,
        "skill_name": skill_name,
        "skill_output": result if isinstance(result, dict) else {"value": result},
    }


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


async def _synthesize_result(
    *,
    user_ask: str,
    skill_name: str | None,
    result,
    first_run: bool,
) -> str:
    """Have Kimi (RESPOND role) rewrite the skill's structured data."""
    trimmed = _trim_for_synthesis(result)
    try:
        payload = json.dumps(trimmed, default=str, indent=2)
    except Exception:
        payload = str(trimmed)
    # Cap at 12k chars after trimming — Kimi has room for ~32k context
    # but we want to keep the answer focused and fast.
    if len(payload) > 12000:
        payload = payload[:12000] + "\n…(truncated)"

    skill_hint = f" (via skill: {skill_name})" if skill_name else ""
    human_content = (
        f"User asked: {user_ask}\n\n"
        f"The skill ran successfully{skill_hint}. Here is what it returned:\n\n"
        f"```json\n{payload}\n```\n\n"
        "Write the user-facing answer now."
    )

    llm = chat_for(Role.RESPOND, temperature=0.4, streaming=False)
    res = await llm.ainvoke([
        SystemMessage(content=_SYNTHESIZE_SYSTEM),
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
