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
        file_obj = ("audio.webm", io.BytesIO(audio_bytes), mime)
        res = await self._client.audio.transcriptions.create(
            file=file_obj,
            model="whisper-large-v3-turbo",
            response_format="text",
            temperature=0,
        )
        # SDK returns either a Transcription object or raw text depending on format
        return res if isinstance(res, str) else getattr(res, "text", str(res))
