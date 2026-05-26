"""Chat WebSocket — the one living conversation.

Wire format (JSON each frame):
  client -> server
    {"type":"user_text", "text":"..."}
    {"type":"user_audio_done"}            # signal end of audio recording, follow with bytes
    (binary frame: webm/opus chunk)

  server -> client
    {"type":"assistant_delta", "text":"..."}      # partial text chunk
    {"type":"assistant_final", "text":"...", "role_used":"orchestrator"}
    {"type":"audio_chunk", "b64":"..."}            # mp3 frame
    {"type":"audio_done"}
    {"type":"error", "message":"..."}
"""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO

import structlog
from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect

from ..auth import CurrentUser, CurrentUserDep, get_current_user
from ..db import supabase_admin
from ..voice.stt import STT
from ..voice.tts import TTS

log = structlog.get_logger()
router = APIRouter()


def _ws_user(token: str | None = Query(default=None)) -> CurrentUser:
    return get_current_user(authorization=f"Bearer {token}" if token else None)


@router.get("/recent")
async def recent_messages(user: CurrentUserDep, limit: int = 100) -> dict:
    """Return the most recent messages from the user's primary conversation.

    Used by the web client to recover a mid-turn response that was persisted
    on the server while the WebSocket was disconnected (e.g. the user
    navigated away from /chat while the LLM was still drafting).
    """
    try:
        sb = supabase_admin()
    except Exception as e:
        log.warning("supabase.unavailable", error=str(e))
        return {"messages": []}
    try:
        conv_id = await _primary_conversation_id(sb, user.user_id)
        res = (
            sb.table("messages")
            .select("id,role,content,metadata,created_at")
            .eq("conversation_id", conv_id)
            .order("created_at", desc=True)
            .limit(max(1, min(limit, 500)))
            .execute()
        )
        rows = list(reversed(res.data or []))
        return {"messages": rows}
    except Exception as e:
        log.warning("chat.recent.failed", error=str(e))
        return {"messages": []}


@router.post("/reset")
async def reset_conversation(request: Request, user: CurrentUserDep) -> dict:
    """Wipe the LangGraph checkpoint for this user.

    The orchestrator's working window is keyed on `thread_id == user_id`,
    so when the user says "clear chat" we drop every checkpoint row tied
    to that thread. Otherwise the LLM keeps drafting replies based on
    stale history (e.g. asking for a Todoist token that no longer
    applies).
    """
    graph = request.app.state.graph
    pool = getattr(graph, "pool", None)
    if pool is None:
        # No checkpointer configured — nothing to clear.
        return {"ok": True, "cleared": 0, "note": "no checkpointer"}
    deleted = 0
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # AsyncPostgresSaver creates these three tables; clearing
                # them by thread_id resets the entire conversation memory.
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    try:
                        await cur.execute(
                            f"DELETE FROM {table} WHERE thread_id = %s",
                            (user.user_id,),
                        )
                        deleted += cur.rowcount or 0
                    except Exception as e:
                        log.warning("chat.reset.delete_failed", table=table, error=str(e))
            await conn.commit()
    except Exception as e:
        log.warning("chat.reset.failed", error=str(e))
        return {"ok": False, "cleared": deleted, "error": str(e)}

    # Also wipe the persisted message log so recovery doesn't resurrect the
    # cleared conversation on the next page load.
    try:
        sb = supabase_admin()
        conv_id = await _primary_conversation_id(sb, user.user_id)
        sb.table("messages").delete().eq("conversation_id", conv_id).execute()
    except Exception as e:
        log.warning("chat.reset.messages_delete_failed", error=str(e))

    log.info("chat.reset.done", user=user.user_id[:8], deleted=deleted)
    return {"ok": True, "cleared": deleted}


