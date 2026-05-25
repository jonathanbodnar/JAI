# Roadmap

## v0.1 — Spine ✅

- [x] Monorepo scaffold, configs, env templates
- [x] FastAPI + LangGraph backend with single persistent thread per user
- [x] OpenRouter LLM wrapper with role-based model registry
- [x] Next.js PWA shell, installable, four routes
- [x] Supabase auth + DB schema
- [x] Push-to-talk: mic capture → Groq Whisper → text → response
- [x] Kokoro TTS sidecar + audio playback
- [x] Mem0 + Qdrant + Neo4j wired into retrieve/persist nodes

## v0.2 — Panels ✅

- [x] Tasks panel (fully custom, Tasks-style look & feel)
- [x] Notes panel (fully custom, Keep-style look & feel)
- [x] Voice capture → auto-route to tasks/notes ("add a note: …", "remind me to …")
- [x] Context panel: Neo4j graph view + auto-organized docs view

## v0.3 — Agent crew ✅

- [x] Reflection sub-agent (Kimi K2.6)
- [x] Strategy sub-agent (DeepSeek V4 Pro)
- [x] Orchestrator routing logic + delegation
- [x] Nightly consolidation job

## v0.4 — Skill engine ✅

- [x] Skill registry tables + pgvector search
- [x] Cloudflare Sandbox SDK integration
- [x] Skill Builder agent + script gen
- [x] Credential prompt flow (Fernet-encrypted, chat-or-Settings entry)
- [x] Auto-match + auto-run on future requests

## v0.5 — Integrations ✅

- [x] External MCP integrations (Gmail/Calendar/Linear/GitHub/custom via Settings → Connections)
- [x] Tool-calling ReAct agent that uses connected MCP tools + built-ins
- [x] Internal MCP server (JAI as MCP for Claude Desktop / Cursor)

## v0.6 — Deploy ✅

- [x] Fly.io: backend (`jai-api`) + TTS (`jai-tts`)
- [x] Cloudflare Workers: sandbox
- [x] Cloudflare Pages: PWA
- [x] GitHub Actions: CI + deploy + nightly cron

## v0.7 — Polish ✅

- [x] Branded SVG icon + render script (192/512/1024/apple-touch)
- [x] Google OAuth helpers (Gmail / Calendar / Drive) with auto-MCP wiring
- [x] Multi-tenant internal MCP (Supabase JWT → per-user, with env fallback)
- [x] Audit log UI (live updates every 5s)
- [x] Langsmith tracing on by env flag
- [x] Qdrant pruning heuristic (hit tracking + nightly prune of stale, unused)
- [x] Capacitor scaffold for iOS / Android with config + build doc

## v0.8 — Operator dashboard + live PWA ✅ (this round)

- [x] **Status & renewals dashboard** (Settings → Status): live credit
      balances from OpenRouter, Groq, Qdrant, Cloudflare, ElevenLabs;
      manual entry for Mem0, Neo4j, Supabase plan + any other subscription;
      monthly run-rate total + renewal alerts (≤14 days)
- [x] Supabase Realtime channels for tasks/notes (instant cross-device sync)
- [x] First-run onboarding wizard (5 questions → Mem0 + Qdrant seed facts)
- [x] Type generation: `pnpm gen:types` boots API in subshell, dumps OpenAPI,
      regenerates `packages/shared-types/src/generated/api.ts`
- [x] Skill marketplace: export/import `.skill.json` files (single + bulk)
- [x] Deployment alternatives: Vercel (PWA), Railway (backend or both), with
      configs alongside existing Fly.io setup → `docs/DEPLOY.md`

## v0.9 — Native polish (needs Xcode)

- [ ] Wake word + always-on push-to-talk on iOS (Capacitor + native plugin)
- [ ] APNs push from consolidation job (nightly reflection alerts)
- [ ] Native screens for cellular voice continuity
- [ ] Background recording with on-device VAD

## v1.0 — App Store

- [ ] App Store + Play Store submission
- [ ] Marketing site
- [ ] Pricing / Stripe
