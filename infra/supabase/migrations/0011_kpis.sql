-- Living KPIs: small numbers the user pins to the top of the app.
-- Updated manually, by skills, or by scheduled jobs.

create table if not exists public.kpis (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references auth.users(id) on delete cascade,

    -- machine-friendly slug, e.g. "mrr", "active_users", "open_invoices".
    -- Skills key off this to upsert.
    key           text not null,

    label         text not null,
    -- value is stored as text so we can hold "$48,250", "12.4%", "3d 4h"
    -- without losing the display format. Numeric work happens in skills.
    value         text not null default '—',
    -- optional pre-formatted "previous value" used to render a trend
    -- arrow in the UI. Stored verbatim too.
    previous      text,
    -- semantic format hint for the renderer.
    format        text not null default 'raw' check (format in ('raw','number','currency','percent','duration')),
    unit          text,
    icon          text,
    color         text,
    source        text not null default 'manual',
    sort_order    int  not null default 0,
    is_visible    boolean not null default true,

    -- short rolling history (last N samples) for sparkline / "since".
    history       jsonb not null default '[]'::jsonb,

    last_updated_at timestamptz not null default now(),
    created_at    timestamptz not null default now(),

    unique (user_id, key)
);

create index if not exists kpis_user_visible_idx
    on public.kpis(user_id, is_visible, sort_order);

alter table public.kpis enable row level security;

drop policy if exists "kpis self read" on public.kpis;
create policy "kpis self read"
    on public.kpis for select
    using (auth.uid() = user_id);

drop policy if exists "kpis self write" on public.kpis;
create policy "kpis self write"
    on public.kpis for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- Realtime so the header pills react instantly when a skill upserts a
-- value from the sandbox.
alter publication supabase_realtime add table public.kpis;
