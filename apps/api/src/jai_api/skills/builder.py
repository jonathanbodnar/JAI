"""The Skill Builder agent.

Asks the LLM to either:
  - declare which credentials are missing, or
  - emit a runnable script with title + description.
"""

from __future__ import annotations

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

    draft: SkillDraft = await structured.ainvoke([sys, human])

    # Belt-and-suspenders: scan the source for env var references and
    # union with whatever the LLM declared. LLMs sometimes forget to
    # populate `uses_credentials` even when the script reads env vars
    # like GMAIL_OAUTH_JSON — and an empty list here means the skill
    # silently runs without credentials and blows up with a KeyError.
    extracted = _extract_env_keys(draft.source or "", draft.language or "python")
    declared = set(draft.uses_credentials or [])
    # Drop platform / data-source vars — those are auto-injected and don't
    # need to be on the skill's required list (which gates execution
    # against `skill_credentials`).
    platform_keys = _PLATFORM_KEYS | {k for k in extracted if k.startswith(("SUPABASE_", "JAI_"))}
    union = (declared | extracted) - platform_keys
    draft.uses_credentials = sorted(union)

    log.info(
        "skill.build",
        title=draft.title,
        language=draft.language,
        need=draft.need_credentials,
        uses=draft.uses_credentials,
    )
    return draft


# Env vars that JAI injects automatically and that we never need to gate on.
_PLATFORM_KEYS = {
    "JAI_SUPABASE_URL",
    "JAI_SUPABASE_KEY",
    "JAI_USER_ID",
    "JAI_BACKEND_URL",
    "SUPABASE_PROJECTS_JSON",
}


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
