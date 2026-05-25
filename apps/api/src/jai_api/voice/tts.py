"""Text-to-speech via self-hosted Kokoro (OpenAI-compatible).

Kokoro-FastAPI exposes an OpenAI-compatible `/v1/audio/speech` endpoint, so
we just POST to it. Streams MP3/Opus back, which we forward over WebSocket
to the PWA.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import structlog

from ..config import Settings, get_settings

log = structlog.get_logger()


class TTS:
    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self._base = s.kokoro_tts_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))

    async def stream(
        self,
        text: str,
        *,
        voice: str = "af_bella",
        fmt: str = "mp3",
    ) -> AsyncIterator[bytes]:
        url = f"{self._base}/v1/audio/speech"
        payload = {
            "model": "kokoro",
            "input": text,
            "voice": voice,
            "response_format": fmt,
            "stream": True,
        }
        async with self._client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk

    async def synth(self, text: str, *, voice: str = "af_bella", fmt: str = "mp3") -> bytes:
        out = bytearray()
        async for chunk in self.stream(text, voice=voice, fmt=fmt):
            out.extend(chunk)
        return bytes(out)

    async def close(self) -> None:
        await self._client.aclose()
