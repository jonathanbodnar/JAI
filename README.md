# JAI

A second brain, founder OS, executive advisor, autonomous operator, memory
system, identity model, workflow agent, and strategic reasoning partner — one
living conversation that learns who you are and gets things done for you.

## What it is

JAI is not a chatbot. It is a stateful, voice-first PWA backed by a multi-agent
graph that:

- holds **one persistent conversation** that never resets
- builds a **long-term identity model** of you (Mem0 + Neo4j + Qdrant)
- accepts **push-to-talk audio** like ChatGPT, with on-device-feel latency
- gives you **tasks and notes that look and feel like Google Tasks and Keep**
  but are fully custom — your data, your DB, no external sync — plus a
  **context panel** that visualizes your knowledge graph and auto-organized
  docs
- runs **agentic skills** (write a script, ask you for creds, sandbox-execute,
  save the skill for next time — the Cursor pattern, generalized to anything)
- connects to **Gmail, Calendar, Linear**, and any MCP server when you want
  external integrations
- exposes its own **MCP server** so other tools can read/write your second brain

## Architecture (one line)

```
PWA (Next.js) ──ws──> FastAPI ──> LangGraph ──> [Orchestrator | Reflection | Strategy | Skill Builder]
                                       │
                                       ├──> Mem0 (identity) + Qdrant (semantic) + Neo4j (graph) + Postgres (state)
                                       ├──> MCP tools (Gmail, Calendar, Linear, …)
                                       └──> Skill sandbox (Cloudflare Sandbox SDK)
```

See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) for the full design.

## Model stack (all via OpenRouter, swap any time)

| Role | Model | Slug |
|---|---|---|
| Orchestrator / Tool calling | Qwen 3.7 Max | `qwen/qwen3.7-max` |
| Reflection / Multi-agent | Kimi K2.6 | `moonshotai/kimi-k2.6` |
| Deep strategy | DeepSeek V4 Pro | `deepseek/deepseek-v4-pro` |
| Skill builder (coding) | Qwen 3.7 Max | `qwen/qwen3.7-max` |
| Fast / cheap | DeepSeek V4 Flash | `deepseek/deepseek-v4-flash:free` |

## Repo layout

```
apps/
  web/        Next.js 15 PWA (chat, tasks, notes, context)
  api/        FastAPI + LangGraph backend (the brain)
  tts/        Kokoro TTS sidecar (Fly.io)
packages/
  shared-types/   OpenAPI-generated TS types
  ui/             Shared React components
infra/
  supabase/   migrations + schema
  cloudflare/ Sandbox SDK + Pages config
  neo4j/      constraints + seed
docs/         architecture, memory, agents, skills
```

## Quick start

```bash
# 1. install
pnpm install
cd apps/api && uv sync && cd ../..

# 2. env
cp .env.example .env  # fill in keys

# 3. infra (one time)
supabase start                                     # local Postgres
docker compose -f infra/docker-compose.dev.yml up  # local Qdrant + Neo4j (optional, prod uses cloud)

# 4. run
pnpm dev:all   # PWA + API + TTS in parallel
```

Open <http://localhost:3000>, install as PWA from your phone via "Add to Home
Screen," and start talking.

## Status

Early. The spine (chat + voice + memory) is the priority. See
[`docs/ROADMAP.md`](./docs/ROADMAP.md).
