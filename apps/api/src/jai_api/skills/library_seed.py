"""Install the bundled `library/` skills into a user's `skills` table.

We mark each row's metadata with `library_key` so we can detect which
library skills the user already has and avoid duplicating on re-seed.
Updating an existing library skill (e.g. new bug fix in the bundled
script) replaces the SOURCE while preserving the user's run history.
"""

from __future__ import annotations

import structlog

from ..db import supabase_admin
from ..models.openrouter import openrouter_embeddings
from .library import LibrarySkill, load_library

log = structlog.get_logger()


async def seed_user_library(
    *,
    user_id: str,
    only_keys: list[str] | None = None,
) -> dict:
    """Install or update every library skill for `user_id`.

    Returns `{installed, updated, skipped, total}` so the UI can give the
    user a clear confirmation message.
    """
    skills = load_library()
    if only_keys:
        wanted = set(only_keys)
        skills = [s for s in skills if s.key in wanted]

    sb = supabase_admin()
    existing = (
        sb.table("skills")
        .select("id, source, metadata")
        .eq("user_id", user_id)
        .execute()
        .data
        or []
    )
    existing_by_key: dict[str, dict] = {}
    for row in existing:
        meta = row.get("metadata") or {}
        lk = meta.get("library_key")
        if lk:
            existing_by_key[lk] = row

    embed = openrouter_embeddings()

    installed = 0
    updated = 0
    skipped = 0

    for sk in skills:
        prior = existing_by_key.get(sk.key)
        if prior:
            # Source unchanged → nothing to do.
            if (prior.get("source") or "") == sk.source.strip():
                skipped += 1
                continue
            # Refresh source + metadata, recompute embedding.
            [emb] = await embed.aembed_documents([f"{sk.title}\n{sk.description}"])
            sb.table("skills").update(
                {
                    "title": sk.title,
                    "description": sk.description,
                    "description_emb": emb,
                    "language": sk.language,
                    "source": sk.source.strip(),
                    "required_credentials": sk.uses_credentials,
                    "required_tools": sk.required_tools,
                    "metadata": {
                        **(prior.get("metadata") or {}),
                        "library_key": sk.key,
                        "source_of_truth": "library",
                    },
                    "is_active": True,
                }
            ).eq("id", prior["id"]).eq("user_id", user_id).execute()
            updated += 1
            continue

        # Brand new for this user.
        [emb] = await embed.aembed_documents([f"{sk.title}\n{sk.description}"])
        sb.table("skills").insert(
            {
                "user_id": user_id,
                "title": sk.title,
                "description": sk.description,
                "description_emb": emb,
                "language": sk.language,
                "source": sk.source.strip(),
                "required_credentials": sk.uses_credentials,
                "required_tools": sk.required_tools,
                "metadata": {
                    "library_key": sk.key,
                    "source_of_truth": "library",
                },
                "is_active": True,
            }
        ).execute()
        installed += 1

    log.info(
        "library.seeded",
        user_id=user_id,
        installed=installed,
        updated=updated,
        skipped=skipped,
        total=len(skills),
    )
    return {
        "installed": installed,
        "updated": updated,
        "skipped": skipped,
        "total": len(skills),
    }
