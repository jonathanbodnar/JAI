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

        mem0_task = asyncio.create_task(mem0.search(user_id, query))
        qdrant_task = asyncio.create_task(qdrant.search(user_id, query))
        graph_task = asyncio.create_task(neo4j.subgraph_for_entities(user_id, entities))

        mem0_hits, qdrant_hits, graph_hits = await asyncio.gather(
            mem0_task, qdrant_task, graph_task, return_exceptions=True
        )

        def _coerce(x):
            if isinstance(x, Exception):
                log.warning("retrieve.failed", error=str(x))
                return []
            return x

        return {
            "retrieved_mem0": _coerce(mem0_hits),
            "retrieved_qdrant": _coerce(qdrant_hits),
            "retrieved_graph": _coerce(graph_hits),
        }

    return retrieve
