-- ============================================================================
-- JAI initial schema
-- ============================================================================
-- Conventions:
--   * uuid PKs with gen_random_uuid()
--   * snake_case
--   * RLS on every user-scoped table; policy: owner-only
--   * timestamps in UTC, app converts on display
-- ============================================================================

create extension if not exists "pgcrypto";
create extension if not exists "vector";

-- ---------------------------------------------------------------------------
-- Users (mirror of auth.users with app-side fields)
-- ---------------------------------------------------------------------------
create table public.users (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text not null,
  display_name text,
  timezone    text default 'UTC',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- The single living conversation per user
-- ---------------------------------------------------------------------------
create table public.conversations (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.users(id) on delete cascade,
  -- 'primary' is the single living conversation; future-proof for sub-threads
  kind        text not null default 'primary' check (kind in ('primary','sub')),
  parent_id   uuid references public.conversations(id) on delete set null,
  title       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index conversations_one_primary_per_user
  on public.conversations(user_id) where kind = 'primary';

create table public.messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  user_id         uuid not null references public.users(id) on delete cascade,
  role            text not null check (role in ('user','assistant','system','tool','reflection')),
  content         text not null,
  audio_url       text,                            -- R2 url if voice
  tool_calls      jsonb,
  tool_results    jsonb,
  model           text,                            -- which model produced this
  tokens_in       int,
  tokens_out      int,
  latency_ms      int,
  metadata        jsonb default '{}'::jsonb,
  created_at      timestamptz not null default now()
);
create index messages_conv_created on public.messages(conversation_id, created_at desc);
create index messages_user_created on public.messages(user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Tasks (Google Tasks–style)
-- ---------------------------------------------------------------------------
create table public.task_lists (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.users(id) on delete cascade,
  title       text not null,
  position    int not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table public.tasks (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.users(id) on delete cascade,
  list_id       uuid not null references public.task_lists(id) on delete cascade,
  parent_id     uuid references public.tasks(id) on delete cascade,
  title         text not null,
  notes         text,
  status        text not null default 'needsAction' check (status in ('needsAction','completed')),
  due           timestamptz,
  position      text,                              -- lexicographic ordering
  completed_at  timestamptz,
  source        text default 'jai' check (source in ('jai','agent','voice')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index tasks_user_list on public.tasks(user_id, list_id);
create index tasks_user_status on public.tasks(user_id, status, due);

-- ---------------------------------------------------------------------------
-- Notes (Google Keep–style)
-- ---------------------------------------------------------------------------
create table public.notes (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.users(id) on delete cascade,
  title       text,
  body        text,                                -- markdown
  color       text default 'default',
  pinned      bool not null default false,
  archived    bool not null default false,
  labels      text[] default '{}',
  reminders   jsonb default '[]'::jsonb,
  checklist   jsonb,                               -- [{text, checked}]
  source      text default 'jai' check (source in ('jai','agent','voice')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index notes_user_updated on public.notes(user_id, updated_at desc);

-- ---------------------------------------------------------------------------
-- Skills (Cursor-pattern: agent writes once, reuses forever)
-- ---------------------------------------------------------------------------
create table public.skills (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references public.users(id) on delete cascade,
  title                 text not null,
  description           text not null,
  description_emb       vector(3072),
  language              text not null check (language in ('python','typescript','bash')),
  source                text not null,
  required_credentials  text[] default '{}',
  required_tools        text[] default '{}',
  inputs_schema         jsonb,
  run_count             int default 0,
  last_run_at           timestamptz,
  last_run_status       text,
  is_active             bool not null default true,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index skills_user_active on public.skills(user_id) where is_active = true;
-- Note: pgvector HNSW/IVFFlat max 2000 dims; text-embedding-3-large is 3072.
-- Sequential scan is used instead (fine for a personal skills table of <1000 rows).

create table public.skill_runs (
  id              uuid primary key default gen_random_uuid(),
  skill_id        uuid not null references public.skills(id) on delete cascade,
  user_id         uuid not null references public.users(id) on delete cascade,
  conversation_id uuid references public.conversations(id) on delete set null,
  inputs          jsonb,
  output          jsonb,
  status          text not null check (status in ('running','ok','error','cancelled')),
  error           text,
  stdout          text,
  stderr          text,
  duration_ms     int,
  started_at      timestamptz not null default now(),
  finished_at     timestamptz
);
create index skill_runs_skill_started on public.skill_runs(skill_id, started_at desc);

-- ---------------------------------------------------------------------------
-- MCP connections + per-skill credentials (encrypted at app layer)
-- ---------------------------------------------------------------------------
create table public.mcp_connections (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.users(id) on delete cascade,
  name         text not null,                      -- e.g. 'gmail', 'linear'
  transport    text not null check (transport in ('stdio','http','sse')),
  url          text,
  config       jsonb default '{}'::jsonb,
  is_active    bool not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique(user_id, name)
);

create table public.skill_credentials (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users(id) on delete cascade,
  key             text not null,
  value_encrypted bytea not null,
  metadata        jsonb default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique(user_id, key)
);

-- ---------------------------------------------------------------------------
-- Audit log (every agent action that touched the outside world)
-- ---------------------------------------------------------------------------
create table public.audit_log (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.users(id) on delete cascade,
  actor       text not null,                       -- 'user' | 'agent:<role>'
  action      text not null,                       -- 'mcp.gmail.send', 'skill.run', etc.
  target      text,
  payload     jsonb default '{}'::jsonb,
  ok          bool not null,
  error       text,
  created_at  timestamptz not null default now()
);
create index audit_log_user_created on public.audit_log(user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- RLS — owner only on everything
-- ---------------------------------------------------------------------------
alter table public.users               enable row level security;
alter table public.conversations       enable row level security;
alter table public.messages            enable row level security;
alter table public.task_lists          enable row level security;
alter table public.tasks               enable row level security;
alter table public.notes               enable row level security;
alter table public.skills              enable row level security;
alter table public.skill_runs          enable row level security;
alter table public.mcp_connections     enable row level security;
alter table public.skill_credentials   enable row level security;
alter table public.audit_log           enable row level security;

do $$ begin
  -- owner-only policies
  perform 1;
end $$;

create policy users_self on public.users
  for all using (auth.uid() = id) with check (auth.uid() = id);

create policy convs_owner on public.conversations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy msgs_owner on public.messages
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy task_lists_owner on public.task_lists
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy tasks_owner on public.tasks
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy notes_owner on public.notes
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy skills_owner on public.skills
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy skill_runs_owner on public.skill_runs
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy mcp_owner on public.mcp_connections
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy creds_owner on public.skill_credentials
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy audit_owner on public.audit_log
  for select using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Trigger: ensure every new auth user gets a public.users row + primary convo
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, email, display_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email,'@',1)));

  insert into public.conversations (user_id, kind, title)
  values (new.id, 'primary', 'JAI');

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ---------------------------------------------------------------------------
-- updated_at touch
-- ---------------------------------------------------------------------------
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

do $$
declare t text;
begin
  for t in select unnest(array[
    'users','conversations','task_lists','tasks','notes',
    'skills','mcp_connections','skill_credentials'
  ]) loop
    execute format(
      'drop trigger if exists touch_updated_at on public.%I;
       create trigger touch_updated_at before update on public.%I
         for each row execute procedure public.touch_updated_at();', t, t);
  end loop;
end $$;
