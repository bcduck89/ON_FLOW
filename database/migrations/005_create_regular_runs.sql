begin;

create table if not exists public.regular_runs (
    regular_run_id bigint generated always as identity primary key,
    title text not null check (char_length(title) between 1 and 100),
    run_date date not null,
    start_time time,
    location text not null default '' check (char_length(location) <= 150),
    course_name text not null default '' check (char_length(course_name) <= 150),
    distance_km numeric(8, 2) not null default 0 check (distance_km >= 0),
    target_pace text not null default '' check (char_length(target_pace) <= 50),
    participant_count integer not null default 0 check (participant_count >= 0),
    memo text not null default '' check (char_length(memo) <= 500),
    source_image_name text not null default '' check (char_length(source_image_name) <= 255),
    raw_ocr_text text not null default '' check (char_length(raw_ocr_text) <= 10000),
    source_hash text not null unique check (char_length(source_hash) = 64),
    created_by text not null check (char_length(created_by) between 1 and 80),
    created_at timestamptz not null default now()
);

create index if not exists regular_runs_run_date_idx
on public.regular_runs (run_date desc, start_time desc);

alter table public.regular_runs enable row level security;

drop policy if exists "Public can view regular runs"
on public.regular_runs;

create policy "Public can view regular runs"
on public.regular_runs
for select
to anon, authenticated
using (true);

revoke insert, update, delete on public.regular_runs from anon, authenticated;
grant select on public.regular_runs to anon, authenticated;

commit;