@router.websocket("/ws")
async def chat_ws(ws: WebSocket, user: CurrentUser = Depends(_ws_user)):
    await ws.accept()
    graph = ws.app.state.graph
    stt = STT()
    tts = TTS()
    sb = None
    try:
        sb = supabase_admin()
    except Exception as e:
        log.warning("supabase.unavailable", error=str(e))

    # Resolve (or create) the user's primary conversation. With Supabase service
    # role we bypass RLS and trust the auth gate above.
    conv_id = await _primary_conversation_id(sb, user.user_id) if sb else "dev"

    audio_buffer = BytesIO()
    expecting_audio = False

    try:
        while True:
            try:
                raw = await ws.receive()
            except WebSocketDisconnect:
                break

            if raw.get("type") == "websocket.disconnect":
                break

            if "bytes" in raw and raw["bytes"] is not None and expecting_audio:
                audio_buffer.write(raw["bytes"])
                continue

            if "text" not in raw or raw["text"] is None:
                continue

            try:
                import json
                msg = json.loads(raw["text"])
            except Exception:
                await ws.send_json({"type": "error", "message": "invalid frame"})
                continue

            mtype = msg.get("type")

            if mtype == "ping":
                # Keepalive from the client so Cloudflare / Railway don't
                # reap the socket as idle (~60s by default).
                try:
                    await ws.send_json({"type": "pong"})
                except Exception:
                    pass
                continue

            if mtype == "user_audio_start":
                audio_buffer = BytesIO()
                expecting_audio = True
                continue

            if mtype == "user_audio_done":
                expecting_audio = False
                audio = audio_buffer.getvalue()
                if not audio:
                    await ws.send_json({"type": "error", "message": "no audio captured"})
                    continue
                # Sniff container so Whisper / Groq STT gets the right hint.
                mime = _sniff_audio_mime(audio)
                try:
                    text = await stt.transcribe(audio, mime=mime)
                except Exception as e:
                    log.warning("stt.failed", error=str(e), bytes=len(audio), mime=mime)
                    await ws.send_json({"type": "error", "message": f"stt failed: {e}"})
                    continue
                if not (text or "").strip():
                    await ws.send_json({"type": "error", "message": "empty transcription — try again with a clearer / longer hold"})
                    continue
                await ws.send_json({"type": "user_transcript", "text": text})
                await _run_turn(ws, graph, user, conv_id, text, tts, sb)
                continue

            if mtype == "user_text":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                await _run_turn(ws, graph, user, conv_id, text, tts, sb)
                continue

            await ws.send_json({"type": "error", "message": f"unknown type {mtype}"})

    finally:
        await tts.close()
        try:
            await ws.close()
        except Exception:
            pass


def _summarize_delta(node_name: str, delta) -> str | None:
    """Produce a short user-friendly description of what a node did."""
    if not isinstance(delta, dict):
        return None
    try:
        if node_name == "retrieve":
            mem = delta.get("memory") or {}
            mem0 = len(mem.get("mem0") or [])
            qd = len(mem.get("qdrant") or [])
            gr = len(mem.get("graph") or [])
            bits: list[str] = []
            if mem0: bits.append(f"{mem0} identity facts")
            if qd: bits.append(f"{qd} embeddings")
            if gr: bits.append(f"{gr} graph nodes")
            return ", ".join(bits) or "No prior context found"
        if node_name == "fast_intent":
            if delta.get("final_text") and (delta.get("role_used", "") or "").startswith("builtin:"):
                return f"Handled by {delta.get('role_used')}"
            return None
        if node_name == "orchestrator":
            route = delta.get("route")
            return f"Route → {route}" if route else None
        if node_name == "respond":
            return "Voice: Kimi K2.6"
        if node_name == "reflect":
            return "Voice: Kimi K2.6"
        if node_name == "strategize":
            return "Voice: DeepSeek V4 Pro"
        if node_name == "skill":
            sk = delta.get("skill_name") or delta.get("skill_id")
            return f"Ran {sk}" if sk else None
        if node_name == "tool":
            t = delta.get("tool_name")
            return f"Called {t}" if t else None
        if node_name == "persist":
            wrote = delta.get("persisted") or {}
            if wrote:
                bits = [f"{k}: {v}" for k, v in wrote.items() if v]
                return ", ".join(bits) or None
            return None
    except Exception:
        return None
    return None


def _sniff_audio_mime(buf: bytes) -> str:
    """Best-effort container detection from the first few bytes.

    MediaRecorder defaults to webm on Chrome / Firefox; Safari / iOS use mp4
    (with an `ftyp` box at byte 4). We can't trust the client's mime string
    once we've round-tripped through a binary WebSocket frame.
    """
    head = buf[:16]
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "audio/webm"
    if len(head) >= 8 and head[4:8] in (b"ftyp", b"moov", b"mdat"):
        return "audio/mp4"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"ID3") or head[:2] == b"\xff\xfb":
        return "audio/mpeg"
    if head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WAVE":
        return "audio/wav"
    return "audio/webm"


