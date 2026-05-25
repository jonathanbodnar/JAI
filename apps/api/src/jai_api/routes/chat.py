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
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from ..auth import CurrentUser, get_current_user
from ..db import supabase_admin
from ..voice.stt import STT
from ..voice.tts import TTS

log = structlog.get_logger()
router = APIRouter()


def _ws_user(token: str | None = Query(default=None)) -> CurrentUser:
    return get_current_user(authorization=f"Bearer {token}" if token else None)


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
                if audio_buffer.tell() == 0:
                    await ws.send_json({"type": "error", "message": "no audio captured"})
                    continue
                try:
                    text = await stt.transcribe(audio_buffer.getvalue())
                except Exception as e:
                    await ws.send_json({"type": "error", "message": f"stt failed: {e}"})
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


async def _run_turn(ws, graph, user, conv_id: str, text: str, tts: TTS, sb) -> None:
    config = {"configurable": {"thread_id": user.user_id}}
    state_input = {
        "user_id": user.user_id,
        "conversation_id": conv_id,
        "input_text": text,
    }

    # Persist user message first (best-effort).
    if sb:
        try:
            sb.table("messages").insert({
                "conversation_id": conv_id,
                "user_id": user.user_id,
                "role": "user",
                "content": text,
            }).execute()
        except Exception as e:
            log.warning("messages.user.insert_failed", error=str(e))

    final_text = ""
    role_used: str | None = None
    try:
        result = await graph.app.ainvoke(state_input, config=config)
        final_text = result.get("final_text") or "(no response)"
        role_used = result.get("role_used")
    except Exception as e:
        log.exception("graph.invoke.failed", error=str(e))
        await ws.send_json({"type": "error", "message": f"graph failed: {e}"})
        return

    await ws.send_json({
        "type": "assistant_final",
        "text": final_text,
        "role_used": role_used,
    })

    if sb:
        try:
            sb.table("messages").insert({
                "conversation_id": conv_id,
                "user_id": user.user_id,
                "role": "assistant",
                "content": final_text,
                "metadata": {"role_used": role_used} if role_used else {},
            }).execute()
        except Exception as e:
            log.warning("messages.assistant.insert_failed", error=str(e))

    # Stream TTS audio back (best-effort).
    try:
        async for chunk in tts.stream(final_text):
            await ws.send_json({
                "type": "audio_chunk",
                "b64": base64.b64encode(chunk).decode("ascii"),
            })
        await ws.send_json({"type": "audio_done"})
    except Exception as e:
        log.warning("tts.failed", error=str(e))
        await ws.send_json({"type": "audio_done", "skipped": True})
