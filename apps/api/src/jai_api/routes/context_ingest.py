"""Context ingest — drag/drop PDFs, text, or ChatGPT exports.

Supported inputs:
- application/pdf            → extract text per page
- text/plain, text/markdown  → use as-is
- application/json           → ChatGPT export (`conversations.json`) detected
                               by shape; pull out user-authored content
- application/zip            → ChatGPT export zip; we look for conversations.json
                               inside

For each ingested file we:
  1. Chunk the text (~1200 chars, 200 overlap)
  2. Embed each chunk → Qdrant
  3. Pull 5-15 durable identity facts (best-effort, LLM-extracted) → Mem0
  4. Mark the user as onboarded so the wizard doesn't reappear

The endpoint streams nothing fancy — it returns once everything is ingested.
For very large drops (ChatGPT exports with thousands of conversations) we cap
the work per request and tell the caller how many items were processed.
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..auth import CurrentUserDep
from ..audit import write as audit_write
from ..db import supabase_admin
from ..memory.mem0 import JaiMem0
from ..memory.qdrant import JaiQdrant

log = structlog.get_logger()
router = APIRouter()


# --- limits --------------------------------------------------------------

MAX_FILE_MB = 25
MAX_TOTAL_CHUNKS = 2000          # per request, prevents runaway costs
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200
MAX_GPT_CONVOS = 500             # safety cap on a single ChatGPT export


# --- text extraction -----------------------------------------------------


def _extract_pdf(blob: bytes) -> str:
    """Pull text from a PDF, page by page. Falls back to empty if unparseable."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise HTTPException(500, "pypdf not installed on the server")

    try:
        reader = PdfReader(io.BytesIO(blob))
    except Exception as e:
        log.warning("pdf.read_failed", error=str(e))
        return ""

    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
            if txt.strip():
                pages.append(f"[page {i + 1}]\n{txt.strip()}")
        except Exception as e:
            log.warning("pdf.page_failed", page=i + 1, error=str(e))
    return "\n\n".join(pages)


def _extract_chatgpt_conversations(data: Any) -> list[dict[str, Any]]:
    """Parse OpenAI's ChatGPT data-export `conversations.json` format.

    The export is a JSON array; each conversation has a `mapping` dict whose
    nodes contain `message.author.role` ("user" / "assistant" / "system") and
    `message.content.parts`. We keep user-authored messages because those
    encode the human's preferences, beliefs, and history — assistant replies
    are noise for identity modeling.
    """
    if not isinstance(data, list):
        return []

    out: list[dict[str, Any]] = []
    for convo in data[:MAX_GPT_CONVOS]:
        if not isinstance(convo, dict):
            continue
        title = (convo.get("title") or "").strip() or "Untitled"
        created = convo.get("create_time")
        mapping = convo.get("mapping") or {}
        user_msgs: list[str] = []
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            msg = node.get("message") or {}
            author = (msg.get("author") or {}).get("role")
            if author != "user":
                continue
            parts = (msg.get("content") or {}).get("parts") or []
            for p in parts:
                if isinstance(p, str) and p.strip():
                    user_msgs.append(p.strip())
        if not user_msgs:
            continue
        body = "\n\n".join(user_msgs)
        out.append({"title": title, "created": created, "body": body})
    return out


def _extract_from_zip(blob: bytes) -> tuple[str, list[dict[str, Any]]]:
    """Returns (plain_text_combined, chatgpt_conversations)."""
    plain: list[str] = []
    convos: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for info in z.infolist():
                if info.is_dir() or info.file_size > MAX_FILE_MB * 1024 * 1024:
                    continue
                name = info.filename.lower()
                if name.endswith("conversations.json"):
                    try:
                        data = json.loads(z.read(info.filename).decode("utf-8"))
                        convos.extend(_extract_chatgpt_conversations(data))
                    except Exception as e:
                        log.warning("zip.gpt_parse_failed", file=info.filename, error=str(e))
                elif name.endswith((".txt", ".md")):
                    try:
                        plain.append(z.read(info.filename).decode("utf-8", errors="ignore"))
                    except Exception:
                        pass
                elif name.endswith(".pdf"):
                    try:
                        plain.append(_extract_pdf(z.read(info.filename)))
                    except Exception:
                        pass
    except zipfile.BadZipFile:
        return "", []
    return "\n\n".join(p for p in plain if p.strip()), convos


# --- chunking ------------------------------------------------------------


