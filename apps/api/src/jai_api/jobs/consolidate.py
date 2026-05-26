"""Nightly consolidation.

Runs once per day per user.

Steps:
  1. Pull all messages from the last 24h for the user's primary conversation.
  2. Ask Fast model for a 200-word "what mattered today" summary + 1–5 Mem0
     candidate facts.
  3. Write summary as a system-level message in the conversation, prefixed
     `[daily.summary]`.
  4. Push the candidate facts into Mem0.
  5. Run reflection pass (Kimi K2.6) over the last 30 days of summaries; if
     it surfaces something the user should see, append it as a `reflection`
     role message so it's visible on next open.
  6. Prune Qdrant entries > 7 days old whose salience was never bumped (i.e.
     never re-retrieved). Simple heuristic for v0.1; later: track retrieval
     hits explicitly in payload.
  7. Execute any due scheduled actions and store results as system messages.

The whole job is idempotent enough — calling twice in a day just produces a
second summary message.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_settings
from ..db import supabase_admin
from ..graph.prompts import REFLECTION_SYSTEM, SUMMARIZE_DAY_SYSTEM
from ..memory.mem0 import JaiMem0
from ..memory.qdrant import JaiQdrant
from ..models.registry import Role, chat_for

log = structlog.get_logger()


async def consolidate_for_user(user_id: str) -> dict:
    sb = supabase_admin()
    settings = get_settings()

    # 1. Pull conversation + last 24h messages.
    conv = (
        sb.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("kind", "primary")
        .limit(1)
        .execute()
    )
    if not conv.data:
        log.info("consolidate.skip", reason="no primary conversation", user=user_id)
        return {"ok": True, "skipped": True}
    conv_id = conv.data[0]["id"]

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    msgs = (
        sb.table("messages")
        .select("role,content,created_at")
        .eq("conversation_id", conv_id)
        .gte("created_at", since)
        .order("created_at")
        .execute()
    )
    if not msgs.data:
        log.info("consolidate.skip", reason="no activity in last 24h", user=user_id)
        return {"ok": True, "skipped": True}

    # 2. Summarize.
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in msgs.data)
    fast = chat_for(Role.FAST, temperature=0.3, streaming=False)
    summary_res = await fast.ainvoke([
        SystemMessage(content=SUMMARIZE_DAY_SYSTEM),
        HumanMessage(content=transcript[:60_000]),
    ])
    summary_raw = summary_res.content if isinstance(summary_res.content, str) else str(summary_res.content)
    summary, facts = _split_summary(summary_raw)

    # 3. Write summary into conversation.
    sb.table("messages").insert({
        "conversation_id": conv_id,
        "user_id": user_id,
        "role": "system",
        "content": f"[daily.summary] {summary}",
        "metadata": {"job": "consolidate", "fact_count": len(facts)},
    }).execute()

    # 4. Push facts to Mem0.
    mem0 = JaiMem0(settings)
    if mem0.enabled and facts:
        await mem0.add(
            user_id,
            [{"role": "assistant", "content": f"Summary {datetime.utcnow().date()}: {summary}"}]
            + [{"role": "assistant", "content": f"Fact: {f}"} for f in facts],
            metadata={"source": "daily_consolidation"},
        )

    # 5. Reflection pass over the last 30 days of summaries.
    since30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    past = (
        sb.table("messages")
        .select("content,created_at")
        .eq("conversation_id", conv_id)
        .eq("role", "system")
        .gte("created_at", since30)
        .ilike("content", "[daily.summary]%")
        .order("created_at")
        .execute()
    )
    reflection_note: str | None = None
    if past.data and len(past.data) >= 3:
        kimi = chat_for(Role.REFLECTION, temperature=0.6, streaming=False)
        joined = "\n\n".join(p["content"].removeprefix("[daily.summary] ").strip() for p in past.data)
        ref_res = await kimi.ainvoke([
            SystemMessage(content=REFLECTION_SYSTEM),
            HumanMessage(content=f"Here are my daily summaries from the last 30 days:\n\n{joined}\n\nWhat pattern, tension, or contradiction is worth surfacing to me right now?"),
        ])
        text = ref_res.content if isinstance(ref_res.content, str) else str(ref_res.content)
        if text.strip():
            reflection_note = text.strip()
            sb.table("messages").insert({
                "conversation_id": conv_id,
                "user_id": user_id,
                "role": "reflection",
                "content": reflection_note,
                "metadata": {"job": "consolidate"},
            }).execute()

    # 6. Prune Qdrant: delete entries > 7 days old that were never re-retrieved.
    qdrant = JaiQdrant(settings)
    pruned = 0
    try:
        await qdrant.ensure_collection()
        pruned = await qdrant.prune_stale(user_id=user_id, older_than_days=7, max_hits=0)
    except Exception as e:
        log.warning("consolidate.qdrant_prune_failed", error=str(e))
    finally:
        await qdrant.close()

    # 7. Run due scheduled actions.
    schedule_results: list[dict] = []
    try:
        from .scheduled import run_due_actions
        schedule_results = await run_due_actions(user_id, sb)
        if schedule_results:
            # Write results as system messages so they surface in morning briefing context.
            for r in schedule_results:
                if r.get("result") and r["status"] == "ok":
                    sb.table("messages").insert({
                        "conversation_id": conv_id,
                        "user_id": user_id,
                        "role": "system",
                        "content": f"[scheduled.{r['action_id'][:8]}] {r['description']}: {r['result']}",
                        "metadata": {"job": "scheduled_action", "action_id": r["action_id"]},
                    }).execute()
            log.info("consolidate.scheduled_ran", count=len(schedule_results))
    except Exception as e:
        log.warning("consolidate.scheduled_failed", error=str(e))

    return {
        "ok": True,
        "summary_len": len(summary),
        "fact_count": len(facts),
        "reflection_emitted": bool(reflection_note),
        "qdrant_pruned": pruned,
        "scheduled_ran": len(schedule_results),
    }


async def consolidate_all_users(*, max_concurrency: int = 4) -> dict:
    """Run consolidation for every active user.

    Iterates `public.users` (Supabase Auth users mirrored into our
    `users` table on first sign-in). Failures for one user never abort
    the whole batch — we collect per-user results and return a summary.
    `max_concurrency` keeps the LLM call budget under control.
    """
    sb = supabase_admin()
    try:
        rows = sb.table("users").select("id").execute().data or []
    except Exception as e:
        log.error("consolidate.user_list_failed", error=str(e))
        return {"ok": False, "error": str(e), "ran": 0}

    user_ids = [r["id"] for r in rows if r.get("id")]
    if not user_ids:
        return {"ok": True, "ran": 0, "skipped": 0, "errored": 0, "results": []}

    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _run_one(uid: str):
        async with sem:
            try:
                return uid, await consolidate_for_user(uid)
            except Exception as e:
                log.exception("consolidate.user_failed", user=uid, error=str(e))
                return uid, {"ok": False, "error": str(e)[:200]}

    results = await asyncio.gather(*(_run_one(uid) for uid in user_ids))

    ok = sum(1 for _, r in results if (r or {}).get("ok") is True)
    skipped = sum(1 for _, r in results if (r or {}).get("ok") is None)
    errored = len(results) - ok - skipped
    return {
        "ok": errored == 0,
        "ran": ok,
        "skipped": skipped,
        "errored": errored,
        "results": [{"user_id": uid, "result": r} for uid, r in results],
    }


def _split_summary(raw: str) -> tuple[str, list[str]]:
    """The Fast model returns: summary, blank line, then a JSON array of strings."""
    lines = raw.strip().splitlines()
    # walk backward to find a JSON array
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if line.startswith("[") and line.endswith("]"):
            try:
                facts = json.loads(line)
                if isinstance(facts, list):
                    summary = "\n".join(lines[:i]).strip()
                    return summary, [str(f) for f in facts[:5]]
            except Exception:
                pass
    return raw.strip(), []
