begin;

alter table public.regular_runs
add column if not exists attendee_names text[] not null default '{}';

commit;
