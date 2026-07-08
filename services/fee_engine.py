import pandas as pd
from dateutil.relativedelta import relativedelta

from core.constants import MONTHLY_FEE, QUARTERLY_FEE, GRACE_DAYS
from repositories.fee_repository import insert_fee_payment, fee_exists_for_transaction
from repositories.member_repository import update_member
from repositories.transaction_repository import update_transaction


def get_months_from_amount(amount: int) -> int:
    if int(amount) == MONTHLY_FEE:
        return 1

    if int(amount) == QUARTERLY_FEE:
        return 3

    return 0


def calculate_membership_period(paid_at, months: int):
    paid_at = pd.to_datetime(paid_at).date()
    valid_from = paid_at.replace(day=1)

    valid_until = (
        valid_from
        + relativedelta(months=months)
        - relativedelta(days=1)
    )

    grace_until = valid_until + relativedelta(days=GRACE_DAYS)

    return valid_from, valid_until, grace_until


def apply_fee_payment(
    transaction_id: int,
    member_id: int,
    paid_at,
    amount: int,
    note: str = "",
) -> tuple[bool, str]:
    if fee_exists_for_transaction(transaction_id):
        update_transaction(
            transaction_id,
            {
                "process_status": "fee_applied",
                "matched_member_id": int(member_id),
            },
        )
        return False, "이미 회비 반영된 거래입니다."

    months = get_months_from_amount(amount)

    if months == 0:
        update_transaction(
            transaction_id,
            {
                "process_status": "need_review",
                "matched_member_id": int(member_id),
            },
        )
        return False, "회비 금액이 아닙니다."

    valid_from, valid_until, grace_until = calculate_membership_period(
        paid_at=paid_at,
        months=months,
    )

    insert_fee_payment(
        {
            "member_id": int(member_id),
            "paid_at": str(paid_at),
            "amount": int(amount),
            "months": int(months),
            "valid_from": str(valid_from),
            "valid_until": str(valid_until),
            "grace_until": str(grace_until),
            "source_transaction_id": int(transaction_id),
            "status": "confirmed",
            "note": note,
        }
    )

    update_member(
        int(member_id),
        {
            "membership_start": str(valid_from),
            "membership_end": str(valid_until),
            "grace_until": str(grace_until),
            "status": "active",
        },
    )

    update_transaction(
        transaction_id,
        {
            "process_status": "fee_applied",
            "matched_member_id": int(member_id),
            "processed_at": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        },
    )

    return True, f"{months}개월 회비 반영 완료"