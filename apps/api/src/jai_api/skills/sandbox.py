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
        try:
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
        except httpx.RequestError as e:
            log.warning("sandbox.request_failed", error=str(e))
            return {
                "status": "error",
                "result": None,
                "stdout": "",
                "stderr": f"sandbox unreachable: {e}",
                "exit_code": -1,
                "duration_ms": 0,
            }

        # The worker now returns 200 with a structured error body even when
        # it crashes internally — but a stray non-2xx (e.g. 401, deploy in
        # flight) still needs graceful handling.
        if resp.status_code >= 400:
            body_preview = (resp.text or "")[:500]
            log.warning(
                "sandbox.http_error",
                status=resp.status_code,
                body=body_preview,
            )
            return {
                "status": "error",
                "result": None,
                "stdout": "",
                "stderr": f"sandbox HTTP {resp.status_code}: {body_preview}",
                "exit_code": resp.status_code,
                "duration_ms": 0,
            }
        try:
            return resp.json()
        except Exception as e:
            return {
                "status": "error",
                "result": None,
                "stdout": "",
                "stderr": f"sandbox returned non-json: {e}; body={resp.text[:300]}",
                "exit_code": -1,
                "duration_ms": 0,
            }

    async def destroy(self, user_id: str) -> None:
        if not self.configured:
            return
        headers = {}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        await self._client.delete(f"{self._base}/sandbox/{user_id}", headers=headers)

    async def close(self) -> None:
        await self._client.aclose()
