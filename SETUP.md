# Setup

Get the spine running locally in ~15 minutes.

## 0. Prereqs

- macOS or Linux
- Node 20+
- Python 3.12+ (`brew install python@3.12`)
- Docker (for local Kokoro TTS, Neo4j, Qdrant)
- A Supabase project (free tier)
- An OpenRouter API key
- A Groq API key (for Whisper STT)

Optional but recommended:

- Mem0 Cloud account
- Qdrant Cloud cluster (or use the local docker-compose one)
- Neo4j Aura instance (or use the local docker-compose one)

## 1. Clone + env

```bash
git clone <your-fork> jai && cd jai
cp .env.example .env
# open .env and paste in your keys
```

The minimum keys to get *something* responding:

```
OPENROUTER_API_KEY=...
GROQ_API_KEY=...
SUPABASE_URL=https://YOURPROJ.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...
DATABASE_URL=postgres://postgres.YOURPROJ:PWD@aws-x-x.pooler.supabase.com:6543/postgres
NEXT_PUBLIC_SUPABASE_URL=$SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

For the **skill engine** add:

```
JAI_CREDENTIALS_KEY=<run: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'>
SANDBOX_BASE_URL=https://jai-sandbox.<your>.workers.dev   # after deploying infra/cloudflare/sandbox
SANDBOX_AUTH_TOKEN=<random 32-byte hex>                   # also `wrangler secret put SANDBOX_AUTH_TOKEN`
```

For the **internal MCP server** (so Claude/Cursor can read your second brain):

```
JAI_MCP_SERVER_TOKEN=<random hex>
JAI_USER_ID=<your supabase user uuid>
```

For dev you can also set `JAI_USER_ID=<your-supabase-user-uuid>` and skip the
auth gate entirely.

## 2. Run the Supabase migrations

```bash
# via the Supabase CLI
supabase link --project-ref YOURPROJ
supabase db push

