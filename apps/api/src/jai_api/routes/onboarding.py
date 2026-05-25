"""First-run onboarding: capture identity facts and seed Mem0/Qdrant/users."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..auth import CurrentUserDep
from ..audit import write as audit_write
from ..db import supabase_admin
from ..memory.mem0 import JaiMem0
from ..memory.qdrant import JaiQdrant

router = APIRouter()


class OnboardIn(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    facts: list[str] = []                         # free-form sentences (optional)
    primary_focus: str | None = None              # e.g. "shipping JAI to App Store"
    voice_preference: str | None = None           # e.g. "concise, direct, no fluff"
    relationships: list[str] | None = None        # e.g. ["co-founder Alice"]
    bio: str | None = None                        # single free-text bio
    skip: bool = False                            # mark onboarded with no inputs


@router.get("/status")
async def status(user: CurrentUserDep) -> dict[str, Any]:
    sb = supabase_admin()
    res = sb.table("users").select("metadata,display_name,timezone").eq("id", user.user_id).execute()
    if not res.data:
        return {"completed": False}
    row = res.data[0]
    meta = (row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {}
    return {
        "completed": bool(meta.get("onboarded")),
        "display_name": row.get("display_name"),
        "timezone": row.get("timezone"),
    }


@router.post("")
async def complete(user: CurrentUserDep, body: OnboardIn | None = None) -> dict[str, Any]:
    body = body or OnboardIn()
    sb = supabase_admin()

    user_patch: dict[str, Any] = {"metadata": {"onboarded": True}}
    if body.display_name:
        user_patch["display_name"] = body.display_name
    if body.timezone:
        user_patch["timezone"] = body.timezone
    sb.table("users").update(user_patch).eq("id", user.user_id).execute()

    mem = JaiMem0()
    messages = [{"role": "user", "content": f"Fact about me: {f}"} for f in body.facts if f.strip()]
    if body.bio and body.bio.strip():
        messages.append({"role": "user", "content": f"About me: {body.bio.strip()}"})
    if body.primary_focus:
        messages.append({"role": "user", "content": f"My current primary focus is: {body.primary_focus}"})
    if body.voice_preference:
        messages.append({"role": "user", "content": f"Talk to me like this: {body.voice_preference}"})
    for rel in body.relationships or []:
        if rel.strip():
            messages.append({"role": "user", "content": f"Key relationship: {rel}"})
    if messages:
        try:
            await mem.add(user.user_id, messages, metadata={"source": "onboarding"})
        except Exception:
            pass  # mem0 optional in skip-only path

    qd = JaiQdrant()
    try:
        await qd.ensure_collection()
        for f in body.facts:
            if f.strip():
                await qd.add(
                    user_id=user.user_id,
                    text=f.strip(),
                    source="onboarding",
                    metadata={"kind": "identity_fact"},
                )
        if body.bio and body.bio.strip():
            await qd.add(
                user_id=user.user_id,
                text=body.bio.strip(),
                source="onboarding",
                metadata={"kind": "bio"},
            )
    except Exception:
        pass  # qdrant optional

    await audit_write(
        user_id=user.user_id,
        actor="onboarding",
        action="onboarding.complete",
        payload={"fact_count": len(body.facts), "skip": body.skip, "had_bio": bool(body.bio)},
    )

    return {"ok": True, "facts_saved": len(body.facts)}
