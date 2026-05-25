"""Qdrant Cloud client — raw semantic memory of everything."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Range,
    VectorParams,
)

from ..config import Settings, get_settings
from ..models.openrouter import openrouter_embeddings

log = structlog.get_logger()

EMBED_DIM = 3072  # text-embedding-3-large


class JaiQdrant:
    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._client = AsyncQdrantClient(
            url=s.qdrant_url,
            api_key=s.qdrant_api_key or None,
        )
        self._collection = s.qdrant_collection
        self._top_k = s.qdrant_top_k
        self._embed = openrouter_embeddings(settings=s)

    async def ensure_collection(self) -> None:
        existing = await self._client.get_collections()
        names = {c.name for c in existing.collections}
        if self._collection not in names:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )
            log.info("qdrant.collection.created", name=self._collection)

        # Qdrant requires a payload index on any field used in scroll/search
        # filters. Without these, every filter call 400s with
        # "Index required but not found for X". Creating an already-existing
        # index is a no-op on the server but raises here, so we swallow.
        for field, schema in (
            ("user_id", PayloadSchemaType.KEYWORD),
            ("source", PayloadSchemaType.KEYWORD),
            ("created_at_ts", PayloadSchemaType.INTEGER),
            ("hits", PayloadSchemaType.INTEGER),
        ):
            try:
                await self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema=schema,
                )
                log.info("qdrant.index.created", field=field)
            except UnexpectedResponse as e:
                # 409 / "already exists" — fine to ignore.
                if "already" not in str(e).lower() and "exists" not in str(e).lower():
                    log.warning("qdrant.index.create_failed", field=field, error=str(e))
            except Exception as e:
                log.warning("qdrant.index.create_failed", field=field, error=str(e))

    async def add(
        self,
        *,
        user_id: str,
        text: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        emb = (await self._embed.aembed_documents([text]))[0]
        point_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": user_id,
            "text": text,
            "source": source,
            "created_at": now.isoformat(),
            "created_at_ts": int(now.timestamp()),
            "hits": 0,                              # retrieval counter for salience
            "last_hit_at": None,
            **(metadata or {}),
        }
        await self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=point_id, vector=emb, payload=payload)],
        )
        return point_id

    async def add_batch(
        self,
        *,
        user_id: str,
        items: list[dict[str, Any]],
        batch_size: int = 64,
    ) -> int:
        """Batch ingest. Each item is {text, source, metadata?}.

        One embeddings call per `batch_size` items, one Qdrant upsert per
        batch. ~10–50x faster than calling `.add()` in a loop because the
        per-request RTT dominates for short chunks.
        """
        if not items:
            return 0
        now = datetime.now(timezone.utc)
        ts = int(now.timestamp())
        iso = now.isoformat()
        added = 0
        for start in range(0, len(items), batch_size):
            window = items[start : start + batch_size]
            texts = [w["text"] for w in window]
            embeddings = await self._embed.aembed_documents(texts)
            points: list[PointStruct] = []
            for w, emb in zip(window, embeddings, strict=True):
                meta = w.get("metadata") or {}
                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=emb,
                        payload={
                            "user_id": user_id,
                            "text": w["text"],
                            "source": w["source"],
                            "created_at": iso,
                            "created_at_ts": ts,
                            "hits": 0,
                            "last_hit_at": None,
                            **meta,
                        },
                    )
                )
            await self._client.upsert(collection_name=self._collection, points=points)
            added += len(points)
        return added

    async def search(self, user_id: str, query: str) -> list[dict]:
        emb = await self._embed.aembed_query(query)
        # qdrant-client >=1.14 removed `.search()` in favour of `.query_points()`.
        # The new API returns a `QueryResponse` whose `.points` is the
        # equivalent of the old `ScoredPoint[]`.
        resp = await self._client.query_points(
            collection_name=self._collection,
            query=emb,
            limit=self._top_k,
            query_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            with_payload=True,
        )
        results = resp.points
        out = [
            {"text": (r.payload or {}).get("text", ""), "score": r.score, "metadata": r.payload or {}, "_id": r.id}
            for r in results
        ]
        # Fire-and-forget salience bump.
        if out:
            try:
                await self._bump_hits([r["_id"] for r in out])
            except Exception as e:
                log.warning("qdrant.bump_hits_failed", error=str(e))
        for r in out:
            r.pop("_id", None)
        return out

    async def _bump_hits(self, point_ids: list[str]) -> None:
        if not point_ids:
            return
        pts = await self._client.retrieve(
            collection_name=self._collection,
            ids=point_ids,
            with_payload=True,
            with_vectors=False,
        )
        now = datetime.now(timezone.utc).isoformat()
        for p in pts:
            cur = int((p.payload or {}).get("hits", 0) or 0)
            await self._client.set_payload(
                collection_name=self._collection,
                payload={"hits": cur + 1, "last_hit_at": now},
                points=[p.id],
            )

    async def prune_stale(
        self,
        *,
        user_id: str | None = None,
        older_than_days: int = 7,
        max_hits: int = 0,
    ) -> int:
        """Delete points older than N days that have hits <= max_hits.
        Returns the number deleted (best-effort, may be approximate)."""
        cutoff = int(
            (datetime.now(timezone.utc) - timedelta(days=older_than_days)).timestamp()
        )
        must: list = [
            FieldCondition(key="created_at_ts", range=Range(lt=cutoff)),
            FieldCondition(key="hits", range=Range(lte=max_hits)),
        ]
        if user_id:
            must.insert(0, FieldCondition(key="user_id", match=MatchValue(value=user_id)))
        flt = Filter(must=must)

        # Count first (scroll), then delete by filter.
        scrolled, _ = await self._client.scroll(
            collection_name=self._collection,
            scroll_filter=flt,
            limit=10_000,
            with_payload=False,
            with_vectors=False,
        )
        count = len(scrolled)
        if count == 0:
            return 0
        await self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(filter=flt),
        )
        log.info("qdrant.pruned", count=count, user=user_id)
        return count

    async def close(self) -> None:
        await self._client.close()
