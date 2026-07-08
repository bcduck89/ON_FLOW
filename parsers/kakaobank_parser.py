import hashlib
import pandas as pd


def _to_int(value) -> int:
    try:
        return int(
            str(value)
            .replace(",", "")
            .replace("원", "")
            .replace("+", "")
            .strip()
        )
    except Exception:
        return 0


def _make_hash(row) -> str:
    raw = (
        f"{row['transaction_datetime']}|"
        f"{row['direction']}|"
        f"{row['amount']}|"
        f"{row['balance']}|"
        f"{row['description']}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_kakaobank_excel(uploaded_file) -> pd.DataFrame:
    raw = pd.read_excel(
        uploaded_file,
        engine="openpyxl",
        header=None,
    ).fillna("")

    header_row_index = None

    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.tolist()]
        if "거래일시" in values and "거래금액" in values:
            header_row_index = idx
            break

    if header_row_index is None:
        raise ValueError("카카오뱅크 거래내역의 컬럼 행을 찾지 못했습니다.")

    df = raw.iloc[header_row_index + 1:].copy()
    df.columns = raw.iloc[header_row_index].tolist()

    df = df.dropna(how="all").fillna("")

    rename_map = {
        "거래일시": "transaction_datetime",
        "구분": "direction",
        "거래금액": "amount",
        "거래 후 잔액": "balance",
        "거래구분": "transaction_type",
        "내용": "description",
        "메모": "memo",
    }

    df = df.rename(columns=rename_map)

    required = [
        "transaction_datetime",
        "direction",
        "amount",
        "balance",
        "transaction_type",
        "description",
    ]

    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"필수 컬럼이 없습니다: {col}\n"
                f"현재 컬럼: {list(df.columns)}"
            )

    df["transaction_datetime"] = df["transaction_datetime"].astype(str).str.strip()
    df["direction"] = df["direction"].astype(str).str.strip()
    df["description"] = df["description"].astype(str).str.strip()
    df["memo"] = df.get("memo", "").astype(str).str.strip()

    df["amount"] = df["amount"].apply(_to_int)
    df["balance"] = df["balance"].apply(_to_int)

    dt = pd.to_datetime(
        df["transaction_datetime"],
        format="%Y.%m.%d %H:%M:%S",
        errors="coerce",
    )

    df["transaction_date"] = dt.dt.date.astype(str)
    df["transaction_time"] = dt.dt.time.astype(str)

    df["transaction_hash"] = df.apply(_make_hash, axis=1)

    df["bank_name"] = "카카오뱅크"
    df["category"] = ""
    df["confirm_status"] = "unchecked"
    df["process_status"] = "uploaded"

    return df[
        [
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
        ]
    ]