async def _primary_conversation_id(sb, user_id: str) -> str:
    res = (
        sb.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("kind", "primary")
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if rows:
        return rows[0]["id"]
    ins = (
        sb.table("conversations")
        .insert({"user_id": user_id, "kind": "primary", "title": "JAI"})
        .execute()
    )
    return ins.data[0]["id"]


_STEP_LABELS = {
    "ingest": ("Reading your message", "Parsing intent & context"),
    "fast_intent": ("Checking quick actions", "Matching against built-in patterns"),
    "retrieve": ("Recalling memory", "Pulling identity facts, embeddings, graph"),
    "orchestrator": ("Routing", "Picking which model handles this turn"),
    "respond": ("Drafting reply", "Kimi K2.6 — the JAI voice"),
    "reflect": ("Reflecting", "Kimi K2.6 — pattern matching across your history"),
    "strategize": ("Strategizing", "DeepSeek V4 Pro — option trade-offs"),
    "tool": ("Calling a tool", "Routing to a connected integration"),
    "skill": ("Running a skill", "Executing sandboxed code"),
    "persist": ("Saving to memory", "Selectively writing durable facts"),
}


async def _run_turn(ws, graph, user, conv_id: str, text: str, tts: TTS, sb) -> None:
    config = {"configurable": {"thread_id": user.user_id}}
    state_input = {
        "user_id": user.user_id,
        "conversation_id": conv_id,
        "input_text": text,
    }

    # Fire-and-forget the user-message insert so it never blocks the LLM.
    if sb:
        async def _insert_user():
            try:
                await asyncio.to_thread(
                    lambda: sb.table("messages").insert({
                        "conversation_id": conv_id,
                        "user_id": user.user_id,
                        "role": "user",
                        "content": text,
                    }).execute()
                )
            except Exception as e:
                log.warning("messages.user.insert_failed", error=str(e))
        asyncio.create_task(_insert_user())

    final_text = ""
    role_used: str | None = None
    try:
        # Stream node-level updates so the client can render "thinking steps"
        # like Cursor. We still need the final state, so we accumulate it.
        accumulated: dict = {}
        async for update in graph.app.astream(state_input, config=config, stream_mode="updates"):
            # update is {node_name: state_delta}
            for node_name, delta in update.items():
                label, detail = _STEP_LABELS.get(node_name, (node_name.replace("_", " ").title(), None))
                extra = _summarize_delta(node_name, delta)
                try:
                    await ws.send_json({
                        "type": "step",
                        "node": node_name,
                        "label": label,
                        "detail": extra or detail,
                    })
                except Exception:
                    # Client may have disconnected — don't abort the turn.
                    pass
                if isinstance(delta, dict):
                    accumulated.update(delta)
        final_text = (accumulated.get("final_text") or "").strip() or "(no response)"
        role_used = accumulated.get("role_used")
    except Exception as e:
        log.exception("graph.invoke.failed", error=str(e))
        try:
            await ws.send_json({"type": "error", "message": f"graph failed: {e}"})
        except Exception:
            pass
        # Persist the error so the user sees it on reload instead of a blank
        # response (they may have switched away during streaming).
        if sb and final_text == "":
            final_text = f"Something went wrong: {str(e)[:200]}"
        if not final_text:
            return

    # Persist the assistant turn FIRST — before sending — so a mid-turn
    # disconnect can't lose the response. The user reloads and sees it.
    if sb:
        async def _insert_assistant():
            try:
                await asyncio.to_thread(
                    lambda: sb.table("messages").insert({
                        "conversation_id": conv_id,
                        "user_id": user.user_id,
                        "role": "assistant",
                        "content": final_text,
                        "metadata": {"role_used": role_used} if role_used else {},
                    }).execute()
                )
            except Exception as e:
                log.warning("messages.assistant.insert_failed", error=str(e))
        asyncio.create_task(_insert_assistant())

    # Send the user-visible text. If the WS is dead, persistence above
    # already captured the response so the next reload renders it.
    try:
        await ws.send_json({
            "type": "assistant_final",
            "text": final_text,
            "role_used": role_used,
        })
    except Exception:
        log.info("chat.assistant_final.ws_closed", conv=conv_id)
        return

    # Stream TTS audio back (best-effort). Wrap in try/except so a failed
    # Kokoro server never breaks the chat.
    try:
        async for chunk in tts.stream(final_text):
            await ws.send_json({
                "type": "audio_chunk",
                "b64": base64.b64encode(chunk).decode("ascii"),
            })
        await ws.send_json({"type": "audio_done"})
    except Exception as e:
        log.warning("tts.failed", error=str(e))
        try:
            await ws.send_json({"type": "audio_done", "skipped": True})
        except Exception:
            pass
