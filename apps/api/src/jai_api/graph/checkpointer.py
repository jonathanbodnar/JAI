"""Postgres-backed LangGraph checkpointer for durable, resumable state."""

from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from ..config import Settings


async def make_checkpointer(settings: Settings) -> tuple[AsyncPostgresSaver, AsyncConnectionPool]:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the LangGraph checkpointer")
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        max_size=20,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return saver, pool
