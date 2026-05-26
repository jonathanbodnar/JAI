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

    # Always inject platform credentials so skills can call JAI's own
    # Supabase and API without the user having to store them manually.
    platform_env = _platform_env(user_id)
    merged_env = {**platform_env, **creds}  # user creds win on collision

    sandbox = SandboxClient()
    try:
        raw = await sandbox.run(
            user_id=user_id,
            skill_id=skill["id"],
            language=skill["language"],
            source=skill["source"],
            env=merged_env,
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
        # Keep enough of the error in the user-facing message that they can
        # actually act on it (token expired → reconnect, 403 → grant scope,
        # etc.) without digging into Supabase.
        diag = _error_diag(raw)
        text = (
            "That didn't work — the script errored out.\n\n"
            f"```\n{diag}\n```\n"
            "Want me to try a different approach, or reconnect the account in Settings?"
        )

    return SkillOutcome(
        final_text=text,
        skill_id=skill["id"],
        raw={**(raw or {}), "skill_name": skill.get("title")},
    )


def _credential_ask(missing: list[str], explanation: str | None = None) -> str:
    keys = ", ".join(missing)
    if explanation:
        return f"Before I can run that, I need: {keys}.\n{explanation}\nReply with the values (e.g. `key=value`, one per line) or open Settings → Credentials."
    return (
        f"To do that, I need a few things from you: {keys}. "
        "Reply with `key=value` (one per line), or set them in Settings → Credentials."
    )


def _platform_env(user_id: str) -> dict[str, str]:
    """Credentials every skill gets for free — no user setup required.

    These are the JAI platform credentials (Supabase URL, service role key,
    backend URL, the user's own ID). Skills can use them to:
    - query/write JAI's own Supabase tables (tasks, notes, messages, etc.)
    - call JAI's internal REST API
    - cross-reference the user's projects, progress, anything stored in Supabase

    We deliberately expose the *service* role key so skills can read across
    all tables without fighting RLS. This is fine because skills run in the
    user's sandboxed container and can't exfiltrate data anywhere outside.
    """
    from ..config import get_settings
    s = get_settings()
    env: dict[str, str] = {}
    if s.supabase_url:
        env["JAI_SUPABASE_URL"] = s.supabase_url
    if s.supabase_service_role_key:
        env["JAI_SUPABASE_KEY"] = s.supabase_service_role_key
    if s.jai_backend_url:
        env["JAI_BACKEND_URL"] = s.jai_backend_url
    env["JAI_USER_ID"] = user_id
    return env


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


def _error_diag(raw: dict | None) -> str:
    """Build a multi-line diagnostic the user can actually read.

    Picks the most informative content — exit message, install log, stderr
    tail, stdout tail — and caps at ~1200 chars so the chat bubble stays
    readable but still includes enough to act on.
    """
    if not raw:
        return "(no diagnostic captured)"
    parts: list[str] = []
    err = (raw.get("error") or "").strip()
    stderr = (raw.get("stderr") or "").strip()
    stdout = (raw.get("stdout") or "").strip()

    # If the sandbox prepended a labeled install log, that's the most
    # actionable signal — keep it visible regardless of stderr length.
    if "--- install log ---" in stderr:
        parts.append(stderr)
    else:
        if err and err not in stderr:
            parts.append(err)
        if stderr:
            # Last 6 lines of stderr keeps the traceback footer (file/line +
            # exception type) without dragging in unrelated noise.
            lines = stderr.splitlines()
            parts.append("\n".join(lines[-6:]) if len(lines) > 6 else stderr)
        elif stdout:
            parts.append(stdout.splitlines()[-1])

    text = "\n".join(parts).strip() or "(empty error)"
    if len(text) > 1200:
        text = text[-1200:]
    return text
