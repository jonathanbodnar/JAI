"""The Skill Builder agent.

Asks the LLM to either:
  - declare which credentials are missing, or
  - emit a runnable script with title + description.
"""

from __future__ import annotations

import ast
from typing import Literal

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..models.registry import Role, chat_for
from ..graph.prompts import SKILL_BUILDER_SYSTEM

log = structlog.get_logger()


class SkillDraft(BaseModel):
    # Credentials the user does NOT have yet. If non-empty, JAI asks the
    # user to provide them before generating a script.
    need_credentials: list[str] = Field(default_factory=list)
    # Every credential the generated script reads from env. Used to inject
    # the right values at run time AND to gate execution if any go missing.
    uses_credentials: list[str] = Field(default_factory=list)
    explanation: str | None = None
    language: Literal["python", "typescript", "bash"] | None = None
    source: str | None = None
    title: str | None = None
    description: str | None = None
    required_tools: list[str] = Field(default_factory=list)


def _format_creds(have: list[str]) -> str:
    if not have:
        return "(none yet)"
    return ", ".join(sorted(have))


async def build_skill(
    *,
    goal: str,
    available_credentials: list[str],
    context_hint: str | None = None,
) -> SkillDraft:
    llm = chat_for(Role.SKILL_BUILDER, temperature=0.2, streaming=False)
    structured = llm.with_structured_output(SkillDraft)

    sys = SystemMessage(
        content=SKILL_BUILDER_SYSTEM
        + f"\n\n=== AVAILABLE CREDENTIALS ===\n{_format_creds(available_credentials)}"
    )
    human_parts: list[str] = [f"Goal: {goal}"]
    if context_hint:
        human_parts.append(f"\nContext from prior conversation:\n{context_hint}")
    human = HumanMessage(content="\n".join(human_parts))

    # Structured-output parsing on Qwen Max can fail when the model emits
    # a very long `source` field with literal newlines that don't escape
    # cleanly into the tool-call JSON. Surface a friendly draft instead
    # of crashing the entire graph turn — the caller will route the
    # explanation back to the user.
    try:
        draft: SkillDraft = await structured.ainvoke([sys, human])
    except Exception as e:
        log.warning(
            "skill.build.parse_failed",
            error=str(e)[:300],
            error_type=type(e).__name__,
            goal=goal[:120],
        )
        return SkillDraft(
            explanation=(
                "I couldn't generate a clean skill for that — the script "
                "draft came back malformed. Try rephrasing the request, or "
                "if you're asking me to transform data we already have "
                "in scope, just say \"go\" or \"do it\" and I'll work from "
                "the cached result."
            ),
            need_credentials=[],
            uses_credentials=[],
        )

    # SYNTAX GUARD — if the LLM emitted Python with a syntax error
    # (very common: missing closing paren on the last line, unterminated
    # string, bad indentation), don't push it to the sandbox. Try one
    # repair pass with the actual SyntaxError in the prompt; if that
    # still fails, surface the issue to the user instead of running
    # broken code that wastes 8s on a sandbox boot.
    if (draft.language or "python") == "python" and draft.source:
        repaired = await _ensure_python_parses(
            source=draft.source,
            goal=goal,
            context_hint=context_hint,
            structured=structured,
            sys=sys,
        )
        if repaired is None:
            return SkillDraft(
                explanation=(
                    "I drafted a script but it had a Python syntax error "
                    "I couldn't fix automatically. Try rephrasing the "
                    "request, or paste the data you want me to work with "
                    "and I'll handle it in-chat."
                ),
                need_credentials=[],
                uses_credentials=[],
            )
        draft.source = repaired

    # Belt-and-suspenders: scan the source for env var references and
    # union with whatever the LLM declared. LLMs sometimes forget to
    # populate `uses_credentials` even when the script reads env vars
    # like GMAIL_OAUTH_JSON — and an empty list here means the skill
    # silently runs without credentials and blows up with a KeyError.
    extracted = _extract_env_keys(draft.source or "", draft.language or "python")
    declared = set(draft.uses_credentials or [])

    def _is_platform(key: str) -> bool:
        if key in _PLATFORM_KEYS:
            return True
        return any(key.startswith(p) for p in _PLATFORM_PREFIXES)

    # Drop platform / data-source vars — those are auto-injected and don't
    # need to be on the skill's required list (which gates execution
    # against `skill_credentials`).
    union = {k for k in (declared | extracted) if not _is_platform(k)}
    draft.uses_credentials = sorted(union)

    log.info(
        "skill.build",
        title=draft.title,
        language=draft.language,
        need=draft.need_credentials,
        uses=draft.uses_credentials,
    )
    return draft


