# Architecture

> One living conversation. One identity model. One operator that grows with you.

## Principles

1. **One conversation, forever.** No "new chat" button. Memory consolidation
   keeps context bounded.
2. **Identity over retrieval.** Mem0 + Neo4j model *who you are*, not just
   *what you've said*. RAG is a side effect.
3. **Voice-first, text-equal.** Push-to-talk is a first-class input. Everything
   the agent says can be spoken.
4. **MCP-first integrations.** Anything that has an MCP server, we use as a
   tool. Anything that doesn't, the agent writes a script for and saves as a
   skill.
5. **Model-agnostic.** Every model is addressed by role (orchestrator,
   reflection, strategy, skill-builder). Swap slugs in `.env` without touching
   code.
6. **Single repo, clean packages.** Monorepo for shipping speed; split into
   services if and when team scale demands it.

## Components

### Frontend — `apps/web` (Next.js 15 PWA)

- Installable PWA (manifest + service worker via `next-pwa`).
- Four panels: **Chat** (default, push-to-talk), **Tasks** (looks and behaves
  like Google Tasks, but fully custom — your data in Supabase, no external
  sync), **Notes** (looks and behaves like Google Keep, also fully custom),
  **Context** (graph view of Neo4j + auto-organized doc view of Qdrant).
- Auth: Supabase email/password + Google OAuth (used only to sign in, not for
  Tasks/Keep data).
- Transport: WebSocket to backend for streaming chat + audio; REST for CRUD.

### Backend — `apps/api` (FastAPI + LangGraph)

- **Single LangGraph per user**, checkpointed to Postgres (Supabase).
- Persistent thread id = `user_id` (no new chats).
- Graph nodes:
  1. `ingest` — STT if audio, normalize text, attach metadata.
  2. `retrieve_memory` — pull Mem0 identity facts + Qdrant semantic hits +
     Neo4j 1-hop subgraph around mentioned entities.
  3. `route` — orchestrator (Qwen 3.7 Max) decides: respond, plan, delegate,
     execute skill, or ask clarifying question.
  4. `delegate` — fan out to reflection (Kimi K2.6) or strategy (DeepSeek V4
     Pro) sub-agents when needed; aggregate.
  5. `execute_tool` — MCP tool calls and/or skill execution in sandbox.
  6. `respond` — stream final response to client.
  7. `persist_memory` — write deltas back to Mem0/Qdrant/Neo4j. Extract new
     facts, beliefs, relationships, decisions.
  8. `consolidate` (nightly cron) — summarize the day, prune stale working
     memory, update identity graph.

### Memory — four-tier, all cloud-managed

| Tier | System | Role | What goes in |
|---|---|---|---|
| Working | LangGraph state | This turn's context | Last N messages, retrieved hits |
| Identity | Mem0 Cloud | "Who am I" facts | beliefs, preferences, patterns, recurring themes |
| Semantic | Qdrant Cloud | Raw embedding store | full transcripts, voice notes, docs, screenshots |
| Relational | Neo4j Aura | Graph of you | people, companies, decisions, projects, timelines, contradictions |
| App state | Supabase Postgres | Operational data | users, tasks, notes, conversations, skills, MCP creds |

### Voice

- **STT**: Groq Whisper Large v3 Turbo (~$0.04/hr, ~300ms latency).
- **TTS**: Kokoro-82M self-hosted in `apps/tts` on Fly.io (free, CPU-only).
  ElevenLabs as fallback voice for higher-fidelity output.
- Frontend captures push-to-talk via `MediaRecorder`, streams chunks over
  WebSocket, plays back TTS audio as it streams.

### Agentic skills

Two layers, in priority order:

1. **MCP tools** — the agent prefers calling existing MCP servers for
   external integrations (Gmail, Calendar, Linear, GitHub, etc.). Reliable,
   typed, audited. Tasks and Notes are internal — no MCP needed.
2. **Generated skills** — when no MCP fits, the orchestrator delegates to the
   **Skill Builder** (Qwen 3.7 Max). It:
   - reads the user's intent and any required inputs,
   - asks for credentials interactively if needed (saved to encrypted
     `skill_credentials` table),
   - writes a Python or TypeScript script,
   - executes it in a Cloudflare Sandbox SDK container,
   - if successful, saves the script + metadata + embedding to the
     `skills` table,
   - on future requests, the **Skill Matcher** (embedding search) finds the
     saved skill and runs it directly, no regeneration.

### Sandbox

- Cloudflare Sandbox SDK runs untrusted code in a remote Linux container with
  network egress, file system, exec — all the things a VA would have on their
  laptop, but isolated.
- Sandbox URL returned for ephemeral browser-style preview when relevant.

### Deployment

- **PWA**: Cloudflare Pages (Next.js adapter).
- **API**: Fly.io (one machine, Python 3.12, autoscale to zero).
- **TTS**: Fly.io (sidecar, CPU machine).
- **Sandbox**: Cloudflare Workers + Sandbox SDK.
- **DB**: Supabase (managed Postgres + auth + storage).
- **Vector / graph / identity**: Qdrant Cloud, Neo4j Aura, Mem0 Cloud.
- **Blobs**: Cloudflare R2.

## Data flow: a single voice turn

```
phone (PWA)
  └─ MediaRecorder captures audio while button held
  └─ WebSocket "audio_chunk" frames

FastAPI ws handler
  └─ accumulate, send to Groq Whisper on flush
  └─ → LangGraph.invoke(user_id, text)

LangGraph
  ingest → retrieve_memory → route
                                ├─ "respond" → respond
                                ├─ "tool"    → execute_tool (MCP) → respond
                                ├─ "skill"   → skill_matcher → (match? run : skill_builder → run) → respond
                                └─ "plan"    → delegate (reflection + strategy) → aggregate → respond
  → persist_memory (async)

FastAPI ws
  └─ stream text deltas back to PWA
  └─ pipe text to Kokoro TTS, stream audio frames back
  └─ PWA plays audio as it arrives
```

## The "one living conversation" mechanic

Naive approach: append every turn forever. Breaks at ~50 messages.

Our approach:

- Working memory = sliding window of last K turns (default K=20).
- Each turn, `retrieve_memory` injects 5–10 most relevant Mem0 facts and
  3–5 Qdrant hits — so even though the window is small, the *recall* feels
  infinite.
- Nightly `consolidate` job summarizes the day into Mem0 + updates Neo4j
  relationships, then prunes Qdrant entries older than N days that didn't
  cross a salience threshold.
- Result: the assistant remembers your kid's name, your last 6 months of
  product decisions, and the exact phrase you used three weeks ago — without
  burning 1M tokens per request.
