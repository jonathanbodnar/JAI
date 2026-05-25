"""Context ingest — drag/drop PDFs, DOCX, text, or ChatGPT exports.

Flow (now async to dodge Railway/Cloudflare's ~100s HTTP timeout):

  1. HTTP handler parses every uploaded file synchronously (cheap — just
     PDF/DOCX text extraction, no network).
  2. For each file we insert a `documents` row in `processing` state and
     return immediately. The frontend already subscribes to that table via
     Supabase Realtime, so rows appear as 'processing' instantly and flip
     to 'complete' (or 'failed') when the background task finishes.
  3. The background task batches embeddings (~64 chunks per OpenRouter call),
     upserts them to Qdrant in one go per batch, and finally extracts identity
     facts to Mem0.
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
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
MAX_TOTAL_CHUNKS = 5000          # per-request safety cap (was 2000 — now async)
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200
MAX_GPT_CONVOS = 1000
EMBED_BATCH = 64                 # chunks per embedding API call


# --- text extraction -----------------------------------------------------


def _extract_pdf(blob: bytes) -> str:
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


def _extract_docx(blob: bytes) -> str:
    try:
        from docx import Document
    except ImportError:
        raise HTTPException(500, "python-docx not installed on the server")
    try:
        doc = Document(io.BytesIO(blob))
    except Exception as e:
        log.warning("docx.read_failed", error=str(e))
        return ""
    parts: list[str] = []
    for p in doc.paragraphs:
        if p.text and p.text.strip():
            parts.append(p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def _extract_chatgpt_conversations(data: Any) -> list[dict[str, Any]]:
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
        out.append({"title": title, "created": created, "body": "\n\n".join(user_msgs)})
    return out


def _extract_from_zip(blob: bytes) -> tuple[str, list[dict[str, Any]]]:
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
                elif name.endswith(".docx"):
                    try:
                        plain.append(_extract_docx(z.read(info.filename)))
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


# --- API models ----------------------------------------------------------


class IngestStub(BaseModel):
    """What we return synchronously — one entry per accepted file."""
    document_id: str
    filename: str
    status: str           # 'processing' | 'failed'
    error: str | None = None


class IngestResponse(BaseModel):
    accepted: list[IngestStub]
    skipped: list[str] = []


class DocumentRow(BaseModel):
    id: str
    filename: str
    size_bytes: int | None = None
    content_type: str | None = None
    kind: str
    status: str = "complete"
    chunks_count: int
    conversations_count: int
    facts_count: int
    metadata: dict[str, Any] | None = None
    error: str | None = None
    created_at: str


class SearchHit(BaseModel):
    text: str
    score: float
    source: str | None = None
    filename: str | None = None
    title: str | None = None


class SearchIn(BaseModel):
    q: str
    limit: int | None = None


# --- background worker ---------------------------------------------------


async def _process_one(
    *,
    user_id: str,
    doc_id: str,
    filename: str,
    plain_text: str,
    gpt_convos: list[dict[str, Any]],
) -> None:
    """Embed → Qdrant → Mem0. Updates the documents row with final counts."""
    sb = supabase_admin()
    qd = JaiQdrant()
    mem = JaiMem0()

    chunks_count = 0
    conv_count = 0
    facts_count = 0

    try:
        await qd.ensure_collection()

        # --- ChatGPT conversations -----------------------------------
        if gpt_convos:
            items: list[dict[str, Any]] = []
            for c in gpt_convos:
                for chunk in _chunk(c["body"]):
                    items.append(
                        {
                            "text": chunk,
                            "source": "chatgpt_export",
                            "metadata": {
                                "title": c["title"],
                                "created": c.get("created"),
                                "kind": "chat_history",
                                "filename": filename,
                            },
                        }
                    )
                    if len(items) >= MAX_TOTAL_CHUNKS:
                        break
                conv_count += 1
                if len(items) >= MAX_TOTAL_CHUNKS:
                    break
            if items:
                chunks_count += await qd.add_batch(
                    user_id=user_id, items=items, batch_size=EMBED_BATCH
                )

        # --- plain text ----------------------------------------------
        if plain_text.strip():
            items = [
                {
                    "text": ch,
                    "source": f"upload:{filename}",
                    "metadata": {"kind": "document", "filename": filename},
                }
                for ch in _chunk(plain_text)
            ][: max(0, MAX_TOTAL_CHUNKS - chunks_count)]
            if items:
                chunks_count += await qd.add_batch(
                    user_id=user_id, items=items, batch_size=EMBED_BATCH
                )

            # Fact extraction once per file
            facts = await _extract_facts(plain_text)
            if facts:
                try:
                    msgs = [{"role": "user", "content": f"Fact about me: {x}"} for x in facts]
                    await mem.add(user_id, msgs, metadata={"source": f"upload:{filename}"})
                    facts_count = len(facts)
                except Exception as e:
                    log.warning("ingest.mem0_add_failed", error=str(e))

        sb.table("documents").update(
            {
                "status": "complete",
                "chunks_count": chunks_count,
                "conversations_count": conv_count,
                "facts_count": facts_count,
            }
        ).eq("id", doc_id).eq("user_id", user_id).execute()

        # Mark onboarded after first successful ingest
        try:
            sb.table("users").update({"metadata": {"onboarded": True}}).eq(
                "id", user_id
            ).execute()
        except Exception:
            pass

        await audit_write(
            user_id=user_id,
            actor="context",
            action="context.ingest.complete",
            payload={
                "document_id": doc_id,
                "filename": filename,
                "chunks": chunks_count,
                "conversations": conv_count,
                "facts": facts_count,
            },
        )
    except Exception as e:
        log.exception("ingest.background_failed", document_id=doc_id, filename=filename)
        try:
            sb.table("documents").update(
                {
                    "status": "failed",
                    "error": str(e)[:500],
                    "chunks_count": chunks_count,
                    "conversations_count": conv_count,
                    "facts_count": facts_count,
                }
            ).eq("id", doc_id).eq("user_id", user_id).execute()
        except Exception:
            pass


# --- routes --------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    user: CurrentUserDep,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> IngestResponse:
    if not files:
        raise HTTPException(400, "no files uploaded")

    sb = supabase_admin()
    accepted: list[IngestStub] = []
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

        lower = name.lower()
        try:
            if ctype == "application/pdf" or lower.endswith(".pdf"):
                plain_text = _extract_pdf(blob)
            elif (
                ctype
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                or lower.endswith(".docx")
            ):
                plain_text = _extract_docx(blob)
            elif ctype == "application/zip" or lower.endswith(".zip"):
                plain_text, gpt_convos = _extract_from_zip(blob)
            elif ctype == "application/json" or lower.endswith(".json"):
                data = json.loads(blob.decode("utf-8"))
                gpt_convos = _extract_chatgpt_conversations(data)
                if not gpt_convos:
                    plain_text = blob.decode("utf-8", errors="ignore")
            elif ctype.startswith("text/") or lower.endswith((".txt", ".md")):
                plain_text = blob.decode("utf-8", errors="ignore")
            else:
                skipped.append(f"{name} (unsupported type {ctype or '?'})")
                continue
        except Exception as e:
            skipped.append(f"{name} ({type(e).__name__}: {e})")
            continue

        if not plain_text.strip() and not gpt_convos:
            skipped.append(f"{name} (no extractable text)")
            continue

        kind = "chatgpt_export" if gpt_convos else "document"

        # Insert the row immediately so the user sees it in the UI right away.
        try:
            res = (
                sb.table("documents")
                .insert(
                    {
                        "user_id": user.user_id,
                        "filename": name,
                        "size_bytes": len(blob),
                        "content_type": ctype or None,
                        "kind": kind,
                        "status": "processing",
                        "chunks_count": 0,
                        "conversations_count": 0,
                        "facts_count": 0,
                    }
                )
                .execute()
            )
            doc_id = res.data[0]["id"]
        except Exception as e:
            skipped.append(f"{name} (db insert: {e})")
            continue

        # Hand the heavy work to FastAPI's background scheduler.
        background.add_task(
            _process_one,
            user_id=user.user_id,
            doc_id=doc_id,
            filename=name,
            plain_text=plain_text,
            gpt_convos=gpt_convos,
        )

        accepted.append(
            IngestStub(document_id=doc_id, filename=name, status="processing")
        )

    return IngestResponse(accepted=accepted, skipped=skipped)


@router.get("/documents", response_model=list[DocumentRow])
async def list_documents(user: CurrentUserDep, limit: int = 200) -> list[dict[str, Any]]:
    sb = supabase_admin()
    res = (
        sb.table("documents")
        .select("*")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
        .limit(min(max(limit, 1), 500))
        .execute()
    )
    return res.data or []


@router.delete("/documents/{doc_id}")
async def delete_document(user: CurrentUserDep, doc_id: str) -> dict[str, Any]:
    sb = supabase_admin()
    sb.table("documents").delete().eq("user_id", user.user_id).eq("id", doc_id).execute()
    return {"ok": True}


@router.post("/search", response_model=list[SearchHit])
async def search(user: CurrentUserDep, body: SearchIn) -> list[dict[str, Any]]:
    q = (body.q or "").strip()
    if not q:
        raise HTTPException(400, "missing query")
    qd = JaiQdrant()
    try:
        await qd.ensure_collection()
        hits = await qd.search(user.user_id, q)
    except Exception as e:
        log.warning("context.search_failed", error=str(e))
        raise HTTPException(500, f"search failed: {e}") from e

    limit = min(max(body.limit or 20, 1), 50)
    out: list[dict[str, Any]] = []
    for h in hits[:limit]:
        meta = h.get("metadata") or {}
        out.append(
            {
                "text": h.get("text", ""),
                "score": float(h.get("score", 0.0)),
                "source": meta.get("source"),
                "filename": meta.get("filename"),
                "title": meta.get("title"),
            }
        )
    return out


# Quiet down a lint complaint about an unused import only relevant once we
# extend the worker with explicit concurrency primitives.
_ = asyncio