# Env vars that JAI injects automatically and that we never need to gate
# on. If we DID gate on them they'd show up as "missing credentials" in
# the chat and the user would be asked to provide a value for an env
# var they don't even know exists.
_PLATFORM_KEYS = {
    # JAI's own Supabase (auto-injected from app config)
    "JAI_SUPABASE_URL",
    "JAI_SUPABASE_KEY",
    "JAI_USER_ID",
    "JAI_BACKEND_URL",
    # OpenRouter platform key — auto-injected for skills that draft text.
    "OPENROUTER_API_KEY",
    # External Supabase projects connected via Settings → Data Sources
    "SUPABASE_PROJECTS_JSON",
    # Multi-account OAuth blobs (auto-injected from connected_accounts)
    "GMAIL_ACCOUNTS_JSON",
    "CALENDAR_ACCOUNTS_JSON",
    "DRIVE_ACCOUNTS_JSON",
}


# Env vars that look like prefixed convenience vars — also auto-injected
# and should never appear on the required list.
_PLATFORM_PREFIXES = (
    "SUPABASE_",   # per-source data project vars (SUPABASE_SHOUTOUT_URL, etc.)
    "JAI_",
)


async def _ensure_python_parses(
    *,
    source: str,
    goal: str,
    context_hint: str | None,
    structured,
    sys: SystemMessage,
) -> str | None:
    """Make sure `source` is parseable Python. Try one auto-repair pass.

    Returns the (possibly repaired) source, or None if it still won't parse.
    """
    err = _syntax_error(source)
    if err is None:
        return source

    log.warning("skill.build.syntax_error", error=str(err)[:200], goal=goal[:120])

    # One repair attempt: feed the broken source + the exact SyntaxError
    # back to Qwen and ask for a fixed version. Same structured-output
    # contract so we keep title/description/required_credentials etc.
    repair_msg = HumanMessage(
        content=(
            f"Goal: {goal}\n\n"
            f"You just drafted this Python skill, but it does not parse:\n\n"
            f"```python\n{source}\n```\n\n"
            f"Python's parser said: {err}\n\n"
            f"Re-emit the SAME skill with the syntax error fixed. Keep the "
            f"same title, description, language, and uses_credentials. Do "
            f"not change behavior — just fix the parse error (most likely "
            f"an unbalanced paren on the print/json.dumps line, or an "
            f"unterminated string)."
            + (f"\n\nOriginal context:\n{context_hint}" if context_hint else "")
        )
    )
    try:
        repaired_draft: SkillDraft = await structured.ainvoke([sys, repair_msg])
    except Exception as e:
        log.warning("skill.build.repair_parse_failed", error=str(e)[:200])
        return None

    new_src = repaired_draft.source or ""
    if not new_src:
        return None
    if _syntax_error(new_src) is not None:
        log.warning("skill.build.repair_still_invalid")
        return None
    log.info("skill.build.syntax_repaired", goal=goal[:120])
    return new_src


def _syntax_error(source: str) -> SyntaxError | None:
    """Return the SyntaxError if `source` doesn't parse, else None."""
    try:
        ast.parse(source)
        return None
    except SyntaxError as e:
        return e


def _extract_env_keys(source: str, language: str) -> set[str]:
    """Pull credential-shaped env var names out of a script.

    Looks for:
      - Python: os.environ["FOO"], os.environ.get("FOO"), os.getenv("FOO")
      - JS/TS:  process.env.FOO, process.env["FOO"]
    Keeps only ALL_CAPS_WITH_UNDERSCORES names so we don't pick up
    incidental matches like home-dir references.
    """
    import re

    found: set[str] = set()
    if not source:
        return found

    patterns = [
        r"""os\.environ\[\s*['"]([A-Z][A-Z0-9_]+)['"]\s*\]""",
        r"""os\.environ\.get\(\s*['"]([A-Z][A-Z0-9_]+)['"]""",
        r"""os\.getenv\(\s*['"]([A-Z][A-Z0-9_]+)['"]""",
        r"""process\.env\.([A-Z][A-Z0-9_]+)""",
        r"""process\.env\[\s*['"]([A-Z][A-Z0-9_]+)['"]\s*\]""",
    ]
    for p in patterns:
        for m in re.finditer(p, source):
            found.add(m.group(1))
    return found
