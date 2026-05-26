"""Curated library of pre-built JAI skills.

These ship with the codebase and get seeded into the user's `skills`
table on demand (Settings → Skills → "Install starter library", or first
sign-in if we want auto-install). The point is to skip the redundant
"have the LLM generate a Gmail-list script from scratch" loop for every
new user — which costs latency, tokens, and a fresh chance to introduce
a bug.

Each skill is a Python module exporting:
  KEY                 stable id (slug, namespaced like "gmail.read_inbox")
  TITLE               human title
  DESCRIPTION         what it does (used by the matcher for similarity)
  LANGUAGE            "python" | "typescript" | "bash"
  SOURCE              full script string
  USES_CREDENTIALS    list[str] — env vars the script reads that JAI
                      does NOT auto-inject (platform/oauth/data-source
                      keys never go here — they're injected for free)
  REQUIRED_TOOLS      list[str] — informational tags ("gmail", "drive")
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pkgutil import iter_modules
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LibrarySkill:
    key: str
    title: str
    description: str
    language: str
    source: str
    uses_credentials: list[str]
    required_tools: list[str]


def _iter_modules() -> Iterable[str]:
    """Walk every namespace package under `library/` and yield dotted paths."""
    pkg_dir = Path(__file__).parent
    prefix = "jai_api.skills.library."
    for sub in pkg_dir.iterdir():
        if not sub.is_dir() or sub.name.startswith("_"):
            continue
        for _, name, ispkg in iter_modules([str(sub)]):
            if ispkg or name.startswith("_"):
                continue
            yield f"{prefix}{sub.name}.{name}"


def load_library() -> list[LibrarySkill]:
    """Discover and return every skill module in the library tree.

    Modules can ship their own KEY/TITLE/etc. constants OR export a
    `SKILL = LibrarySkill(...)` directly. Either pattern works; we
    prefer the second when present.
    """
    out: list[LibrarySkill] = []
    for dotted in _iter_modules():
        mod = import_module(dotted)
        if hasattr(mod, "SKILL") and isinstance(mod.SKILL, LibrarySkill):
            out.append(mod.SKILL)
            continue
        try:
            out.append(
                LibrarySkill(
                    key=mod.KEY,
                    title=mod.TITLE,
                    description=mod.DESCRIPTION,
                    language=mod.LANGUAGE,
                    source=mod.SOURCE,
                    uses_credentials=getattr(mod, "USES_CREDENTIALS", []),
                    required_tools=getattr(mod, "REQUIRED_TOOLS", []),
                )
            )
        except AttributeError as e:
            raise RuntimeError(f"library module {dotted} missing required field: {e}")
    return out
