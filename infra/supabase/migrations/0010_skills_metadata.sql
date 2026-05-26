-- 0010_skills_metadata.sql
-- Purpose: let library-seeded skills tag themselves so subsequent
-- re-seeds can update in place (and the UI can show "from library"
-- vs "user-created") without name-matching.

alter table public.skills
    add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists skills_metadata_library_key_idx
    on public.skills ((metadata->>'library_key'))
    where (metadata->>'library_key') is not null;
