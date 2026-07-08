import pandas as pd

from database.client import get_supabase_client


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
    sb.table("fee_payments").insert(row).execute()


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