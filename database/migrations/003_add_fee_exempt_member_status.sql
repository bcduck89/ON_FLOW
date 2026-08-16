begin;

alter table public.members
drop constraint if exists members_status_check;

alter table public.members
add constraint members_status_check
check (status in ('active', 'grace', 'fee_exempt', 'withdrawn'));

comment on column public.members.status is
'회원 상태: active(활동), grace(납부유예), fee_exempt(납부예외), withdrawn(탈퇴)';

commit;
