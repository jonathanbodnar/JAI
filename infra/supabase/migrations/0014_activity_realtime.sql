-- 0014_activity_realtime.sql
--
-- Add `skill_runs` to the Realtime publication so the bottom-left
-- "Recent" ribbon in the chat updates instantly when a skill
-- finishes. tasks/notes/kpis/messages are already in the publication
-- via earlier migrations; this just rounds out the activity feed.
--
-- Idempotent: ALTER PUBLICATION will error if the table is already
-- a member, so we check first.

do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'skill_runs'
  ) then
    alter publication supabase_realtime add table public.skill_runs;
  end if;
end
$$;
