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
    threshold: float = 0.65,
    limit: int = 5,
) -> list[dict]:
    """Return ordered matches with cosine `similarity` field.

    Threshold lowered from 0.72 to 0.65 because the library skill
    descriptions and natural user phrasings often diverge by enough
    embedding distance that 0.72 was leaving good matches on the floor
    and forcing the builder to regenerate the same skill repeatedly.
    """
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
        rows = res.data or []
    except Exception as e:
        log.warning("skill.match.failed", error=str(e))
        return []

    # Prefer library skills when similarity is close — they're hand-
    # tuned and faster than a regenerated one-off. Within 0.04 of the
    # top score, a library skill beats a user-generated duplicate.
    if rows:
        top_sim = rows[0].get("similarity") or 0.0
        for r in rows:
            if (
                (r.get("similarity") or 0.0) >= top_sim - 0.04
                and (r.get("metadata") or {}).get("library_key")
            ):
                rows = [r] + [x for x in rows if x is not r]
                break
    return rows


async def match_for_dedup(
    *,
    user_id: str,
    title: str,
    description: str,
    threshold: float = 0.82,
) -> dict | None:
    """Stronger-threshold match used *before* inserting a new skill.

    If the about-to-be-saved skill is very close to one we already have,
    return the existing row so the runner can re-activate it instead of
    creating a duplicate. The dedup threshold is intentionally tight
    (0.82) — we'd rather over-create than over-merge two distinct skills
    that happen to be related.
    """
    embed = openrouter_embeddings()
    [emb] = await embed.aembed_documents([f"{title}\n{description}"])
    sb = supabase_admin()
    try:
        # Search ALL skills (active + inactive) — if a near-twin was
        # archived earlier, prefer reviving it over creating a 27th
        # "Read Recent Emails".
        res = sb.rpc(
            "match_skills_for_dedup",
            {
                "query_embedding": emb,
                "match_user_id": user_id,
                "match_threshold": threshold,
                "match_count": 3,
            },
        ).execute()
    except Exception as e:
        log.warning("skill.dedup.failed", error=str(e))
        return None
    rows = res.data or []
    if not rows:
        return None
    # Prefer the library skill on tie.
    for r in rows:
        if (r.get("metadata") or {}).get("library_key"):
            return r
    return rows[0]
