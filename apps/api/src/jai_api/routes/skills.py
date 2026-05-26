"""Skills CRUD + context graph endpoint + credentials + manual run."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..auth import CurrentUserDep
from ..db import supabase_admin
from ..skills import registry
from ..skills.library import load_library
from ..skills.library_seed import seed_user_library
from ..skills.runner import run_intent

router = APIRouter()


@router.get("/library")
async def list_library_skills() -> list[dict[str, Any]]:
    """Return the curated library catalogue (the same for every user)."""
    return [
        {
            "key": s.key,
            "title": s.title,
            "description": s.description,
            "language": s.language,
            "required_tools": s.required_tools,
        }
        for s in load_library()
    ]


class SeedLibraryIn(BaseModel):
    only: list[str] | None = None  # optional subset of library keys


@router.post("/library/seed")
async def install_library(user: CurrentUserDep, body: SeedLibraryIn | None = None) -> dict:
    """Install (or update) the bundled library skills for the current user."""
    return await seed_user_library(
        user_id=user.user_id,
        only_keys=(body.only if body and body.only else None),
    )


@router.get("")
async def list_skills(user: CurrentUserDep) -> list[dict[str, Any]]:
    sb = supabase_admin()
    res = (
        sb.table("skills")
        .select("id,title,description,language,required_credentials,run_count,last_run_at,last_run_status,is_active,created_at,updated_at")
        .eq("user_id", user.user_id)
        .eq("is_active", True)
        .order("updated_at", desc=True)
        .execute()
    )
    return res.data or []


@router.get("/{skill_id}")
async def get_skill(user: CurrentUserDep, skill_id: str) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("skills")
        .select("*")
        .eq("user_id", user.user_id)
        .eq("id", skill_id)
        .single()
        .execute()
    )
    return res.data


@router.delete("/{skill_id}")
async def deactivate_skill(user: CurrentUserDep, skill_id: str) -> dict:
    sb = supabase_admin()
    sb.table("skills").update({"is_active": False}).eq("user_id", user.user_id).eq("id", skill_id).execute()
    return {"ok": True}


class RunBody(BaseModel):
    intent: str
    conversation_id: str | None = None


@router.post("/run")
async def run_skill_intent(user: CurrentUserDep, body: RunBody) -> dict:
    """Run an intent through the skill engine. Used by the Skills panel for ad-hoc execution."""
    outcome = await run_intent(
        user_id=user.user_id,
        conversation_id=body.conversation_id,
        intent=body.intent,
    )
    return {
        "final_text": outcome.final_text,
        "skill_id": outcome.skill_id,
        "needs_credentials": outcome.needs_credentials or [],
        "raw": outcome.raw,
    }


@router.get("/credentials/keys")
async def list_credential_keys(user: CurrentUserDep) -> list[str]:
    sb = supabase_admin()
    res = sb.table("skill_credentials").select("key").eq("user_id", user.user_id).execute()
    return [r["key"] for r in (res.data or [])]


class CredentialIn(BaseModel):
    key: str
    value: str
    metadata: dict[str, Any] | None = None


@router.post("/credentials")
async def set_credential(user: CurrentUserDep, body: CredentialIn) -> dict:
    if not body.key or "=" in body.key:
        raise HTTPException(400, "invalid key")
    await registry.set_credential(
        user_id=user.user_id,
        key=body.key,
        value=body.value,
        metadata=body.metadata,
    )
    return {"ok": True, "key": body.key}


@router.delete("/credentials/{key}")
async def delete_credential(user: CurrentUserDep, key: str) -> dict:
    sb = supabase_admin()
    sb.table("skill_credentials").delete().eq("user_id", user.user_id).eq("key", key).execute()
    return {"ok": True}


@router.get("/_context/graph")
async def context_graph(user: CurrentUserDep, request: Request) -> dict:
    """Return the user's Neo4j graph for the Context panel."""
    graph = request.app.state.graph
    return await graph.neo4j.graph_dump(user.user_id, limit=300)


# ============================================================================
# Marketplace — export/import skills as portable JSON
# ============================================================================

SKILL_EXPORT_VERSION = 1


@router.get("/{skill_id}/export")
async def export_skill(user: CurrentUserDep, skill_id: str) -> dict:
    """Export a single skill as portable JSON (no credentials, no run history)."""
    sk = await registry.get_skill(user_id=user.user_id, skill_id=skill_id)
    if not sk:
        raise HTTPException(404, "skill not found")
    return _to_export(sk)


@router.get("/_export/all")
async def export_all(user: CurrentUserDep) -> dict:
    sb = supabase_admin()
    res = (
        sb.table("skills")
        .select("*")
        .eq("user_id", user.user_id)
        .eq("is_active", True)
        .execute()
    )
    return {
        "version": SKILL_EXPORT_VERSION,
        "exported_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "skills": [_to_export(s) for s in (res.data or [])],
    }


class SkillImport(BaseModel):
    title: str
    description: str
    language: str
    source: str
    required_credentials: list[str] = []
    required_tools: list[str] = []
    inputs_schema: dict[str, Any] = {}


class ImportBody(BaseModel):
    skills: list[SkillImport]


@router.post("/_import")
async def import_skills(user: CurrentUserDep, body: ImportBody) -> dict:
    """Bulk import skills. Skips duplicates (same user + same title)."""
    sb = supabase_admin()
    existing = (
        sb.table("skills")
        .select("title")
        .eq("user_id", user.user_id)
        .eq("is_active", True)
        .execute()
    )
    have = {r["title"] for r in (existing.data or [])}
    saved: list[dict] = []
    skipped: list[str] = []
    for s in body.skills:
        if s.title in have:
            skipped.append(s.title)
            continue
        if s.language not in {"python", "typescript", "bash"}:
            skipped.append(s.title)
            continue
        try:
            row = await registry.save_skill(
                user_id=user.user_id,
                title=s.title,
                description=s.description,
                language=s.language,
                source=s.source,
                required_credentials=s.required_credentials,
                required_tools=s.required_tools,
                inputs_schema=s.inputs_schema,
            )
            saved.append({"id": row["id"], "title": row["title"]})
        except Exception as e:
            skipped.append(f"{s.title} ({e})")
    return {"saved": saved, "skipped": skipped}


def _to_export(s: dict) -> dict:
    return {
        "title": s.get("title"),
        "description": s.get("description"),
        "language": s.get("language"),
        "source": s.get("source"),
        "required_credentials": s.get("required_credentials") or [],
        "required_tools": s.get("required_tools") or [],
        "inputs_schema": s.get("inputs_schema") or {},
    }
