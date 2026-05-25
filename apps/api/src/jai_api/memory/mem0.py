"""Mem0 Cloud client — identity facts about the user.

Mem0 does the extraction + consolidation for us; we just push messages and
query by user_id.
"""

from __future__ import annotations

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
        self._client = MemoryClient(
            api_key=s.mem0_api_key,
            org_id=s.mem0_org_id or None,
            project_id=s.mem0_project_id or None,
        )
        self._top_k = s.mem0_top_k

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def search(self, user_id: str, query: str) -> list[dict]:
        if not self._client:
            return []
        try:
            # mem0 client is sync; offload in caller if hot
            results = self._client.search(query=query, user_id=user_id, limit=self._top_k)
            return [{"text": r.get("memory") or r.get("text", ""), "score": r.get("score", 0)}
                    for r in (results or [])]
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
            self._client.add(messages=messages, user_id=user_id, metadata=metadata or {})
        except Exception as e:
            log.error("mem0.add.failed", error=str(e))
