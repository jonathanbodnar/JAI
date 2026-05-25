"""Role → model resolution. Roles are stable; slugs swap via env."""

from __future__ import annotations

from enum import StrEnum

from langchain_openai import ChatOpenAI

from ..config import Settings, get_settings
from .openrouter import openrouter_chat


class Role(StrEnum):
    ORCHESTRATOR = "orchestrator"
    REFLECTION = "reflection"
    STRATEGY = "strategy"
    SKILL_BUILDER = "skill_builder"
    FAST = "fast"


def model_for(role: Role, *, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return {
        Role.ORCHESTRATOR: s.jai_model_orchestrator,
        Role.REFLECTION: s.jai_model_reflection,
        Role.STRATEGY: s.jai_model_strategy,
        Role.SKILL_BUILDER: s.jai_model_skill_builder,
        Role.FAST: s.jai_model_fast,
    }[role]


def chat_for(
    role: Role,
    *,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    streaming: bool = True,
    settings: Settings | None = None,
) -> ChatOpenAI:
    return openrouter_chat(
        model_for(role, settings=settings),
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        settings=settings,
    )
