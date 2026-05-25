"""Build the LangGraph and own its lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from langgraph.graph import END, START, StateGraph

from ..config import Settings
from ..memory.mem0 import JaiMem0
from ..memory.neo4j_client import JaiNeo4j
from ..memory.qdrant import JaiQdrant
from .checkpointer import make_checkpointer
from .nodes.fast_intent import fast_intent
from .nodes.ingest import ingest
from .nodes.orchestrator import orchestrator
from .nodes.persist_memory import make_persist
from .nodes.reflect import reflect
from .nodes.retrieve_memory import make_retrieve
from .nodes.skill_executor import skill_executor
from .nodes.strategize import strategize
from .nodes.tool_router import tool_router
from .state import JaiState

log = structlog.get_logger()


@dataclass
class JaiGraph:
    app: object  # CompiledGraph; opaque to the rest of the app
    mem0: JaiMem0
    qdrant: JaiQdrant
    neo4j: JaiNeo4j
    pool: object | None  # psycopg pool when checkpointer is enabled


def _route_after_orchestrator(state: JaiState) -> str:
    r = state.get("route")
    if r in ("respond", "ask"):
        return "persist"
    return {
        "reflect": "reflect",
        "strategize": "strategize",
        "tool": "tool",
        "skill": "skill",
    }.get(r, "persist")


def _route_after_fast_intent(state: JaiState) -> str:
    """If fast_intent set final_text via a builtin, skip everything else."""
    if state.get("final_text") and state.get("role_used", "").startswith("builtin:"):
        return "persist"
    return "retrieve"


async def build_graph(settings: Settings) -> JaiGraph:
    mem0 = JaiMem0(settings)
    qdrant = JaiQdrant(settings)
    neo4j = JaiNeo4j(settings)

    # Best-effort init; first request will fail loudly if creds are bad.
    try:
        await qdrant.ensure_collection()
    except Exception as e:
        log.warning("qdrant.init_failed", error=str(e))

    retrieve = make_retrieve(mem0, qdrant, neo4j)
    persist = make_persist(mem0, qdrant)

    g: StateGraph = StateGraph(JaiState)
    g.add_node("ingest", ingest)
    g.add_node("fast_intent", fast_intent)
    g.add_node("retrieve", retrieve)
    g.add_node("orchestrator", orchestrator)
    g.add_node("reflect", reflect)
    g.add_node("strategize", strategize)
    g.add_node("tool", tool_router)
    g.add_node("skill", skill_executor)
    g.add_node("persist", persist)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "fast_intent")
    # Skip retrieve+orchestrator when a builtin already handled the turn.
    g.add_conditional_edges(
        "fast_intent",
        _route_after_fast_intent,
        {"persist": "persist", "retrieve": "retrieve"},
    )
    g.add_edge("retrieve", "orchestrator")
    g.add_conditional_edges(
        "orchestrator",
        _route_after_orchestrator,
        {
            "persist": "persist",
            "reflect": "reflect",
            "strategize": "strategize",
            "tool": "tool",
            "skill": "skill",
        },
    )
    g.add_edge("reflect", "persist")
    g.add_edge("strategize", "persist")
    g.add_edge("tool", "persist")
    g.add_edge("skill", "persist")
    g.add_edge("persist", END)

    pool = None
    if settings.database_url:
        try:
            saver, pool = await make_checkpointer(settings)
            app = g.compile(checkpointer=saver)
        except Exception as e:
            log.warning("checkpointer.init_failed", error=str(e))
            app = g.compile()
    else:
        log.warning("checkpointer.disabled", reason="DATABASE_URL not set")
        app = g.compile()

    return JaiGraph(app=app, mem0=mem0, qdrant=qdrant, neo4j=neo4j, pool=pool)


async def close_graph(graph: JaiGraph) -> None:
    await graph.qdrant.close()
    await graph.neo4j.close()
    if graph.pool is not None:
        try:
            await graph.pool.close()
        except Exception:
            pass
