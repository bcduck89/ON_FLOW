from datetime import date
import pandas as pd
from dateutil.relativedelta import relativedelta

from core.constants import GRACE_DAYS
from repositories.fee_repository import insert_fee_payment
from repositories.member_repository import update_member
from services.fee_engine import get_months_from_amount


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


def register_fee_payment(
    member_id: int,
    paid_at,
    amount: int,
    source_transaction_id=None,
    note: str = "",
) -> None:
    months = get_months_from_amount(amount)

    if months == 0:
        raise ValueError("회비 금액은 2,000원 단위로 입력해야 합니다.")

    valid_from, valid_until, grace_until = calculate_membership_period(
        paid_at,
        months,
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
            "source_transaction_id": source_transaction_id,
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