def _chunk(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# --- fact extraction -----------------------------------------------------


async def _extract_facts(text: str, max_facts: int = 12) -> list[str]:
    """Pull durable identity facts out of a blob (best-effort).

    Uses the orchestrator model with a tight prompt. Failures are non-fatal —
    we just return [] so the chunk-embedding path still runs.
    """
    if not text.strip():
        return []
    try:
        from ..config import get_settings
        from ..models.openrouter import openrouter_chat

        s = get_settings()
        llm = openrouter_chat(model=s.jai_model_orchestrator, settings=s, temperature=0.1)
        prompt = (
            "Extract up to "
            f"{max_facts} short, durable facts about the human from the text below. "
            "Focus on: identity, role, beliefs, preferences, recurring themes, "
            "relationships, goals, values. Skip transient tasks or one-off events. "
            "Return one fact per line, no numbering, no preamble.\n\n"
            "TEXT:\n"
            f"{text[:8000]}"
        )
        resp = await llm.ainvoke(prompt)
        raw = str(resp.content or "")
        facts = [
            line.strip().lstrip("-•* ").strip()
            for line in raw.splitlines()
            if line.strip() and len(line.strip()) > 5
        ]
        return facts[:max_facts]
    except Exception as e:
        log.warning("ingest.fact_extract_failed", error=str(e))
        return []


# --- main route ----------------------------------------------------------


class IngestSummary(BaseModel):
    files: int
    chunks_added: int
    facts_added: int
    conversations_added: int
    skipped: list[str] = []


@router.post("/ingest", response_model=IngestSummary)
async def ingest(
    user: CurrentUserDep,
    files: list[UploadFile] = File(...),
) -> IngestSummary:
    if not files:
        raise HTTPException(400, "no files uploaded")

    qd = JaiQdrant()
    await qd.ensure_collection()
    mem = JaiMem0()

    chunks_added = 0
    facts_added = 0
    convos_added = 0
    skipped: list[str] = []

    for f in files:
        name = f.filename or "unnamed"
        ctype = (f.content_type or "").lower()
        blob = await f.read()
        if len(blob) > MAX_FILE_MB * 1024 * 1024:
            skipped.append(f"{name} (>{MAX_FILE_MB}MB)")
            continue

        plain_text = ""
        gpt_convos: list[dict[str, Any]] = []

        # Route based on type / extension
        lower = name.lower()
        if ctype == "application/pdf" or lower.endswith(".pdf"):
            plain_text = _extract_pdf(blob)
        elif ctype == "application/zip" or lower.endswith(".zip"):
            plain_text, gpt_convos = _extract_from_zip(blob)
        elif ctype == "application/json" or lower.endswith(".json"):
            try:
                data = json.loads(blob.decode("utf-8"))
                gpt_convos = _extract_chatgpt_conversations(data)
                if not gpt_convos:
                    # plain JSON, dump as text
                    plain_text = blob.decode("utf-8", errors="ignore")
            except Exception:
                skipped.append(f"{name} (invalid JSON)")
                continue
        elif ctype.startswith("text/") or lower.endswith((".txt", ".md")):
            plain_text = blob.decode("utf-8", errors="ignore")
        else:
            skipped.append(f"{name} (unsupported type {ctype or '?'})")
            continue

        # --- index ChatGPT conversations ---------------------------------
        for c in gpt_convos:
            if chunks_added >= MAX_TOTAL_CHUNKS:
                break
            for chunk in _chunk(c["body"]):
                if chunks_added >= MAX_TOTAL_CHUNKS:
                    break
                try:
                    await qd.add(
                        user_id=user.user_id,
                        text=chunk,
                        source="chatgpt_export",
                        metadata={
                            "title": c["title"],
                            "created": c.get("created"),
                            "kind": "chat_history",
                        },
                    )
                    chunks_added += 1
                except Exception as e:
                    log.warning("ingest.qdrant_add_failed", error=str(e))
            convos_added += 1

        # --- index plain text (PDFs, .txt, .md) --------------------------
        if plain_text.strip():
            chunks = _chunk(plain_text)
            for chunk in chunks:
                if chunks_added >= MAX_TOTAL_CHUNKS:
                    break
                try:
                    await qd.add(
                        user_id=user.user_id,
                        text=chunk,
                        source=f"upload:{name}",
                        metadata={"kind": "document", "filename": name},
                    )
                    chunks_added += 1
                except Exception as e:
                    log.warning("ingest.qdrant_add_failed", error=str(e))

            # Fact extraction — runs once per file, not per chunk
            facts = await _extract_facts(plain_text)
            if facts:
                try:
                    msgs = [{"role": "user", "content": f"Fact about me: {x}"} for x in facts]
                    await mem.add(
                        user.user_id,
                        msgs,
                        metadata={"source": f"upload:{name}"},
                    )
                    facts_added += len(facts)
                except Exception as e:
                    log.warning("ingest.mem0_add_failed", error=str(e))

    # Mark onboarded as soon as anything was ingested
    if chunks_added > 0 or convos_added > 0:
        try:
            sb = supabase_admin()
            sb.table("users").update({"metadata": {"onboarded": True}}).eq(
                "id", user.user_id
            ).execute()
        except Exception as e:
            log.warning("ingest.onboarded_flag_failed", error=str(e))

    await audit_write(
        user_id=user.user_id,
        actor="context",
        action="context.ingest",
        payload={
            "files": len(files),
            "chunks": chunks_added,
            "facts": facts_added,
            "conversations": convos_added,
            "skipped": skipped,
        },
    )

    return IngestSummary(
        files=len(files) - len(skipped),
        chunks_added=chunks_added,
        facts_added=facts_added,
        conversations_added=convos_added,
        skipped=skipped,
    )
