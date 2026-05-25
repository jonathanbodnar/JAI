"""Voice REST endpoints (transcribe-only; live mode uses /chat/ws)."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from ..auth import CurrentUserDep
from ..voice.stt import STT

router = APIRouter()


@router.post("/transcribe")
async def transcribe(
    user: CurrentUserDep,
    file: UploadFile = File(...),
) -> dict:
    audio = await file.read()
    stt = STT()
    text = await stt.transcribe(audio, mime=file.content_type or "audio/webm")
    return {"text": text}
