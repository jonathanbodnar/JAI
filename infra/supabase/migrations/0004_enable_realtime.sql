-- Enable Supabase Realtime on tables we want to sync across devices live.

alter publication supabase_realtime add table public.tasks;
alter publication supabase_realtime add table public.task_lists;
alter publication supabase_realtime add table public.notes;

-- Users get a metadata blob for onboarding flags + UI preferences.
alter table public.users add column if not exists metadata jsonb not null default '{}'::jsonb;
