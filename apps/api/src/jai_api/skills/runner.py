"""Top-level skill orchestration.

Flow per turn:
  1. Try built-in fast-path (add_note / add_task / …). If hit, respond.
  2. Try matcher: if cos sim > threshold, fetch creds, run sandbox, respond.
  3. Else build: call Skill Builder.
      a. If it returns need_credentials, respond with an "I need: X" ask.
      b. Otherwise save the new skill, fetch creds, run sandbox, respond.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from .. import audit
from . import builder, matcher, registry
from .builtin import try_builtin
from .sandbox import SandboxClient

log = structlog.get_logger()


@dataclass
class SkillOutcome:
    final_text: str
    skill_id: str | None = None
    record_id: str | None = None
    needs_credentials: list[str] | None = None
    raw: dict | None = None


async def run_intent(
    *,
    user_id: str,
    conversation_id: str | None,
    intent: str,
) -> SkillOutcome:
    # 1. Built-in fast path.
    hit = await try_builtin(user_id=user_id, text=intent)
    if hit:
        await audit.write(
            user_id=user_id,
            actor="agent:builtin",
            action=hit.kind,
            target=hit.record_id,
            payload={"intent": intent[:200]},
            ok=True,
        )
        return SkillOutcome(final_text=hit.response, record_id=hit.record_id)

    # 2. Match.
    matches = await matcher.match(user_id=user_id, intent=intent)
    if matches:
        sk = matches[0]
        log.info("skill.match.hit", id=sk["id"], sim=sk.get("similarity"))
        return await _execute(
            user_id=user_id,
            conversation_id=conversation_id,
            skill=sk,
            inputs={"intent": intent},
        )

    # 3. Build.
    creds_have = await _user_credential_keys(user_id)
    draft = await builder.build_skill(
        goal=intent,
        available_credentials=creds_have,
    )
    if draft.need_credentials:
        ask = _credential_ask(draft.need_credentials, draft.explanation)
        return SkillOutcome(final_text=ask, needs_credentials=draft.need_credentials)

    if not (draft.language and draft.source and draft.title and draft.description):
        return SkillOutcome(
            final_text="I couldn't build a skill for that — could you rephrase what you want me to do?"
        )

    saved = await registry.save_skill(
        user_id=user_id,
        title=draft.title,
        description=draft.description,
        language=draft.language,
        source=draft.source,
        required_credentials=draft.need_credentials,  # likely empty here
        required_tools=draft.required_tools,
    )
    return await _execute(
        user_id=user_id,
        conversation_id=conversation_id,
        skill=saved,
        inputs={"intent": intent},
        first_run=True,
    )


async def _execute(
    *,
    user_id: str,
    conversation_id: str | None,
    skill: dict,
    inputs: dict,
    first_run: bool = False,
) -> SkillOutcome:
    required = skill.get("required_credentials") or []
    missing = await registry.missing_credentials(user_id=user_id, required=required)
    if missing:
        return SkillOutcome(
            final_text=_credential_ask(missing),
            skill_id=skill["id"],
            needs_credentials=missing,
        )

    creds = await registry.get_credentials(user_id=user_id, keys=required)
    sandbox = SandboxClient()
    try:
        raw = await sandbox.run(
            user_id=user_id,
            skill_id=skill["id"],
            language=skill["language"],
            source=skill["source"],
            env=creds,
        )
    finally:
        await sandbox.close()

    status = raw.get("status", "error")
    await registry.record_run(
        user_id=user_id,
        skill_id=skill["id"],
        conversation_id=conversation_id,
        inputs=inputs,
        output=raw.get("result"),
        status="ok" if status == "ok" else "error",
        stdout=raw.get("stdout"),
        stderr=raw.get("stderr"),
        error=None if status == "ok" else (raw.get("stderr") or "non-zero exit"),
        duration_ms=raw.get("duration_ms"),
    )
    await audit.write(
        user_id=user_id,
        actor=f"agent:skill:{skill['title']}",
        action="skill.run",
        target=skill["id"],
        payload={"duration_ms": raw.get("duration_ms"), "exit_code": raw.get("exit_code")},
        ok=status == "ok",
        error=None if status == "ok" else _short(raw.get("stderr")),
    )

    if status == "ok":
        suffix = " (saved as a reusable skill)" if first_run else ""
        result_preview = _preview(raw.get("result"))
        text = f"Done{suffix}. {result_preview}" if result_preview else f"Done{suffix}."
    else:
        text = (
            "That didn't work — the script errored out. "
            f"({_short(raw.get('stderr')) or 'no stderr'}). "
            "Want me to try a different approach?"
        )

    return SkillOutcome(final_text=text, skill_id=skill["id"], raw=raw)


def _credential_ask(missing: list[str], explanation: str | None = None) -> str:
    keys = ", ".join(missing)
    if explanation:
        return f"Before I can run that, I need: {keys}.\n{explanation}\nReply with the values (e.g. `key=value`, one per line) or open Settings → Credentials."
    return (
        f"To do that, I need a few things from you: {keys}. "
        "Reply with `key=value` (one per line), or set them in Settings → Credentials."
    )


async def _user_credential_keys(user_id: str) -> list[str]:
    from ..db import supabase_admin
    sb = supabase_admin()
    res = sb.table("skill_credentials").select("key").eq("user_id", user_id).execute()
    return [r["key"] for r in (res.data or [])]


def _preview(result) -> str:
    if result is None:
        return ""
    s = str(result)
    return s if len(s) <= 240 else s[:240] + "…"


def _short(s) -> str:
    if not s:
        return ""
    s = str(s).strip().splitlines()[-1]
    return s[:160]
