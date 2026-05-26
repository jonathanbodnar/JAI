-- 0008_connected_accounts.sql
-- Purpose: support connecting multiple OAuth-backed accounts per service
-- (e.g. several Gmail mailboxes for the same JAI user). The legacy
-- `skill_credentials` row keyed by service is preserved as the active /
-- "default" account so existing skills keep working unchanged.

create table if not exists public.connected_accounts (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null references auth.users(id) on delete cascade,
    provider        text not null,                               -- 'google'
    service         text not null,                               -- 'gmail' | 'calendar' | 'drive'
    account_email   text not null,                               -- the email tied to the token
    label           text,                                        -- optional user-facing nickname
    value_encrypted text not null,                               -- Fernet token JSON
    scopes          text[] not null default '{}',
    metadata        jsonb  not null default '{}'::jsonb,
    is_default      boolean not null default false,
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (user_id, provider, service, account_email)
);

create index if not exists connected_accounts_user_service_idx
    on public.connected_accounts (user_id, service)
    where is_active;

alter table public.connected_accounts enable row level security;

create policy connected_accounts_owner on public.connected_accounts
    for all
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

-- Touch updated_at on any change.
create or replace function public._connected_accounts_touch() returns trigger as $$
begin
    new.updated_at := now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists connected_accounts_touch on public.connected_accounts;
create trigger connected_accounts_touch
    before update on public.connected_accounts
    for each row execute function public._connected_accounts_touch();

-- Only one default per (user, service). When we set one row to default, we
-- knock the others off.
create or replace function public._connected_accounts_single_default() returns trigger as $$
begin
    if new.is_default then
        update public.connected_accounts
            set is_default = false
            where user_id = new.user_id
              and service = new.service
              and id <> new.id
              and is_default;
    end if;
    return new;
end;
$$ language plpgsql;

drop trigger if exists connected_accounts_single_default on public.connected_accounts;
create trigger connected_accounts_single_default
    before insert or update of is_default on public.connected_accounts
    for each row execute function public._connected_accounts_single_default();
