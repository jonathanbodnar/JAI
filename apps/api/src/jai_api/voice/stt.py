"""Speech-to-text via Groq Whisper Large v3 Turbo.

Groq is currently the fastest hosted Whisper (~real-time at 1/100th cost of
OpenAI's hosted version). Swap to local whisper.cpp by changing this file only.
"""

from __future__ import annotations

import io

import structlog
from groq import AsyncGroq

from ..config import Settings, get_settings

log = structlog.get_logger()


class STT:
    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        if not s.groq_api_key:
            log.warning("stt.disabled", reason="no groq key")
            self._client = None
            return
        self._client = AsyncGroq(api_key=s.groq_api_key)

    async def transcribe(self, audio_bytes: bytes, *, mime: str = "audio/webm") -> str:
        if not self._client:
            raise RuntimeError("STT not configured (set GROQ_API_KEY)")
        # Groq inspects both the filename extension AND the bytes — wrong
        # extension can flip a valid file into a 400. Match extension to mime.
        ext = {
            "audio/webm": "webm",
            "audio/ogg": "ogg",
            "audio/mp4": "mp4",
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
        }.get(mime, "webm")
        file_obj = (f"audio.{ext}", io.BytesIO(audio_bytes), mime)
        try:
            res = await self._client.audio.transcriptions.create(
                file=file_obj,
                model="whisper-large-v3-turbo",
                response_format="text",
                temperature=0,
            )
        except Exception as e:
            log.warning(
                "stt.api_error",
                error=str(e),
                bytes=len(audio_bytes),
                mime=mime,
                head=audio_bytes[:8].hex(),
            )
            raise
        return res if isinstance(res, str) else getattr(res, "text", str(res))
