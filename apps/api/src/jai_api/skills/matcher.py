"""Find an existing skill whose description matches the user's intent."""

from __future__ import annotations

import structlog

from ..db import supabase_admin
from ..models.openrouter import openrouter_embeddings

log = structlog.get_logger()


async def match(
    *,
    user_id: str,
    intent: str,
    threshold: float = 0.82,
    limit: int = 3,
) -> list[dict]:
    """Return ordered matches with cosine `similarity` field."""
    embed = openrouter_embeddings()
    [emb] = await embed.aembed_documents([intent])
    sb = supabase_admin()
    try:
        res = sb.rpc(
            "match_skills",
            {
                "query_embedding": emb,
                "match_user_id": user_id,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return res.data or []
    except Exception as e:
        log.warning("skill.match.failed", error=str(e))
        return []
