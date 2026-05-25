"""Shared status types."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    service: str                                                   # canonical id
    display_name: str
    category: Literal["llm", "voice", "memory", "infra", "platform", "billing"]
    healthy: bool = True
    configured: bool = True
    dashboard_url: str | None = None

    # quantitative — any subset may be present
    balance_usd: float | None = None                                # remaining prepaid
    used_usd: float | None = None                                   # usage this period
    limit: dict[str, Any] | None = None                             # plan limit, e.g. {"storage_gb": 1}
    usage: dict[str, Any] | None = None                             # current usage, e.g. {"points": 12_345}
    period_end: str | None = None                                   # next renewal ISO date

    notes: str | None = None
    error: str | None = None
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
