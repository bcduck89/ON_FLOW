-- ON_FLOW 러닝 활동 기록
-- Supabase Dashboard > SQL Editor에서 전체를 한 번 실행하세요.

create table if not exists public.running_activities (
    activity_id bigint generated always as identity primary key,
    name text not null check (char_length(name) between 1 and 80),
    run_date date not null,
    started_at timestamptz,
    ended_at timestamptz,
    duration_seconds integer check (duration_seconds is null or duration_seconds >= 0),
    distance_km numeric(8, 2) not null check (distance_km >= 0),
    elevation_gain_m numeric(10, 0) not null default 0 check (elevation_gain_m >= 0),
    point_count integer not null check (point_count between 2 and 100000),
    paths jsonb not null check (
        jsonb_typeof(paths) = 'array'
        and jsonb_array_length(paths) between 1 and 100
    ),
    location_name text not null default '' check (char_length(location_name) <= 100),
    description text not null default '' check (char_length(description) <= 500),
    tags text[] not null default '{}',
    source_hash text not null unique check (char_length(source_hash) = 64),
    uploaded_by text not null check (char_length(uploaded_by) between 1 and 80),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (ended_at is null or started_at is null or ended_at >= started_at)
);

create index if not exists running_activities_run_date_idx
on public.running_activities (run_date desc);

create index if not exists running_activities_tags_idx
on public.running_activities using gin (tags);

create or replace function public.set_running_activity_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists running_activities_set_updated_at
on public.running_activities;

create trigger running_activities_set_updated_at
before update on public.running_activities
for each row
execute function public.set_running_activity_updated_at();

alter table public.running_activities enable row level security;

drop policy if exists "Public can view running activities"
on public.running_activities;

create policy "Public can view running activities"
on public.running_activities
for select
to anon, authenticated
using (true);

-- 공개 키는 조회만 허용합니다. 등록은 Streamlit 서버에만 보관한
-- SUPABASE_SERVICE_ROLE_KEY를 사용하고, 앱의 관리자 세션에서만 호출합니다.
revoke insert, update, delete on public.running_activities from anon, authenticated;
grant select on public.running_activities to anon, authenticated;
