# Agents

Every "agent" in JAI is a LangGraph node with:

- a **role** (orchestrator, reflection, strategy, skill_builder, …)
- a **model slug** (resolved from `.env` via the registry)
- a **system prompt** (versioned in `apps/api/src/jai_api/graph/prompts/`)
- a **tool allow-list**

## Roles

### Orchestrator — `qwen/qwen3.7-max`

The boss. Reads the user's input + retrieved memory, decides:

- respond directly,
- call a tool (MCP),
- run a saved skill,
- generate a new skill,
- delegate to reflection or strategy,
- ask a clarifying question.

Why Qwen 3.7 Max: agent-centric design, strong tool use, 1M context, explicit
prompt caching for cheap repeated context.

### Reflection — `moonshotai/kimi-k2.6`

The "introspective twin." Engaged when the user is processing something
emotional, philosophical, or pattern-shaped ("why do I keep doing X?").
Reads long memory windows, surfaces contradictions, names patterns kindly.

Why Kimi K2.6: long-horizon coherence across months of context, multi-agent
swarm-friendly for parallel reflection.

### Strategy — `deepseek/deepseek-v4-pro`

The war-room analyst. Engaged for business decisions, scenario trees,
market/competitive analysis, org design, negotiation prep.

Why DeepSeek V4 Pro: 1.6T MoE, strong structured reasoning, 1M context for
ingesting docs, deals, financials.

### Skill Builder — `qwen/qwen3.7-max`

Writes new scripts when no MCP fits. Pairs with the sandbox executor and the
credential prompt flow. Saves successful runs to the skill registry.

### Fast — `deepseek/deepseek-v4-flash:free`

Background jobs: summarization, embedding selection, salience scoring,
title generation, etc. Free tier on OpenRouter, fine for throughput tasks.

## Switching models

Every role reads from env at startup:

```bash
JAI_MODEL_ORCHESTRATOR=qwen/qwen3.7-max
JAI_MODEL_REFLECTION=moonshotai/kimi-k2.6
JAI_MODEL_STRATEGY=deepseek/deepseek-v4-pro
JAI_MODEL_SKILL_BUILDER=qwen/qwen3.7-max
JAI_MODEL_FAST=deepseek/deepseek-v4-flash:free
```

Drop in any OpenRouter slug. No code change required.
