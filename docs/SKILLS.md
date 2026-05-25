# Skills

A **skill** is a saved, reusable script the agent wrote for you once and can
run again without re-thinking.

## Lifecycle

```
User: "Email the people I met last week and ask for follow-up calls."
  │
  ▼
Orchestrator → Skill Matcher (embedding search over skills.description_emb)
  │
  ├─ Match found (cos sim > 0.85)
  │    └─ Run saved skill with extracted inputs → respond
  │
  └─ No match
       └─ Skill Builder (Qwen 3.7 Max)
            ├─ Plan: "I need Gmail access + calendar last-7-days. Do I have creds?"
            ├─ Ask user (only for missing creds)
            ├─ Write script (TS or Python)
            ├─ Run in Cloudflare Sandbox SDK
            ├─ On success:
            │    save to `skills` table with:
            │      - title, description, description_emb
            │      - language, source code
            │      - required_credentials, required_tools
            │      - run history
            │    link in Neo4j: (:Skill)-[:USED_FOR]->(:Intent)
            └─ Respond with result + "saved this as skill X for next time"
```

## Storage (Supabase)

```sql
create table skills (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id),
  title text not null,
  description text not null,
  description_emb vector(3072),         -- pgvector
  language text not null check (language in ('python','typescript','bash')),
  source text not null,
  required_credentials text[] default '{}',
  required_tools text[] default '{}',
  inputs_schema jsonb,                  -- JSON Schema for the inputs
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  run_count int default 0,
  last_run_at timestamptz,
  last_run_status text
);

create table skill_runs (
  id uuid primary key default gen_random_uuid(),
  skill_id uuid not null references skills(id),
  conversation_id uuid not null references conversations(id),
  inputs jsonb,
  output jsonb,
  status text not null,
  error text,
  started_at timestamptz default now(),
  finished_at timestamptz
);

create table skill_credentials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id),
  key text not null,                    -- e.g. 'gmail_oauth_token'
  value_encrypted bytea not null,       -- encrypted with KMS/age
  created_at timestamptz default now(),
  unique(user_id, key)
);
```

## Sandbox contract

Skill scripts run inside a Cloudflare Sandbox SDK container with:

- network egress
- `/workspace` as cwd
- env vars injected from `skill_credentials` (only those declared in
  `required_credentials`)
- 5-minute wall clock by default (configurable per skill)
- structured stdout: skills must end with a single JSON line
  `{"status":"ok","result":...}` or `{"status":"error","error":...}`

## Safety

- Skills cannot read other skills' credentials.
- Network egress is logged and shown in `audit_log`.
- Destructive operations (deletes, sends, payments) require a `confirm:true`
  flag set by the user voice/text reply before execution.
- The user can revoke any skill in the Skills panel; it's soft-deleted but
  the source is kept for forensics.
