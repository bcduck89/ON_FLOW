import pandas as pd

from core.constants import TRANSACTION_STATUS
from repositories.transaction_repository import list_transactions
from repositories.member_repository import list_members


def get_transaction_list() -> pd.DataFrame:
    df = list_transactions()

    if df.empty:
        return df

    members = list_members()

    member_name_map = {}

    if not members.empty:
        member_name_map = dict(
            zip(
                members["member_id"].astype(int),
                members["name"],
            )
        )


    df = df.copy()

    df["회원"] = (
        pd.to_numeric(
            df["matched_member_id"],
            errors="coerce",
        )
        .astype("Int64")
        .map(member_name_map)
        .fillna("")
    )

    df["처리상태"] = (
        df["process_status"]
        .map(TRANSACTION_STATUS)
        .fillna(df["process_status"])
    )

    view = df.rename(
        columns={
            "transaction_id": "거래ID",
            "transaction_datetime": "거래일시",
            "transaction_date": "거래일",
            "transaction_time": "시간",
            "direction": "입출금",
            "amount": "금액",
            "balance": "잔액",
            "transaction_type": "거래구분",
            "description": "내용",
            "memo": "메모",
            "category": "분류",
            "confirm_status": "확인상태",
            "bank_name": "은행",
        }
    )

    display_cols = [
        "거래ID",
        "거래일시",
        "입출금",
        "금액",
        "잔액",
        "내용",
        "회원",
        "은행",
        "처리상태",
    ]

    return view[display_cols]