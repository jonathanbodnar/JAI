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
    need_credentials: list[str] = Field(default_factory=list)
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
    log.info(
        "skill.build",
        title=draft.title,
        language=draft.language,
        need=draft.need_credentials,
    )
    return draft
