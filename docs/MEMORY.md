# Memory

Four-tier memory. Every tier is managed in the cloud — zero ops.

## 1. Working memory (LangGraph state)

Lives only for the current turn. Holds:

- last K turns (K=20 by default)
- retrieved Mem0 facts (top 5–10)
- retrieved Qdrant hits (top 3–5)
- retrieved Neo4j subgraph (1-hop around mentioned entities)
- current task/skill context

Wiped between turns (LangGraph checkpoint persists it but each invocation
rebuilds it from the long-term stores, so changing retrieval logic doesn't
poison old state).

## 2. Identity memory (Mem0 Cloud)

What it stores: **facts about you**. Not transcripts. Distilled.

Examples:

- "Jonathan's first kid is named X"
- "Jonathan prefers concise, direct responses"
- "Jonathan's company is JAI, currently pre-revenue"
- "Jonathan repeatedly avoids hard product conversations on Mondays"
- "Jonathan considers shipping > polish"

Writes happen in `persist_memory` after every meaningful turn, using Mem0's
extraction pipeline. Reads happen in `retrieve_memory` via semantic search
with the current turn as query.

## 3. Semantic memory (Qdrant Cloud)

What it stores: **everything raw**, embedded.

- full conversation transcripts (one point per message)
- voice note transcriptions
- ingested docs (PDFs, Notion exports, etc.)
- screenshots (with OCR + caption)
- meeting notes
- web pages saved to JAI

Collection: `jai_memory`. Embedding: `openai/text-embedding-3-large` via
OpenRouter, 3072 dim. Metadata: `{user_id, source, created_at, type,
conversation_id, salience}`.

## 4. Relational memory (Neo4j Aura)

What it stores: **the graph of you**.

Node labels:

- `Person` — humans you mention (with relationship type)
- `Company` — orgs (yours + others)
- `Project` — multi-week initiatives
- `Decision` — choices you made, with date + rationale + outcome
- `Belief` — your stated worldviews (track contradictions over time)
- `Pattern` — recurring behaviors the system has noticed
- `Skill` — saved skills (linked here for graph queries)
- `Conversation` — a logical "session" (boundary set by silence > 6h)

Relationships:

- `(:Person)-[:WORKS_AT]->(:Company)`
- `(:Person)-[:REPORTS_TO]->(:Person)`
- `(:Decision)-[:RESULTED_IN]->(:Outcome)`
- `(:Decision)-[:CONTRADICTS]->(:Decision)`
- `(:Belief)-[:UPDATED_BY]->(:Conversation)`
- `(:Pattern)-[:OBSERVED_IN]->(:Conversation)`

Writes: `persist_memory` upserts nodes for any named entity, plus
LLM-extracted edges. Nightly `consolidate` job tightens the graph and flags
contradictions for the next reflection turn.

## App state (Supabase Postgres)

Not "memory" in the AI sense; this is the boring operational DB:

- `users`, `conversations`, `messages`, `tasks`, `notes`, `skills`,
  `skill_runs`, `mcp_connections`, `skill_credentials` (encrypted),
  `audit_log`.
- Also hosts the LangGraph Postgres checkpointer.

## Consolidation (nightly)

A cron-triggered LangGraph subflow runs at 03:00 user-local time:

1. Pull the day's conversations.
2. Ask Fast model for a 200-word "what mattered today" summary.
3. Extract new Mem0 facts.
4. Upsert any new Neo4j entities + relationships.
5. Score salience for every Qdrant point added in the last 7 days; delete
   anything below threshold that hasn't been re-retrieved.
6. Run reflection pass: ask Kimi to surface any contradictions or patterns
   in the last 30 days, write the answer as a new "reflection" message in
   the user's conversation so they see it next morning.
