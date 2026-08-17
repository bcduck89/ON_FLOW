begin;

-- 처음 설치하는 프로젝트와 기존 005/006 적용 프로젝트에서 모두 실행할 수 있습니다.
create table if not exists public.regular_runs (
    regular_run_id bigint generated always as identity primary key,
    run_type text not null default '정기',
    title text not null check (char_length(title) between 1 and 100),
    run_date date not null,
    start_time time,
    location text not null default '' check (char_length(location) <= 150),
    course_name text not null default '' check (char_length(course_name) <= 150),
    distance_km numeric(8, 2) not null default 0 check (distance_km >= 0),
    target_pace text not null default '' check (char_length(target_pace) <= 50),
    after_party text not null default '없음',
    participant_count integer not null default 0 check (participant_count >= 0),
    attendee_names text[] not null default '{}',
    memo text not null default '' check (char_length(memo) <= 500),
    source_image_name text not null default '' check (char_length(source_image_name) <= 255),
    source_image_bucket text not null default 'regular-run-captures',
    source_image_path text,
    source_image_mime_type text,
    source_image_size integer,
    raw_ocr_text text not null default '' check (char_length(raw_ocr_text) <= 10000),
    source_hash text not null unique check (char_length(source_hash) = 64),
    created_by text not null check (char_length(created_by) between 1 and 80),
    created_at timestamptz not null default now()
);

alter table public.regular_runs
    add column if not exists run_type text not null default '정기',
    add column if not exists attendee_names text[] not null default '{}',
    add column if not exists source_image_bucket text not null default 'regular-run-captures',
    add column if not exists source_image_path text,
    add column if not exists source_image_mime_type text,
    add column if not exists source_image_size integer,
    add column if not exists after_party text not null default '없음';

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'regular_runs_after_party_check'
          and conrelid = 'public.regular_runs'::regclass
    ) then
        alter table public.regular_runs
            add constraint regular_runs_after_party_check
            check (after_party in ('카페', '식사', '없음'));
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'regular_runs_run_type_check'
          and conrelid = 'public.regular_runs'::regclass
    ) then
        alter table public.regular_runs
            add constraint regular_runs_run_type_check
            check (run_type in ('정기', '자유'));
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'regular_runs_source_image_size_check'
          and conrelid = 'public.regular_runs'::regclass
    ) then
        alter table public.regular_runs
            add constraint regular_runs_source_image_size_check
            check (source_image_size is null or source_image_size between 1 and 10485760);
    end if;
end
$$;

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

-- 참석자 캡처는 개인 정보가 포함될 수 있으므로 공개하지 않습니다.
insert into storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
values (
    'regular-run-captures',
    'regular-run-captures',
    false,
    10485760,
    array['image/png', 'image/jpeg', 'image/webp']
)
on conflict (id) do update
set
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

commit;

-- 앱은 Streamlit secrets의 SUPABASE_SECRET_KEY(또는 SERVICE_ROLE_KEY)로만
-- 이 비공개 버킷에 접근하므로 storage.objects 공개 정책은 만들지 않습니다.
