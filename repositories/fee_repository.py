import pandas as pd

from database.client import get_supabase_client


class FeePaymentSchemaError(RuntimeError):
    pass


FEE_COLUMNS = [
    "payment_id",
    "member_id",
    "paid_at",
    "amount",
    "months",
    "valid_from",
    "valid_until",
    "grace_until",
    "source_transaction_id",
    "status",
    "note",
    "created_at",
]


def list_fee_payments() -> pd.DataFrame:
    sb = get_supabase_client()

    response = (
        sb.table("fee_payments")
        .select("*")
        .order("payment_id", desc=True)
        .execute()
    )

    df = pd.DataFrame(response.data or [])

    for col in FEE_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if df.empty:
        return pd.DataFrame(columns=FEE_COLUMNS)

    return df[FEE_COLUMNS].fillna("")


def insert_fee_payment(row: dict) -> None:
    sb = get_supabase_client()
    try:
        sb.table("fee_payments").insert(row).execute()
    except Exception as exc:
        error_message = str(exc)
        outdated_constraints = (
            "fee_payments_amount_check",
            "fee_payments_months_check",
        )
        if "23514" in error_message and any(
            constraint in error_message for constraint in outdated_constraints
        ):
            raise FeePaymentSchemaError(
                "회비 데이터베이스 설정을 업데이트해야 합니다. "
                "database/migrations/002_update_fee_payment_constraints.sql을 "
                "Supabase SQL Editor에서 실행해 주세요."
            ) from exc
        raise


def fee_exists_for_transaction(transaction_id: int) -> bool:
    sb = get_supabase_client()

    response = (
        sb.table("fee_payments")
        .select("payment_id")
        .eq("source_transaction_id", transaction_id)
        .limit(1)
        .execute()
    )

    return len(response.data or []) > 0
