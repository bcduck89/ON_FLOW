import pandas as pd

from database.client import get_supabase_client


TRANSACTION_COLUMNS = [
    "transaction_id",
    "transaction_hash",
    "transaction_datetime",
    "transaction_date",
    "transaction_time",
    "direction",
    "amount",
    "balance",
    "transaction_type",
    "description",
    "memo",
    "category",
    "confirm_status",
    "bank_name",
    "process_status",
    "matched_member_id",
    "processed_at",
]


def list_transactions() -> pd.DataFrame:
    sb = get_supabase_client()

    response = (
        sb.table("transactions")
        .select("*")
        .order("transaction_id", desc=True)
        .execute()
    )

    df = pd.DataFrame(response.data or [])

    for col in TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if df.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)

    return df[TRANSACTION_COLUMNS].fillna("")


def get_existing_hashes() -> set[str]:
    sb = get_supabase_client()

    response = (
        sb.table("transactions")
        .select("transaction_hash")
        .execute()
    )

    return {
        str(row["transaction_hash"])
        for row in response.data or []
        if row.get("transaction_hash")
    }


def insert_transactions(rows: list[dict]) -> None:
    if not rows:
        return

    sb = get_supabase_client()
    sb.table("transactions").insert(rows).execute()


def update_transaction(transaction_id: int, values: dict) -> None:
    sb = get_supabase_client()
    sb.table("transactions").update(values).eq("transaction_id", transaction_id).execute()
    
def list_reprocessable_transactions() -> pd.DataFrame:
    sb = get_supabase_client()

    response = (
        sb.table("transactions")
        .select("*")
        .in_("process_status", ["unmatched", "uploaded", "need_review"])
        .execute()
    )

    df = pd.DataFrame(response.data or [])

    for col in TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if df.empty:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)

    return df[TRANSACTION_COLUMNS].fillna("")