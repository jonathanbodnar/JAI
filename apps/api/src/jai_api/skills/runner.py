"""Top-level skill orchestration.

Flow per turn:
  1. Try built-in fast-path (add_note / add_task / …). If hit, respond.
  2. Try matcher: if cos sim > threshold, fetch creds, run sandbox, respond.
  3. Else build: call Skill Builder.
      a. If it returns need_credentials, respond with an "I need: X" ask.
      b. Otherwise save the new skill, fetch creds, run sandbox, respond.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from .. import audit
from . import builder, matcher, registry
from .builtin import try_builtin
from .sandbox import SandboxClient

log = structlog.get_logger()


@dataclass
class SkillOutcome:
    final_text: str
    skill_id: str | None = None
    record_id: str | None = None
    needs_credentials: list[str] | None = None
    raw: dict | None = None


async def run_intent(
    *,
    user_id: str,
    conversation_id: str | None,
    intent: str,
) -> SkillOutcome:
    # 1. Built-in fast path.
    hit = await try_builtin(user_id=user_id, text=intent)
    if hit:
        await audit.write(
            user_id=user_id,
            actor="agent:builtin",
            action=hit.kind,
            target=hit.record_id,
            payload={"intent": intent[:200]},
            ok=True,
        )
        return SkillOutcome(final_text=hit.response, record_id=hit.record_id)

    # 1.5. URL shortcut. A bare Google Sheets/Drive/Docs URL embeds
    # poorly — the matcher's cosine similarity against the library
    # skill descriptions usually misses (URL token soup vs. natural
    # language description), and we fall through to the skill builder
    # which regenerates something that already exists. Catch the
    # common Google URL shapes here and route directly to the right
    # library skill if the user has it.
    url_hit = await _url_shortcut(user_id=user_id, intent=intent)
    if url_hit:
        log.info("skill.url_shortcut", id=url_hit["id"], title=url_hit.get("title"))
        return await _execute(
            user_id=user_id,
            conversation_id=conversation_id,
            skill=url_hit,
            inputs={"intent": intent},
        )

    # 1.6. Intent shortcut. Common verbs ("draft an email", "what's
    # on my calendar", "search my drive", "track <kpi> = N") map
    # deterministically to library skills. Matters because the
    # embedding matcher misses these often enough that the skill
    # builder gets called for skills we already have, ballooning the
    # library with duplicates (see JB's 12+ "Read Recent Emails" rows).
    intent_hit = await _intent_shortcut(user_id=user_id, intent=intent)
    if intent_hit:
        log.info("skill.intent_shortcut", id=intent_hit["id"], title=intent_hit.get("title"))
        return await _execute(
            user_id=user_id,
            conversation_id=conversation_id,
            skill=intent_hit,
            inputs={"intent": intent},
        )

    # 2. Match.
    matches = await matcher.match(user_id=user_id, intent=intent)
    if matches:
        sk = matches[0]
        log.info("skill.match.hit", id=sk["id"], sim=sk.get("similarity"))
        return await _execute(
            user_id=user_id,
            conversation_id=conversation_id,
            skill=sk,
            inputs={"intent": intent},
        )

    # 3. Build.
    creds_have = await _user_credential_keys(user_id)
    draft = await builder.build_skill(
        goal=intent,
        available_credentials=creds_have,
    )
    # Filter out platform vars from need_credentials — the LLM sometimes
    # lists GMAIL_ACCOUNTS_JSON / SUPABASE_PROJECTS_JSON as missing even
    # though we auto-inject those. Treating them as required would dead-
    # end the user with "Reply with key=value" for a value they can't
    # provide.
    from .builder import _PLATFORM_KEYS, _PLATFORM_PREFIXES
    real_needs = [
        k for k in (draft.need_credentials or [])
        if k not in _PLATFORM_KEYS and not any(k.startswith(p) for p in _PLATFORM_PREFIXES)
    ]
    draft.need_credentials = real_needs
    if real_needs:
        ask = _credential_ask(real_needs, draft.explanation)
        return SkillOutcome(final_text=ask, needs_credentials=real_needs)

    if not (draft.language and draft.source and draft.title and draft.description):
        # If the builder gave us a specific explanation (e.g. the JSON
        # parse fallback), surface that instead of the generic apology
        # — it carries more actionable info for the user.
        explanation = (draft.explanation or "").strip()
        return SkillOutcome(
            final_text=(
                explanation
                or "I couldn't build a skill for that — could you rephrase what you want me to do?"
            )
        )

    # Last-mile dedup. Even after a permissive match miss, the builder's
    # output description embeds much more cleanly than the user's raw
    # phrasing, so an additional similarity check against the whole
    # skill library (including archived ones) catches the case where
    # the LLM just regenerated something we already have.
    twin = await matcher.match_for_dedup(
        user_id=user_id,
        title=draft.title,
        description=draft.description,
    )
    if twin:
        # If the near-twin was disabled because it was broken (syntax
        # error, runtime poison, etc.), DO NOT revive it — that's how
        # the same SyntaxError ran four times in a row for JB. Just
        # ignore it and let the rest of the flow save the fresh draft.
        twin_meta = twin.get("metadata") or {}
        if twin_meta.get("disabled_reason"):
            log.info(
                "skill.dedup.skip_disabled",
                twin_id=twin["id"],
                reason=str(twin_meta.get("disabled_reason"))[:120],
            )
            twin = None

    if twin:
        log.info(
            "skill.dedup.hit",
            twin_id=twin["id"],
            twin_title=twin.get("title"),
            sim=twin.get("similarity"),
            was_active=twin.get("is_active"),
        )
        # Reactivate if it was archived — that's better than ignoring
        # the user's existing library and forcing a regeneration.
        if not twin.get("is_active"):
            try:
                await registry.set_active(user_id=user_id, skill_id=twin["id"], is_active=True)
                twin["is_active"] = True
            except Exception as e:
                log.warning("skill.reactivate_failed", error=str(e))
        return await _execute(
            user_id=user_id,
            conversation_id=conversation_id,
            skill=twin,
            inputs={"intent": intent},
        )

    saved = await registry.save_skill(
        user_id=user_id,
        title=draft.title,
        description=draft.description,
        language=draft.language,
        source=draft.source,
        # `uses_credentials` is the set of env vars the script actually
        # reads (extracted from the source + declared by the LLM). This
        # is what gates execution and gets injected into the sandbox.
        required_credentials=draft.uses_credentials,
        required_tools=draft.required_tools,
    )
    return await _execute(
        user_id=user_id,
        conversation_id=conversation_id,
        skill=saved,
        inputs={"intent": intent},
        first_run=True,
    )


async def _execute(
    *,
    user_id: str,
    conversation_id: str | None,
    skill: dict,
    inputs: dict,
    first_run: bool = False,
) -> SkillOutcome:
    required = skill.get("required_credentials") or []
    # Strip platform vars defensively — some older skills saved them on
    # required_credentials before we filtered the builder output, and
    # without this they'd permanently 404 with a credential ask.
    from .builder import _PLATFORM_KEYS, _PLATFORM_PREFIXES
    required = [
        k for k in required
        if k not in _PLATFORM_KEYS and not any(k.startswith(p) for p in _PLATFORM_PREFIXES)
    ]
    missing = await registry.missing_credentials(user_id=user_id, required=required)
    if missing:
        return SkillOutcome(
            final_text=_credential_ask(missing),
            skill_id=skill["id"],
            needs_credentials=missing,
        )

    creds = await registry.get_credentials(user_id=user_id, keys=required)

    # Always inject platform credentials so skills can call JAI's own
    # Supabase and API without the user having to store them manually.
    platform_env = _platform_env(user_id)
    sources_env = await _data_sources_env(user_id)
    accounts_env = await _connected_accounts_env(user_id)

    # Pass the user's raw intent + structured inputs so library skills
    # (which can't have their source rewritten per call) still have
    # access to the request context.
    import json as _json
    intent_env = {
        "JAI_USER_INTENT": (inputs.get("intent") if isinstance(inputs, dict) else "") or "",
        "JAI_SKILL_INPUTS_JSON": _json.dumps(inputs or {}),
    }

    merged_env = {
        **platform_env,
        **sources_env,
        **accounts_env,
        **intent_env,
        **creds,  # user creds win on collision
    }

    # SYNTAX GUARD at execution time — covers skills already in the DB
    # whose source is broken (LLM artifacts from before the builder-side
    # syntax check, or skills that survived an archive/dedup cycle).
    # If we don't gate this here, the matcher happily re-runs the same
    # broken skill forever and the user pays the sandbox boot cost each
    # time for the same SyntaxError. Also disable the skill so the next
    # matcher round doesn't return it again.
    bad = _python_syntax_error(skill.get("language") or "python", skill.get("source") or "")
    if bad is not None:
        log.warning(
            "skill.execute.syntax_invalid",
            skill_id=skill["id"],
            title=skill.get("title"),
            error=str(bad)[:200],
        )
        try:
            await registry.disable_skill(skill_id=skill["id"], reason=f"syntax: {bad}")
        except Exception as disable_err:
            log.warning("skill.disable_failed", error=str(disable_err)[:200])
        return SkillOutcome(
            final_text=(
                "That skill's source had a Python syntax error "
                f"(`{bad}`), so I disabled it instead of running broken "
                "code in the sandbox. Ask me again and I'll draft a "
                "fresh version, or tell me what you want differently."
            ),
            skill_id=skill["id"],
        )

    sandbox = SandboxClient()
    try:
        raw = await sandbox.run(
            user_id=user_id,
            skill_id=skill["id"],
            language=skill["language"],
            source=skill["source"],
            env=merged_env,
        )
    finally:
        await sandbox.close()

    status = raw.get("status", "error")
    await registry.record_run(
        user_id=user_id,
        skill_id=skill["id"],
        conversation_id=conversation_id,
        inputs=inputs,
        output=raw.get("result"),
        status="ok" if status == "ok" else "error",
        stdout=raw.get("stdout"),
        stderr=raw.get("stderr"),
        error=None if status == "ok" else (raw.get("stderr") or "non-zero exit"),
        duration_ms=raw.get("duration_ms"),
    )
    await audit.write(
        user_id=user_id,
        actor=f"agent:skill:{skill['title']}",
        action="skill.run",
        target=skill["id"],
        payload={"duration_ms": raw.get("duration_ms"), "exit_code": raw.get("exit_code")},
        ok=status == "ok",
        error=None if status == "ok" else _short(raw.get("stderr")),
    )

    if status == "ok":
        suffix = " (saved as a reusable skill)" if first_run else ""
        result_preview = _preview(raw.get("result"))
        text = f"Done{suffix}. {result_preview}" if result_preview else f"Done{suffix}."
    else:
        # Translate well-known Google / OAuth / sandbox errors into
        # actionable instructions before falling back to the raw diag.
        diag = _error_diag(raw)
        hint = _actionable_hint(diag, raw)
        if hint:
            text = hint
        else:
            text = (
                "That didn't work — the script errored out.\n\n"
                f"```\n{diag}\n```\n"
                "Want me to try a different approach, or reconnect the account in Settings?"
            )

    return SkillOutcome(
        final_text=text,
        skill_id=skill["id"],
        # `skill_executor` reads `raw.status` + `raw.result` to decide
        # whether to synthesize through Kimi vs. fall back to `text`.
        raw={
            **(raw or {}),
            "skill_name": skill.get("title"),
            "first_run": first_run,
        },
    )


# Map of (regex pattern, library_key) for fast URL → skill routing.
# Order matters — Sheets is matched before generic Drive because a
# Sheets URL is also technically a Drive URL.
_URL_ROUTES: list[tuple[str, str]] = [
    (r"docs\.google\.com/spreadsheets/d/", "sheets.read_rows"),
    (r"docs\.google\.com/document/d/", "drive.read_doc"),
    (r"docs\.google\.com/presentation/d/", "drive.read_doc"),
    (r"drive\.google\.com/(file/d/|open\?id=|drive/folders/)", "drive.search_files"),
]


# Intent → library_key map. Each pattern is a regex matched
# case-insensitively against the full user message. We match the
# verbs/phrases that the orchestrator's own prompt lists as concrete
# skill triggers, so server-side routing mirrors what we're already
# telling the LLM to do.
#
# Order matters — more specific patterns first. "send the draft"
# should beat "send email" (the former is gmail.send_draft, the
# latter is gmail.compose if no draft exists yet).
_INTENT_ROUTES: list[tuple[str, str]] = [
    # --- Email: refine / send / draft (compose) ---
    (r"\b(send|fire off|ship) (the|that|this|my)? ?(draft|email|reply)\b", "gmail.send_draft"),
    # Refinement triggers — require an explicit draft/email noun so
    # "make it shorter" doesn't false-match unrelated content. Bare
    # follow-ups still flow through the orchestrator's recent-skill
    # hint into respond (which can re-derive from cache).
    (r"\b(more casual|more formal|shorter|longer|tighten|rewrite|edit|fix)\s+(the\s+)?(draft|opener|email|subject|reply)\b", "gmail.refine_draft"),
    (r"\bmake (it|the (email|draft)) (shorter|longer|more casual|more formal)\b", "gmail.refine_draft"),
    # Compose triggers — allow flexible filler between the verb and the
    # noun ("draft an email", "write me a quick email", "compose a
    # reply", "put together a short note", etc.).
    (r"\b(draft|write|compose|prep|prepare|put together)\b[^\n]{0,25}?\b(email|reply|message|note|response|dm)\b", "gmail.compose"),
    (r"\breply to\b.*\b(email|thread|message)\b", "gmail.compose"),
    (r"\breply to\b\s+\S+@\S+\.\S+", "gmail.compose"),
    # --- Email: reading ---
    (r"\b(any |what'?s |show me |list )?(important|priority) (emails|inbox|mail)\b", "gmail.important_inbox"),
    (r"\b(read|check|show|list|see) (my )?(latest |recent |today'?s |new )?(emails|inbox|mail|gmail)\b", "gmail.read_inbox"),
    (r"\bwhat'?s in my (inbox|gmail|mail)\b", "gmail.read_inbox"),
    (r"\b(any )?(new )?unread (emails?|mails?)\b", "gmail.unread_count"),
    (r"\bsearch (my )?(emails?|gmail|inbox)\b", "gmail.search"),
    (r"\barchive (my )?(emails?|messages?|gmail)\b", "gmail.archive"),
    # --- Calendar ---
    (r"\b(find|any) free (time|slots?)\b", "calendar.find_free_time"),
    (r"\b(create|add|schedule|book|put on) (an? |the )?(event|meeting|calendar (event|invite)|invite)\b", "calendar.create_event"),
    (r"\bweek('s)? (calendar|summary|meetings|hours)\b", "calendar.week_summary"),
    (r"\b(what'?s |show |my )?(today'?s |my )?(calendar|agenda|schedule)\b", "calendar.agenda"),
    # --- Drive ---
    (r"\b(search|find) (my )?(drive|files|docs?)\b", "drive.search_files"),
    (r"\b(read|open|show me) (this |the |that )?(doc|document|sheet|spreadsheet|slides?)\b", "drive.read_doc"),
    (r"\b(recent|latest) (drive )?(files?|docs?)\b", "drive.recent_files"),
    # --- KPIs ---
    # Verb + label + "= value" within a single short phrase. The bounded
    # gap (≤40 chars, no newline) avoids matching unrelated `=` later
    # in a long message like "I set the alarm = wake at 7".
    (r"\b(track|pin|set|update)\b[^\n]{0,40}=\s*\S+", "jai.kpi_upsert"),
    (r"\b(what'?s|what are|show|list) (my |the )?KPIs?\b", "jai.kpi_list"),
    # --- JAI internal ---
    (r"\b(what'?s|what are|show|list) (my )?tasks?\b", "jai.list_tasks"),
    (r"\b(add|create) (a )?task\b", "jai.create_task"),
    (r"\bsearch (my )?notes\b", "jai.search_notes"),
    (r"\brecent (jai )?(activity|history)\b", "jai.recent_activity"),
]


async def _library_skill_by_key(user_id: str, library_key: str) -> dict | None:
    """Fetch a user's active library skill by its canonical key.

    Returns None if the skill isn't installed (user opted out, or
    seeder hasn't run yet for them) so the caller can fall through.
    """
    from ..db import supabase_admin
    sb = supabase_admin()
    res = (
        sb.table("skills")
        .select("id, title, description, language, source, required_credentials, required_tools, metadata")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .contains("metadata", {"library_key": library_key})
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


async def _url_shortcut(*, user_id: str, intent: str) -> dict | None:
    """Direct-route well-known content URLs to their library skill.

    Bypasses the embedding matcher, which struggles to embed a bare URL
    close to a library skill description. Returns the active skill row
    (same shape as matcher.match) or None if there's no URL hit or the
    user doesn't have the corresponding library skill installed.
    """
    import re

    library_key: str | None = None
    for pattern, key in _URL_ROUTES:
        if re.search(pattern, intent):
            library_key = key
            break
    if not library_key:
        return None

    return await _library_skill_by_key(user_id, library_key)


async def _intent_shortcut(*, user_id: str, intent: str) -> dict | None:
    """Direct-route common skill verbs to their library skill.

    The embedding matcher routinely misses obvious phrasings — "draft
    an email" vs. the gmail.compose description sits below the 0.65
    cosine threshold often enough that the runner falls through to
    skill_builder and regenerates a duplicate skill (or fails). The
    orchestrator prompt already enumerates these mappings; this is
    the server-side enforcement of the same contract.

    Returns the active skill row or None if no pattern matches or the
    user doesn't have that library skill installed.
    """
    import re

    library_key: str | None = None
    for pattern, key in _INTENT_ROUTES:
        if re.search(pattern, intent, flags=re.IGNORECASE):
            library_key = key
            break
    if not library_key:
        return None

    return await _library_skill_by_key(user_id, library_key)


def _credential_ask(missing: list[str], explanation: str | None = None) -> str:
    keys = ", ".join(missing)
    if explanation:
        return f"Before I can run that, I need: {keys}.\n{explanation}\nReply with the values (e.g. `key=value`, one per line) or open Settings → Credentials."
    return (
        f"To do that, I need a few things from you: {keys}. "
        "Reply with `key=value` (one per line), or set them in Settings → Credentials."
    )


async def _connected_accounts_env(user_id: str) -> dict[str, str]:
    """Inject ALL connected OAuth accounts as JSON env vars.

    The legacy `GMAIL_OAUTH_JSON` (default account only) still gets
    populated through `skill_credentials`, but skills that say things
    like "read all my emails" need every connected mailbox. We expose:

      GMAIL_ACCOUNTS_JSON       — list of {email,label,token_json,is_default}
      CALENDAR_ACCOUNTS_JSON
      DRIVE_ACCOUNTS_JSON

    Each `token_json` is the same shape the existing Gmail recipe
    consumes (token/refresh_token/client_id/client_secret/etc.) so a
    skill can iterate and call `Credentials.from_authorized_user_info`
    per account.
    """
    import json as _json
    from ..db import supabase_admin
    from .credentials import decrypt

    env: dict[str, str] = {}
    try:
        sb = supabase_admin()
        rows = (
            sb.table("connected_accounts")
            .select(
                "service, account_email, label, value_encrypted, is_default, scopes"
            )
            .eq("user_id", user_id)
            .eq("provider", "google")
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
    except Exception as e:
        log.warning("connected_accounts.fetch_failed", error=str(e))
        return env

    by_service: dict[str, list[dict]] = {}
    for r in rows:
        try:
            token_str = decrypt(r["value_encrypted"].encode("ascii"))
            token_obj = _json.loads(token_str)
        except Exception as e:
            log.warning(
                "connected_accounts.decrypt_failed",
                service=r.get("service"),
                email=r.get("account_email"),
                error=str(e),
            )
            continue
        by_service.setdefault(r["service"], []).append(
            {
                "email": r["account_email"],
                "label": r.get("label") or r["account_email"],
                "token_json": token_obj,
                "is_default": bool(r.get("is_default")),
                "scopes": r.get("scopes") or [],
            }
        )

    for service, accounts in by_service.items():
        env[f"{service.upper()}_ACCOUNTS_JSON"] = _json.dumps(accounts)
    return env


async def _data_sources_env(user_id: str) -> dict[str, str]:
    """Build env vars for the user's connected external data sources.

    Emits two kinds of vars:
      - `SUPABASE_PROJECTS_JSON` — JSON list of {slug,label,url,key} for
        every active Supabase source. Lets skills enumerate or pick by slug.
      - `SUPABASE_{SLUG}_URL` / `SUPABASE_{SLUG}_KEY` — per-source pairs
        for skills that want a direct lookup.
    """
    import json
    from ..db import supabase_admin
    from .credentials import decrypt

    env: dict[str, str] = {}
    try:
        sb = supabase_admin()
        rows = (
            sb.table("data_sources")
            .select("kind, slug, label, url, key_encrypted")
            .eq("user_id", user_id)
            .eq("kind", "supabase")
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
    except Exception as e:
        log.warning("data_sources.fetch_failed", error=str(e))
        return env

    projects: list[dict] = []
    for r in rows:
        try:
            key = decrypt(r["key_encrypted"].encode("ascii"))
        except Exception as e:
            log.warning("data_sources.decrypt_failed", slug=r.get("slug"), error=str(e))
            continue
        slug = (r["slug"] or "").upper()
        url = r["url"]
        projects.append({"slug": r["slug"], "label": r["label"], "url": url, "key": key})
        # Convenient per-source env vars for skills that target one project.
        env[f"SUPABASE_{slug}_URL"] = url
        env[f"SUPABASE_{slug}_KEY"] = key

    if projects:
        env["SUPABASE_PROJECTS_JSON"] = json.dumps(projects)
    return env


def _platform_env(user_id: str) -> dict[str, str]:
    """Credentials every skill gets for free — no user setup required.

    These are the JAI platform credentials (Supabase URL, service role key,
    backend URL, the user's own ID). Skills can use them to:
    - query/write JAI's own Supabase tables (tasks, notes, messages, etc.)
    - call JAI's internal REST API
    - cross-reference the user's projects, progress, anything stored in Supabase

    We deliberately expose the *service* role key so skills can read across
    all tables without fighting RLS. This is fine because skills run in the
    user's sandboxed container and can't exfiltrate data anywhere outside.
    """
    from ..config import get_settings
    s = get_settings()
    env: dict[str, str] = {}
    if s.supabase_url:
        env["JAI_SUPABASE_URL"] = s.supabase_url
    if s.supabase_service_role_key:
        env["JAI_SUPABASE_KEY"] = s.supabase_service_role_key
    if s.jai_backend_url:
        env["JAI_BACKEND_URL"] = s.jai_backend_url
    # OpenRouter access is needed by skills that draft text (e.g. email
    # composers). The sandbox is isolated so exposing the platform key
    # here is fine, but skills MUST treat this like any other secret —
    # never log or echo it back to the user.
    if s.openrouter_api_key:
        env["OPENROUTER_API_KEY"] = s.openrouter_api_key
    env["JAI_USER_ID"] = user_id
    return env


async def _user_credential_keys(user_id: str) -> list[str]:
    """Every credential-shaped env var that will be available at run time.

    The LLM uses this list to decide whether it can complete the task or
    needs to ask the user for something. It MUST include the auto-
    injected platform / OAuth / data-source vars or the LLM will treat
    them as missing and JAI will ask the user to type in a value for a
    var they don't even know about.
    """
    from ..db import supabase_admin
    sb = supabase_admin()

    keys: list[str] = []

    # 1) User-supplied creds in skill_credentials.
    try:
        res = sb.table("skill_credentials").select("key").eq("user_id", user_id).execute()
        keys.extend(r["key"] for r in (res.data or []))
    except Exception as e:
        log.warning("creds.list_failed", error=str(e))

    # 2) JAI platform vars (always injected).
    keys.extend([
        "JAI_SUPABASE_URL", "JAI_SUPABASE_KEY", "JAI_USER_ID", "JAI_BACKEND_URL",
        "OPENROUTER_API_KEY",
    ])

    # 3) External Supabase data sources.
    try:
        rows = (
            sb.table("data_sources")
            .select("slug")
            .eq("user_id", user_id)
            .eq("kind", "supabase")
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        if rows:
            keys.append("SUPABASE_PROJECTS_JSON")
            for r in rows:
                slug = (r["slug"] or "").upper()
                if slug:
                    keys.append(f"SUPABASE_{slug}_URL")
                    keys.append(f"SUPABASE_{slug}_KEY")
    except Exception as e:
        log.warning("creds.data_sources_list_failed", error=str(e))

    # 4) Connected OAuth accounts (multi-account env vars).
    try:
        accts = (
            sb.table("connected_accounts")
            .select("service")
            .eq("user_id", user_id)
            .eq("provider", "google")
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        for svc in {a["service"] for a in accts}:
            keys.append(f"{svc.upper()}_ACCOUNTS_JSON")
    except Exception as e:
        log.warning("creds.accounts_list_failed", error=str(e))

    return sorted(set(keys))


def _preview(result) -> str:
    if result is None:
        return ""
    s = str(result)
    return s if len(s) <= 240 else s[:240] + "…"


def _short(s) -> str:
    if not s:
        return ""
    s = str(s).strip().splitlines()[-1]
    return s[:160]


def _python_syntax_error(language: str, source: str) -> str | None:
    """Return a short SyntaxError summary if `source` won't parse, else None.

    Only validates Python (the dominant language). For TS/bash we trust
    the sandbox to surface its own parse errors.
    """
    if (language or "").lower() != "python" or not source:
        return None
    import ast as _ast
    try:
        _ast.parse(source)
        return None
    except SyntaxError as e:
        msg = e.msg or "syntax error"
        loc = f" at line {e.lineno}" if getattr(e, "lineno", None) else ""
        return f"{msg}{loc}"


def _error_diag(raw: dict | None) -> str:
    """Build a multi-line diagnostic the user can actually read.

    Picks the most informative content — exit message, install log, stderr
    tail, stdout tail — and caps at ~1200 chars so the chat bubble stays
    readable but still includes enough to act on.
    """
    if not raw:
        return "(no diagnostic captured)"
    parts: list[str] = []
    err = (raw.get("error") or "").strip()
    stderr = (raw.get("stderr") or "").strip()
    stdout = (raw.get("stdout") or "").strip()

    # If the sandbox prepended a labeled install log, that's the most
    # actionable signal — keep it visible regardless of stderr length.
    if "--- install log ---" in stderr:
        parts.append(stderr)
    else:
        if err and err not in stderr:
            parts.append(err)
        if stderr:
            # Last 6 lines of stderr keeps the traceback footer (file/line +
            # exception type) without dragging in unrelated noise.
            lines = stderr.splitlines()
            parts.append("\n".join(lines[-6:]) if len(lines) > 6 else stderr)
        elif stdout:
            parts.append(stdout.splitlines()[-1])

    text = "\n".join(parts).strip() or "(empty error)"
    if len(text) > 1200:
        text = text[-1200:]
    return text


def _actionable_hint(diag: str, raw: dict | None) -> str | None:
    """Translate well-known failures into a clear, actionable user message.

    Returns `None` if no rule matches — caller falls back to the raw diag.
    Each branch produces a complete chat reply (with the relevant link
    or next step) so the user never has to read a Python traceback.
    """
    import re

    if not diag:
        return None
    d = diag.lower()

    # Google API not enabled on the Cloud project. The error body always
    # includes "API has not been used in project N before or it is
    # disabled" plus a direct enable URL we can hand to the user.
    if "accessnotconfigured" in d or "api has not been used in project" in d:
        m = re.search(
            r"https://console\.developers\.google\.com/apis/api/([\w.\-]+)/overview\?project=(\d+)",
            diag,
        )
        if m:
            api = m.group(1)
            project = m.group(2)
            pretty = {
                "gmail.googleapis.com": "Gmail API",
                "calendar-json.googleapis.com": "Calendar API",
                "drive.googleapis.com": "Drive API",
            }.get(api, api)
            url = f"https://console.developers.google.com/apis/api/{api}/overview?project={project}"
            return (
                f"The **{pretty}** isn't enabled on your Google Cloud project yet. "
                f"That's a one-click fix: open [this link]({url}) and click "
                "**Enable**, wait ~30 seconds, then ask me again."
            )

    # Refresh token rejected / revoked. Re-auth in Settings.
    if "invalid_grant" in d or "token has been expired or revoked" in d:
        return (
            "Your Google sign-in expired or was revoked. Open **Settings → "
            "Connections**, hit the trash icon on the Gmail/Calendar/Drive "
            "account, and reconnect it."
        )

    # Missing OAuth scope (vs. API not enabled — those are different 403s).
    if "insufficient" in d and ("scope" in d or "permission" in d):
        return (
            "The connected Google account doesn't have the right permission "
            "for this. Open **Settings → Connections**, disconnect that "
            "account, and reconnect it — Google will re-prompt for the "
            "missing scopes."
        )

    # Sandbox couldn't pip-install something. Tell the user which package
    # so we can decide whether to add it permanently or rewrite the skill.
    if "FAILED" in diag and "pip install" in diag:
        return (
            "The skill needed a Python package that isn't available in the "
            "sandbox. Tell me what you were trying to do and I'll rewrite "
            "the skill to use only the pre-installed libraries."
        )

    return None
