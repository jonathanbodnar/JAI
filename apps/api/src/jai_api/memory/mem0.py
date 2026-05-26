"""Mem0 Cloud client — identity facts about the user.

Mem0's SDK is sync, but every JAI hot path is async. Wrap each call in
`asyncio.to_thread` so the event loop isn't blocked for the ~150–600ms a
Mem0 round-trip takes. This alone shaves ~half a second off every chat
turn (search runs in parallel with Qdrant/Neo4j now).
"""

from __future__ import annotations

import asyncio

import structlog
from mem0 import MemoryClient

from ..config import Settings, get_settings

log = structlog.get_logger()


class JaiMem0:
    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        if not s.mem0_api_key:
            log.warning("mem0.disabled", reason="no api key")
            self._client = None
            return
        # mem0ai v2 dropped org_id / project_id from the constructor; both are
        # inferred from the API key's account context.
        self._client = MemoryClient(api_key=s.mem0_api_key)
        self._top_k = s.mem0_top_k

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def search(self, user_id: str, query: str) -> list[dict]:
        if not self._client:
            return []
        try:
            results = await asyncio.to_thread(
                self._client.search, query=query, user_id=user_id, limit=self._top_k
            )
            return [
                {
                    "text": r.get("memory") or r.get("text", ""),
                    "score": r.get("score", 0),
                }
                for r in (results or [])
            ]
        except Exception as e:
            log.error("mem0.search.failed", error=str(e))
            return []

    async def add(
        self,
        user_id: str,
        messages: list[dict],
        *,
        metadata: dict | None = None,
    ) -> None:
        if not self._client:
            return
        try:
            await asyncio.to_thread(
                self._client.add,
                messages=messages,
                user_id=user_id,
                metadata=metadata or {},
            )
        except Exception as e:
            log.error("mem0.add.failed", error=str(e))

    async def delete_about(self, user_id: str, query: str, limit: int = 10) -> int:
        """Best-effort delete memories matching `query` (used by 'forget X')."""
        if not self._client:
            return 0
        try:
            hits = await asyncio.to_thread(
                self._client.search, query=query, user_id=user_id, limit=limit
            )
            ids = [h.get("id") for h in (hits or []) if h.get("id")]
            for mid in ids:
                try:
                    await asyncio.to_thread(self._client.delete, memory_id=mid)
                except Exception as e:
                    log.warning("mem0.delete.failed", id=mid, error=str(e))
            return len(ids)
        except Exception as e:
            log.warning("mem0.delete_about.failed", error=str(e))
            return 0
