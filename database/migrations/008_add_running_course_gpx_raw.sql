-- 기존 running_activities 테이블에 GPX 원문 보관 컬럼을 추가합니다.
-- Supabase Dashboard > SQL Editor에서 전체를 한 번 실행하세요.

alter table public.running_activities
    add column if not exists gpx_raw_base64 text,
    add column if not exists gpx_filename text,
    add column if not exists gpx_size_bytes integer;

comment on column public.running_activities.gpx_raw_base64 is
    '업로드된 GPX 파일 원문을 손실 없이 복원하기 위한 Base64 문자열';
comment on column public.running_activities.gpx_filename is
    '업로드 당시 GPX 파일명';
comment on column public.running_activities.gpx_size_bytes is
    '업로드 당시 GPX 파일 크기(byte)';

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'running_activities_gpx_filename_check'
          and conrelid = 'public.running_activities'::regclass
    ) then
        alter table public.running_activities
            add constraint running_activities_gpx_filename_check
            check (
                gpx_filename is null
                or char_length(gpx_filename) between 1 and 255
            );
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conname = 'running_activities_gpx_size_bytes_check'
          and conrelid = 'public.running_activities'::regclass
    ) then
        alter table public.running_activities
            add constraint running_activities_gpx_size_bytes_check
            check (
                gpx_size_bytes is null
                or gpx_size_bytes between 1 and 5242880
            );
    end if;
end
$$;
