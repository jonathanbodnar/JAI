"""Database clients (Supabase REST + raw asyncpg pool for LangGraph checkpointer)."""

from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings


@lru_cache
def supabase_admin() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase URL or service role key missing")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
