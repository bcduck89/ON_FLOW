import pandas as pd

from database.client import get_supabase_client


MEMBER_COLUMNS = [
    "member_id",
    "member_code",
    "member_type",
    "name",
    "nickname",
    "age",
    "gender",
    "city",
    "district",
    "deposit_name",
    "joined_at",
    "membership_start",
    "membership_end",
    "grace_until",
    "status",
    "memo",
]


def list_members() -> pd.DataFrame:
    sb = get_supabase_client()

    response = (
        sb.table("members")
        .select("*")
        .order("member_id", desc=False)
        .execute()
    )

    data = response.data or []
    df = pd.DataFrame(data)

    for col in MEMBER_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    if df.empty:
        return pd.DataFrame(columns=MEMBER_COLUMNS)

    return df[MEMBER_COLUMNS].fillna("")


def insert_member(row: dict) -> None:
    sb = get_supabase_client()
    sb.table("members").insert(row).execute()


def update_member(member_id: int, values: dict) -> None:
    sb = get_supabase_client()
    sb.table("members").update(values).eq("member_id", member_id).execute()


def delete_member(member_id: int) -> None:
    sb = get_supabase_client()
    sb.table("members").delete().eq("member_id", member_id).execute()