begin;

alter table public.fee_payments
drop constraint if exists fee_payments_amount_check;

alter table public.fee_payments
drop constraint if exists fee_payments_months_check;

alter table public.fee_payments
add constraint fee_payments_amount_check
check (amount > 0 and amount % 2000 = 0);

alter table public.fee_payments
add constraint fee_payments_months_check
check (months > 0 and amount = months * 2000);

commit;
