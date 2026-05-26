-- 0009_data_sources.sql
-- Purpose: connect external data sources (other Supabase projects, etc.)
-- so JAI skills can query them with auto-injected credentials. Distinct
-- from `connected_accounts` because OAuth-shaped fields (account_email,
-- scopes) don't apply — these are raw URL + service key pairs.

create table if not exists public.data_sources (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    kind            text not null,                               -- 'supabase' (extensible: 'postgres','mysql', etc.)
    slug            text not null,                               -- machine-safe name e.g. 'shoutout'
    label           text not null,                               -- human-friendly name e.g. 'Shoutout'
    url             text not null,                               -- e.g. 'https://abc.supabase.co'
    key_encrypted   text not null,                               -- Fernet-encrypted service role key
    metadata        jsonb  not null default '{}'::jsonb,
    is_active       boolean not null default true,
    last_tested_at  timestamptz,
    last_test_ok    boolean,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (user_id, kind, slug)
);

create index if not exists data_sources_user_active_idx
    on public.data_sources (user_id, kind)
    where is_active;

alter table public.data_sources enable row level security;

create policy data_sources_owner on public.data_sources
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create or replace function public._data_sources_touch() returns trigger as $$
begin
    new.updated_at := now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists data_sources_touch on public.data_sources;
create trigger data_sources_touch
    before update on public.data_sources
    for each row execute function public._data_sources_touch();
