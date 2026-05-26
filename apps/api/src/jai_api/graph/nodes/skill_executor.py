"""Skill executor — built-in fast path, then match, then build & run."""

from __future__ import annotations

import re

import structlog
from langchain_core.messages import AIMessage

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

    return {
        "final_text": outcome.final_text,
        "messages": [AIMessage(content=outcome.final_text)],
        "role_used": "skill_executor",
        "skill_id": outcome.skill_id,
        "skill_name": (outcome.raw or {}).get("skill_name") if outcome.raw else None,
    }


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
