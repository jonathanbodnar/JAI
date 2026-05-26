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
- For lists of items (emails, tasks, events): show the top 5-10 as a
  short bulleted list, one line each, most important first. Then a
  one-sentence overall takeaway if there's something worth flagging.
- For single records: lead with the headline, follow with 1-3 useful
  details.
- For metrics/counts: state the number plainly, then any context.
- Mention the source account/project once when it's relevant (e.g. "from
  your Lunarpay inbox"); don't repeat it on every line.
- Skip junk: unsubscribe links, full message IDs, raw thread IDs,
  internal tokens.
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
    try:
        payload = json.dumps(result, default=str, indent=2)
    except Exception:
        payload = str(result)
    # Trim aggressively — most JSON results have repetitive metadata that
    # eats context for nothing.
    if len(payload) > 6000:
        payload = payload[:6000] + "\n…(truncated)"

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
