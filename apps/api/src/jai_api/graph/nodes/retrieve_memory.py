"""Pull from Mem0 + Qdrant + Neo4j in parallel."""

from __future__ import annotations

import asyncio
import re

import structlog

from ...memory.mem0 import JaiMem0
from ...memory.neo4j_client import JaiNeo4j
from ...memory.qdrant import JaiQdrant
from ..state import JaiState

log = structlog.get_logger()

# Crude entity heuristic — we replace with NER later; for now anything
# Capitalized that isn't sentence-initial is fair game for graph lookup.
_ENTITY = re.compile(r"\b([A-Z][a-zA-Z0-9_-]{2,})\b")


def make_retrieve(mem0: JaiMem0, qdrant: JaiQdrant, neo4j: JaiNeo4j):
    async def retrieve(state: JaiState) -> dict:
        user_id = state["user_id"]
        query = state.get("input_text") or ""
        if not query:
            return {}

        entities = list({m.group(1) for m in _ENTITY.finditer(query)})[:5]

        # Best-effort ensure indexes exist (idempotent, cheap after first run).
        try:
            await qdrant.ensure_collection()
        except Exception as e:
            log.warning("retrieve.ensure_collection_failed", error=str(e))

        mem0_task = asyncio.create_task(mem0.search(user_id, query))
        qdrant_task = asyncio.create_task(qdrant.search(user_id, query))
        graph_task = asyncio.create_task(neo4j.subgraph_for_entities(user_id, entities))

        mem0_hits, qdrant_hits, graph_hits = await asyncio.gather(
            mem0_task, qdrant_task, graph_task, return_exceptions=True
        )

        def _coerce(name: str, x):
            if isinstance(x, Exception):
                log.warning(f"retrieve.{name}.failed", error=str(x), error_type=type(x).__name__)
                return []
            return x

        mem0_clean = _coerce("mem0", mem0_hits)
        qdrant_clean = _coerce("qdrant", qdrant_hits)
        graph_clean = _coerce("graph", graph_hits)

        log.info(
            "retrieve.hits",
            user=user_id[:8],
            mem0=len(mem0_clean) if isinstance(mem0_clean, list) else 0,
            qdrant=len(qdrant_clean) if isinstance(qdrant_clean, list) else 0,
            graph=len(graph_clean) if isinstance(graph_clean, list) else 0,
            entities=entities,
        )

        return {
            "retrieved_mem0": mem0_clean,
            "retrieved_qdrant": qdrant_clean,
            "retrieved_graph": graph_clean,
        }

    return retrieve
