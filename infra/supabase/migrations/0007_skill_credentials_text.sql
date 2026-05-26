-- 0007_skill_credentials_text.sql
-- Fernet output is already URL-safe base64 ASCII, so switch the column from
-- `bytea` to `text` to make PostgREST/JSON round-trips trivial. Existing rows
-- are converted in place.
alter table public.skill_credentials
    alter column value_encrypted type text
    using convert_from(value_encrypted, 'UTF8');
