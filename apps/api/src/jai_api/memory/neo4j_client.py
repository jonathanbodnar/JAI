"""Neo4j Aura client — the graph of you."""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import AsyncGraphDatabase
from neo4j.time import Date, DateTime, Duration, Time

from ..config import Settings, get_settings

log = structlog.get_logger()


def _coerce(value: Any) -> Any:
    """Make Neo4j-native types JSON serializable.

    `properties(n)` will return Cypher-side temporal objects (DateTime,
    Date, etc.) which Pydantic can't dump. Convert them recursively into
    ISO strings (or primitive types) before they ever reach FastAPI's
    response serializer.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (DateTime, Date, Time)):
        return value.iso_format()
    if isinstance(value, Duration):
        return str(value)
    if isinstance(value, list):
        return [_coerce(v) for v in value]
    if isinstance(value, tuple):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    return str(value)


class JaiNeo4j:
    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._driver = AsyncGraphDatabase.driver(
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password) if s.neo4j_user else None,
        )
        self._db = s.neo4j_database
        self._hops = s.neo4j_hops

    async def upsert_entity(
        self,
        *,
        user_id: str,
        label: str,
        entity_id: str,
        properties: dict[str, Any],
    ) -> None:
        cypher = (
            f"MERGE (n:{label} {{id: $id, user_id: $user_id}}) "
            f"SET n += $props, n.updated_at = datetime() "
            f"RETURN n"
        )
        async with self._driver.session(database=self._db) as sess:
            await sess.run(cypher, id=entity_id, user_id=user_id, props=properties)

    async def delete_entity(self, *, user_id: str, node_id: str) -> int:
        """Detach-delete one node belonging to this user. Returns rows touched."""
        cypher = (
            "MATCH (n {id: $id, user_id: $uid}) "
            "DETACH DELETE n "
            "RETURN count(n) AS n"
        )
        async with self._driver.session(database=self._db) as sess:
            res = await sess.run(cypher, id=node_id, uid=user_id)
            rec = await res.single()
            return int(rec["n"]) if rec else 0

    async def update_entity_name(self, *, user_id: str, node_id: str, name: str) -> bool:
        """Rename a node and bump updated_at."""
        cypher = (
            "MATCH (n {id: $id, user_id: $uid}) "
            "SET n.name = $name, n.updated_at = datetime() "
            "RETURN n"
        )
        async with self._driver.session(database=self._db) as sess:
            res = await sess.run(cypher, id=node_id, uid=user_id, name=name)
            return (await res.single()) is not None

    async def delete_by_name_fragment(
        self, *, user_id: str, fragment: str
    ) -> list[dict]:
        """Detach-delete every node whose name contains `fragment` (case-insensitive).
        Returns the deleted nodes' {id, label, name} for confirmation messaging."""
        if not fragment.strip():
            return []
        cypher = (
            "MATCH (n) "
            "WHERE n.user_id = $uid AND toLower(n.name) CONTAINS toLower($frag) "
            "WITH n, labels(n)[0] AS label, n.id AS id, n.name AS name "
            "DETACH DELETE n "
            "RETURN id, label, name"
        )
        out: list[dict] = []
        async with self._driver.session(database=self._db) as sess:
            res = await sess.run(cypher, uid=user_id, frag=fragment.strip())
            async for rec in res:
                out.append({"id": rec["id"], "label": rec["label"], "name": rec["name"]})
        return out

    async def upsert_rel(
        self,
        *,
        user_id: str,
        src_label: str,
        src_id: str,
        rel_type: str,
        dst_label: str,
        dst_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        cypher = (
            f"MATCH (a:{src_label} {{id: $src_id, user_id: $user_id}}), "
            f"      (b:{dst_label} {{id: $dst_id, user_id: $user_id}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"SET r += $props, r.updated_at = datetime()"
        )
        async with self._driver.session(database=self._db) as sess:
            await sess.run(
                cypher,
                src_id=src_id,
                dst_id=dst_id,
                user_id=user_id,
                props=properties or {},
            )

    async def subgraph_for_entities(
        self,
        user_id: str,
        names: list[str],
    ) -> list[dict]:
        """Pull a 1-hop subgraph around any node whose name matches in `names`."""
        if not names:
            return []
        cypher = (
            "MATCH (n) WHERE n.user_id = $uid AND toLower(n.name) IN $names "
            "OPTIONAL MATCH (n)-[r]-(m) WHERE m.user_id = $uid "
            "RETURN n, collect({rel: type(r), node: m}) AS edges "
            "LIMIT 25"
        )
        out: list[dict] = []
        async with self._driver.session(database=self._db) as sess:
            res = await sess.run(cypher, uid=user_id, names=[n.lower() for n in names])
            async for rec in res:
                node = _coerce(dict(rec["n"]))
                edges = [
                    {
                        "rel": e["rel"],
                        "node": _coerce(dict(e["node"])) if e["node"] else None,
                    }
                    for e in rec["edges"]
                    if e["node"] is not None
                ]
                out.append({"node": node, "edges": edges})
        return out

    async def fetch_all_concepts(self, user_id: str) -> list[dict]:
        """Return every concept-class node with its degree — used by the
        deduplication pass to pick the canonical survivor in each group."""
        cypher = (
            "MATCH (n) "
            "WHERE n.user_id = $uid "
            "  AND labels(n)[0] IN ['Belief','Topic','Project','Concept','Company','Tool','Pattern','Skill','Decision','Person'] "
            "  AND coalesce(n.is_me, false) = false "
            "OPTIONAL MATCH (n)-[r]-() "
            "WITH n, labels(n)[0] AS label, count(r) AS degree "
            "RETURN label, n.id AS id, coalesce(n.name, '') AS name, "
            "       coalesce(n.updated_at, datetime()) AS updated_at, degree"
        )
        out: list[dict] = []
        async with self._driver.session(database=self._db) as sess:
            res = await sess.run(cypher, uid=user_id)
            async for rec in res:
                out.append(
                    {
                        "id": rec["id"],
                        "label": rec["label"],
                        "name": rec["name"],
                        "updated_at": str(rec["updated_at"]),
                        "degree": int(rec["degree"] or 0),
                    }
                )
        return out

    async def merge_nodes(
        self, *, user_id: str, canonical_id: str, dup_id: str
    ) -> dict[str, int]:
        """Re-route every edge of `dup_id` onto `canonical_id`, then detach-delete `dup_id`.

        Edges are MERGE'd by type so the canonical node never accumulates
        parallel duplicate relationships of the same type to the same neighbor."""
        if canonical_id == dup_id:
            return {"edges_moved": 0, "deleted": 0}

        moved = 0
        deleted = 0
        async with self._driver.session(database=self._db) as sess:
            # Resolve canonical label so we can build typed Cypher.
            res = await sess.run(
                "MATCH (c {id: $cid, user_id: $uid}) RETURN labels(c)[0] AS l",
                cid=canonical_id, uid=user_id,
            )
            rec = await res.single()
            if not rec:
                return {"edges_moved": 0, "deleted": 0}
            canon_label = rec["l"]

            # Pull outgoing rels of the duplicate.
            outgoing: list[tuple[str, str, str]] = []
            res = await sess.run(
                "MATCH (d {id: $dup, user_id: $uid})-[r]->(t) "
                "WHERE t.user_id = $uid AND t.id <> $cid "
                "RETURN type(r) AS rel, t.id AS tid, labels(t)[0] AS tlabel",
                dup=dup_id, uid=user_id, cid=canonical_id,
            )
            async for r in res:
                outgoing.append((r["rel"], r["tid"], r["tlabel"]))

            # Pull incoming rels.
            incoming: list[tuple[str, str, str]] = []
            res = await sess.run(
                "MATCH (s)-[r]->(d {id: $dup, user_id: $uid}) "
                "WHERE s.user_id = $uid AND s.id <> $cid "
                "RETURN type(r) AS rel, s.id AS sid, labels(s)[0] AS slabel",
                dup=dup_id, uid=user_id, cid=canonical_id,
            )
            async for r in res:
                incoming.append((r["rel"], r["sid"], r["slabel"]))

            for rel, tid, tlabel in outgoing:
                try:
                    await sess.run(
                        f"MATCH (c:{canon_label} {{id: $cid, user_id: $uid}}), "
                        f"      (t:{tlabel} {{id: $tid, user_id: $uid}}) "
                        f"MERGE (c)-[:{rel}]->(t)",
                        cid=canonical_id, tid=tid, uid=user_id,
                    )
                    moved += 1
                except Exception as e:
                    log.warning("merge.out_edge_failed", rel=rel, error=str(e))

            for rel, sid, slabel in incoming:
                try:
                    await sess.run(
                        f"MATCH (s:{slabel} {{id: $sid, user_id: $uid}}), "
                        f"      (c:{canon_label} {{id: $cid, user_id: $uid}}) "
                        f"MERGE (s)-[:{rel}]->(c)",
                        sid=sid, cid=canonical_id, uid=user_id,
                    )
                    moved += 1
                except Exception as e:
                    log.warning("merge.in_edge_failed", rel=rel, error=str(e))

            res = await sess.run(
                "MATCH (d {id: $dup, user_id: $uid}) DETACH DELETE d RETURN 1 AS done",
                dup=dup_id, uid=user_id,
            )
            if await res.single():
                deleted = 1

        return {"edges_moved": moved, "deleted": deleted}

    async def fetch_recent_concepts(self, user_id: str, limit: int = 60) -> list[dict]:
        """Return the user's most recently touched concept-like nodes for the
        cross-link inference pass.

        Skips the Me node and external Documents (those are anchors, not
        targets for conceptual edges)."""
        cypher = (
            "MATCH (n) "
            "WHERE n.user_id = $uid "
            "  AND labels(n)[0] IN ['Belief','Topic','Project','Concept','Company','Tool','Pattern','Skill','Decision'] "
            "  AND coalesce(n.is_me, false) = false "
            "RETURN labels(n)[0] AS label, n.id AS id, coalesce(n.name, '') AS name "
            "ORDER BY coalesce(n.updated_at, datetime()) DESC "
            "LIMIT $limit"
        )
        out: list[dict] = []
        async with self._driver.session(database=self._db) as sess:
            res = await sess.run(cypher, uid=user_id, limit=limit)
            async for rec in res:
                out.append({"label": rec["label"], "id": rec["id"], "name": rec["name"]})
        return out

    async def graph_dump(self, user_id: str, limit: int = 200) -> dict:
        """Used by the Context panel to render the whole user graph."""
        cypher_nodes = (
            "MATCH (n) WHERE n.user_id = $uid "
            "RETURN labels(n)[0] AS label, n.id AS id, n.name AS name, "
            "       properties(n) AS props LIMIT $limit"
        )
        cypher_edges = (
            "MATCH (a)-[r]->(b) WHERE a.user_id = $uid AND b.user_id = $uid "
            "RETURN a.id AS src, b.id AS dst, type(r) AS rel LIMIT $limit"
        )
        nodes: list[dict] = []
        edges: list[dict] = []
        async with self._driver.session(database=self._db) as sess:
            res = await sess.run(cypher_nodes, uid=user_id, limit=limit)
            async for rec in res:
                nodes.append(_coerce(dict(rec)))
            res = await sess.run(cypher_edges, uid=user_id, limit=limit)
            async for rec in res:
                edges.append(_coerce(dict(rec)))
        return {"nodes": nodes, "edges": edges}

    async def close(self) -> None:
        await self._driver.close()
