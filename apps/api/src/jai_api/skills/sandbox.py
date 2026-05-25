"""HTTP client for the Cloudflare Sandbox worker."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from ..config import get_settings

log = structlog.get_logger()


class SandboxClient:
    def __init__(self) -> None:
        s = get_settings()
        self._base = (s.sandbox_base_url or "").rstrip("/")
        self._token = s.sandbox_auth_token if hasattr(s, "sandbox_auth_token") else ""
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(360.0, connect=10.0))

    @property
    def configured(self) -> bool:
        return bool(self._base)

    async def run(
        self,
        *,
        user_id: str,
        skill_id: str,
        language: str,
        source: str,
        env: dict[str, str] | None = None,
        timeout_ms: int = 300_000,
    ) -> dict[str, Any]:
        if not self.configured:
            return {
                "status": "error",
                "result": None,
                "stdout": "",
                "stderr": "sandbox not configured (set SANDBOX_BASE_URL)",
                "exit_code": -1,
                "duration_ms": 0,
            }
        headers = {"content-type": "application/json"}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        resp = await self._client.post(
            f"{self._base}/run",
            json={
                "user_id": user_id,
                "skill_id": skill_id,
                "language": language,
                "source": source,
                "env": env or {},
                "timeout_ms": timeout_ms,
            },
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def destroy(self, user_id: str) -> None:
        if not self.configured:
            return
        headers = {}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        await self._client.delete(f"{self._base}/sandbox/{user_id}", headers=headers)

    async def close(self) -> None:
        await self._client.aclose()
