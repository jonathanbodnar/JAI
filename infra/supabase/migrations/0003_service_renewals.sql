-- Service renewals — what the user pays for, when it renews, where the dashboard is.
-- Lets the Status panel show subscription cost + renewal date for services that
-- don't have a public usage API.

create table public.service_renewals (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references public.users(id) on delete cascade,
  service          text not null,                  -- 'openrouter','supabase','mem0',...
  display_name     text not null,
  monthly_cost_usd numeric(10,2),
  renews_at        date,                           -- next billing date
  dashboard_url    text,
  api_key_present  boolean not null default false, -- whether we have an API key configured
  notes            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique(user_id, service)
);
create index service_renewals_user on public.service_renewals(user_id, service);

alter table public.service_renewals enable row level security;
create policy renewals_owner on public.service_renewals
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop trigger if exists touch_updated_at on public.service_renewals;
create trigger touch_updated_at before update on public.service_renewals
  for each row execute procedure public.touch_updated_at();
