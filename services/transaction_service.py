import pandas as pd

from core.constants import TRANSACTION_STATUS
from repositories.transaction_repository import list_transactions
from repositories.member_repository import list_members


TRANSACTION_DISPLAY_COLUMNS = [
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
DEPOSIT_DISPLAY_COLUMNS = [
    column for column in TRANSACTION_DISPLAY_COLUMNS if column != "잔액"
]


def get_transaction_list() -> pd.DataFrame:
    df = list_transactions()

    if df.empty:
        return pd.DataFrame(columns=TRANSACTION_DISPLAY_COLUMNS)

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

    return view[TRANSACTION_DISPLAY_COLUMNS]


def split_fee_transactions(
    transactions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """거래 목록을 회비 입금과 회비 사용(출금) 목록으로 나눈다."""
    if transactions.empty:
        expense_columns = ["거래ID", "거래일시", "사용금액", "잔액", "내용", "은행"]
        return (
            pd.DataFrame(columns=DEPOSIT_DISPLAY_COLUMNS),
            pd.DataFrame(columns=expense_columns),
        )

    directions = transactions.get(
        "입출금",
        pd.Series("", index=transactions.index, dtype="object"),
    ).fillna("").astype(str).str.strip()
    amounts = pd.to_numeric(
        transactions.get(
            "금액",
            pd.Series(0, index=transactions.index, dtype="int64"),
        ),
        errors="coerce",
    ).fillna(0)

    # 과거에 입출금 값이 비어 저장된 거래는 금액의 부호로 보완한다.
    expense_mask = directions.eq("출금") | (~directions.eq("입금") & amounts.lt(0))
    deposits = transactions.loc[~expense_mask].copy()
    for column in DEPOSIT_DISPLAY_COLUMNS:
        if column not in deposits.columns:
            deposits[column] = ""
    deposits = deposits[DEPOSIT_DISPLAY_COLUMNS].reset_index(drop=True)

    expenses = transactions.loc[expense_mask].copy()
    expenses["사용금액"] = amounts.loc[expense_mask].abs()
    expense_columns = ["거래ID", "거래일시", "사용금액", "잔액", "내용", "은행"]
    for column in expense_columns:
        if column not in expenses.columns:
            expenses[column] = ""

    return deposits, expenses[expense_columns].reset_index(drop=True)


def get_fee_transaction_lists() -> tuple[pd.DataFrame, pd.DataFrame]:
    return split_fee_transactions(get_transaction_list())
