-- ============================================================================
-- Scheduled Actions — user-defined recurring automations
-- ============================================================================
-- Each row represents one recurring job. The nightly consolidation job
-- (POST /jobs/consolidate) picks up every row whose next_run_at <= now()
-- and enabled = true, executes it, and advances next_run_at.
--
-- Two execution modes:
--   builtin_name  → run a named built-in function (e.g. "task_summary")
--   skill_id      → execute a saved skill via the sandbox
-- ============================================================================

create table public.scheduled_actions (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.users(id) on delete cascade,

  -- Human-readable description (what JAI shows in the Automations UI)
  description  text not null,

  -- Frequency: how often to run
  frequency    text not null default 'daily'
               check (frequency in ('hourly','daily','weekdays','weekly','monthly')),

  -- Time of day (UTC hour 0–23) the action should fire
  hour_utc     smallint not null default 6 check (hour_utc between 0 and 23),

  -- For weekly frequency: 0=Sun, 1=Mon ... 6=Sat (null = any day)
  day_of_week  smallint check (day_of_week between 0 and 6),

  -- What to run (exactly one should be non-null, or neither = description only)
  skill_id     uuid references public.skills(id) on delete set null,
  builtin_name text,                              -- e.g. 'task_summary'
  skill_inputs jsonb not null default '{}',

  enabled      bool not null default true,

  -- Execution tracking
  last_run_at  timestamptz,
  next_run_at  timestamptz not null default now(),
  last_result  text,
  last_status  text check (last_status in ('ok','error','skipped')),
  run_count    int not null default 0,

  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

alter table public.scheduled_actions enable row level security;

create policy "scheduled_actions_owner"
  on public.scheduled_actions for all
  using  (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- Index used by the cron runner to find due actions efficiently
create index scheduled_actions_user_due
  on public.scheduled_actions (user_id, enabled, next_run_at);

-- Auto-touch updated_at on every update
create trigger touch_updated_at
  before update on public.scheduled_actions
  for each row execute procedure public.touch_updated_at();
