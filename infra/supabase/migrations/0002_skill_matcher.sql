-- Pgvector RPC for fast skill similarity search.
-- Returns the top-N most similar active skills for a user, with cosine score.

create or replace function public.match_skills(
  query_embedding vector(3072),
  match_user_id uuid,
  match_threshold float default 0.75,
  match_count int default 5
)
returns table (
  id uuid,
  title text,
  description text,
  language text,
  source text,
  required_credentials text[],
  required_tools text[],
  inputs_schema jsonb,
  similarity float
)
language sql stable
as $$
  select
    s.id,
    s.title,
    s.description,
    s.language,
    s.source,
    s.required_credentials,
    s.required_tools,
    s.inputs_schema,
    1 - (s.description_emb <=> query_embedding) as similarity
  from public.skills s
  where s.user_id = match_user_id
    and s.is_active = true
    and s.description_emb is not null
    and 1 - (s.description_emb <=> query_embedding) > match_threshold
  order by s.description_emb <=> query_embedding
  limit match_count;
$$;

grant execute on function public.match_skills to authenticated, service_role;
