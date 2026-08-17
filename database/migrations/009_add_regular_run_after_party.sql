begin;

alter table public.regular_runs
    add column if not exists after_party text not null default '없음';

update public.regular_runs
set after_party = '없음'
where after_party is null
   or after_party not in ('카페', '식사', '없음');

alter table public.regular_runs
    drop constraint if exists regular_runs_after_party_check;

alter table public.regular_runs
    add constraint regular_runs_after_party_check
    check (after_party in ('카페', '식사', '없음'));

comment on column public.regular_runs.after_party is
    '러닝 후 뒷풀이 구분: 카페, 식사, 없음';

commit;
