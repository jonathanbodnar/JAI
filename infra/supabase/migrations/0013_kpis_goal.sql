-- KPI goals: track progress toward a target.
--
-- The header pill renders "27/300" (current/goal) with a thin progress
-- bar when a goal is set. Stored as text just like `value` so we can
-- keep "$1,200" vs "1200" formatting symmetry — numeric work happens
-- in the UI/skills.

alter table public.kpis
    add column if not exists goal text;