# or manually in the SQL Editor — run all four files, in order:
# 1) infra/supabase/migrations/0001_initial.sql
# 2) infra/supabase/migrations/0002_skill_matcher.sql
# 3) infra/supabase/migrations/0003_service_renewals.sql
# 4) infra/supabase/migrations/0004_enable_realtime.sql
```

## 3. Run constraints on Neo4j

```bash
# In Neo4j Aura console → Cypher tab, paste:
cat infra/neo4j/constraints.cypher
```

## 4. Start everything

```bash
./scripts/dev.sh
```

This runs:

- Backend API on <http://localhost:8000>
- Kokoro TTS on <http://localhost:8880> (docker)
- PWA on <http://localhost:3000>

Open <http://localhost:3000> in Chrome or Safari, sign in with your email, and
start talking.

## 5. Install as PWA on iOS

1. Open the URL above in Mobile Safari.
2. Tap Share → Add to Home Screen.
3. JAI now lives on your home screen, full-screen, with mic access.

## 6. Deploy the sandbox worker (for the skill engine)

```bash
cd infra/cloudflare/sandbox
npm install
wrangler secret put SANDBOX_AUTH_TOKEN     # generate with: openssl rand -hex 32
wrangler deploy
# copy the resulting URL into .env as SANDBOX_BASE_URL
```

## 7. Connect JAI's MCP server to Claude Desktop / Cursor

Add to your client's MCP config (e.g. `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "jai": {
      "transport": "sse",
      "url": "http://localhost:8000/mcp/sse",
      "headers": { "Authorization": "Bearer YOUR_JAI_MCP_SERVER_TOKEN" }
    }
  }
}
```

Now Claude/Cursor can call `search_memory`, `list_tasks`, `add_note`,
`get_graph`, `run_skill_intent`, etc. — your second brain as a tool surface.

## 8. Production deploy

```bash
./scripts/deploy.sh
```

Or push to `main` — the GitHub Actions in `.github/workflows/` deploy:
- backend → Fly (`jai-api`)
- TTS → Fly (`jai-tts`)
- sandbox → Cloudflare Workers
- PWA → Cloudflare Pages

Required GitHub secrets: `FLY_API_TOKEN`, `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_ACCOUNT_ID`, `NEXT_PUBLIC_*` build-time vars,
`JAI_MCP_SERVER_TOKEN`, `JAI_BACKEND_URL`.

## 9. Nightly consolidation

`.github/workflows/cron.yml` runs nightly at 07:00 UTC and POSTs to
`/jobs/consolidate`. Override the schedule by editing the cron expression.

## 10. (Optional) Native iOS app via Capacitor

```bash
cd apps/native
pnpm install
export JAI_PWA_URL=https://jai.yourdomain.com
pnpm init:ios
pnpm open:ios   # Xcode → Archive → upload
```

See `apps/native/README.md` for the full App Store flow.

## 11. Pick a different host (optional)

The default stack is **Vercel (PWA) + Fly.io (backend) + Cloudflare (sandbox)**.
You can also run everything on **Railway** (one bill, slightly more expensive)
or keep PWA on Cloudflare Pages — see `docs/DEPLOY.md` for the configs and
trade-offs.

## What works end-to-end (v0.1)

- ✅ One living conversation per user, Postgres-checkpointed
- ✅ Push-to-talk → Groq Whisper → graph → Kokoro TTS → playback
- ✅ Orchestrator (Qwen 3.7 Max) routes to Reflection (Kimi K2.6) / Strategy
  (DeepSeek V4 Pro) / Tool / Skill / Respond / Ask
- ✅ Memory: writes to Mem0 + Qdrant + Neo4j after every turn; retrieves all
  three on every turn (parallel)
- ✅ Tasks panel — fully custom, Google Tasks–style look & feel
- ✅ Notes panel — fully custom, Google Keep–style look & feel
- ✅ Context panel: graph view + docs view + skills view
- ✅ **Voice → tasks/notes auto-routing**: "add a note: …", "remind me to …"
- ✅ **Skill engine**: built-in fast-path → pgvector matcher → Skill Builder
  (Qwen) → Cloudflare Sandbox SDK runner → encrypted credential prompt loop
  → auto-save to skills registry for reuse
- ✅ **External MCP integrations**: connect any MCP server (Gmail, Calendar,
  Linear, GitHub, custom stdio servers) from Settings → Connections
- ✅ **Internal MCP server**: JAI exposes `/mcp/sse` so Claude Desktop,
  Cursor, or any MCP client can search your memory, list/add tasks & notes,
  query your graph, and run skill intents
- ✅ **Nightly consolidation job**: day summary + Mem0 fact extraction +
  reflection pass (Kimi over 30 days of summaries)
- ✅ **Settings UI**: connections, credentials (KEY=value or in chat),
  models registry
- ✅ **Deployment**: `scripts/deploy.sh` + GitHub Actions for backend (Fly),
  TTS (Fly), Sandbox (Cloudflare), PWA (Cloudflare Pages); nightly cron via
  Action

## v0.7 — also shipped

- ✅ **Google OAuth** for Gmail / Calendar / Drive (one-click "Connect" in
  Settings, auto-creates the MCP connection)
- ✅ **Multi-tenant MCP server** — accepts either the static MCP token (dev) or
  a per-user Supabase JWT (production)
- ✅ **Qdrant retrieval-hit tracking + nightly prune** of stale unused entries
- ✅ **Audit log** with live UI (Settings → Audit, refreshes every 5s)
- ✅ **Langsmith tracing** — flip `LANGSMITH_TRACING=true` and set the key
- ✅ **Branded SVG icon** + `scripts/make-icons.sh` to render PNGs at any size
- ✅ **Capacitor scaffold** at `apps/native/` for iOS App Store distribution

## v0.8 — also shipped

- ✅ **Status & renewals dashboard** (Settings → Status): live credit balances
  from OpenRouter / Groq / Qdrant / Cloudflare / ElevenLabs; manual subscription
  tracking for Mem0 / Neo4j / Supabase plan; monthly run-rate; renewal
  alerts ≤14 days out
- ✅ **Supabase Realtime** for tasks/notes — instant cross-device sync, no polling
- ✅ **Onboarding wizard** — 5-step intro that seeds Mem0 + Qdrant with your
  identity facts on first launch
- ✅ **`pnpm gen:types`** — boots the API in a subshell, dumps OpenAPI,
  regenerates `packages/shared-types/src/generated/api.ts`
- ✅ **Skill marketplace** — export/import skills as `.skill.json`
  (single or bulk) from the Skills panel
- ✅ **Vercel + Railway** deployment configs alongside Fly.io —
  see `docs/DEPLOY.md`

## What's still ahead (v0.9 — needs Xcode)

- ⏳ Wake word + always-on push-to-talk on iOS (Capacitor + native plugin)
- ⏳ APNs push (so nightly reflection wakes you up instead of waiting for you)

See `docs/ROADMAP.md`.
