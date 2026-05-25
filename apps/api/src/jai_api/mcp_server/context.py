"""Request-scoped user context for the internal MCP server.

The middleware (in main.py) resolves the user from the bearer token and sets
the contextvar before delegating to the mounted FastMCP ASGI app. Tools then
call `current_user_id()` instead of reading the env var.
"""

from __future__ import annotations

from contextvars import ContextVar

from ..config import get_settings

_USER_ID: ContextVar[str | None] = ContextVar("jai_mcp_user_id", default=None)


def set_user_id(user_id: str | None) -> None:
    _USER_ID.set(user_id)


def current_user_id() -> str:
    uid = _USER_ID.get()
    if uid:
        return uid
    fallback = get_settings().jai_user_id
    if fallback:
        return fallback
    raise RuntimeError("No user in context. Pass a Supabase JWT or set JAI_USER_ID.")
