-- Ingested context documents — one row per file uploaded via /context/ingest.
-- The actual semantic vectors live in Qdrant and the identity facts live in
-- Mem0; this table is purely the "library" view so users can see what they've
-- fed the system.

create table public.documents (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references public.users(id) on delete cascade,
  filename             text not null,
  size_bytes           bigint,
  content_type         text,
  kind                 text not null default 'document',     -- 'document' | 'chatgpt_export'
  chunks_count         int  not null default 0,
  conversations_count  int  not null default 0,
  facts_count          int  not null default 0,
  metadata             jsonb,
  created_at           timestamptz not null default now()
);
create index documents_user on public.documents(user_id, created_at desc);

alter table public.documents enable row level security;
create policy documents_owner on public.documents
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Realtime so newly-ingested files appear instantly.
alter publication supabase_realtime add table public.documents;
