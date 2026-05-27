"""Pull from Mem0 + Qdrant + Neo4j in parallel, with per-source timeouts.

Memory retrieval is on the hot path for every non-fast-lane turn. If a
single backend (typically Mem0 cloud or Neo4j Aura waking from auto-
pause) is slow, the whole turn waits on it. We cap each source at a
hard upper bound and treat a timeout the same as "no results" — the
LLM can still answer, just with less context.
"""

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


# Per-source upper bound. Tuned to "fast enough that a healthy backend
# always lands well inside it, slow enough that a cold cloud instance
# still has a chance". A timeout returns [] instead of raising — we'd
# rather a slightly thinner context than a 30s hang.
_SOURCE_TIMEOUT_S = 1.8


async def _with_timeout(name: str, coro, timeout: float):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        log.warning("retrieve.timeout", source=name, timeout=timeout)
        return []
    except Exception as e:
        log.warning("retrieve.failed", source=name, error=str(e)[:200], error_type=type(e).__name__)
        return []


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

        mem0_hits, qdrant_hits, graph_hits = await asyncio.gather(
            _with_timeout("mem0", mem0.search(user_id, query), _SOURCE_TIMEOUT_S),
            _with_timeout("qdrant", qdrant.search(user_id, query), _SOURCE_TIMEOUT_S),
            _with_timeout("graph", neo4j.subgraph_for_entities(user_id, entities), _SOURCE_TIMEOUT_S),
        )

        # Defensive: anything not a list (None, dict, etc.) collapses to [].
        def _as_list(x):
            return x if isinstance(x, list) else []

        mem0_clean = _as_list(mem0_hits)
        qdrant_clean = _as_list(qdrant_hits)
        graph_clean = _as_list(graph_hits)

        log.info(
            "retrieve.hits",
            user=user_id[:8],
            mem0=len(mem0_clean),
            qdrant=len(qdrant_clean),
            graph=len(graph_clean),
            entities=entities,
        )

        return {
            "retrieved_mem0": mem0_clean,
            "retrieved_qdrant": qdrant_clean,
            "retrieved_graph": graph_clean,
        }

    return retrieve
