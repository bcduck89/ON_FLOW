import hashlib
from datetime import date, datetime, time

import pandas as pd

from parsers.kakaobank_parser import parse_kakaobank_excel
from repositories.member_repository import list_members
from repositories.transaction_repository import (
    list_transactions,
    list_reprocessable_transactions,
    get_existing_hashes,
    insert_transactions,
    update_transaction,
)
from services.fee_engine import get_months_from_amount, apply_fee_payment


def create_manual_transaction(
    *,
    transaction_date: date,
    transaction_time: time,
    direction: str,
    amount: int,
    balance: int,
    description: str,
    memo: str = "",
    bank_name: str = "카카오뱅크",
) -> pd.DataFrame:
    """수동 거래를 저장하고 입금이면 기존 회비 엔진까지 적용한다."""
    direction = str(direction or "").strip()
    if direction not in {"입금", "출금"}:
        raise ValueError("입출금 구분은 입금 또는 출금이어야 합니다.")
    if not transaction_date or not transaction_time:
        raise ValueError("거래 날짜와 시간을 입력해주세요.")
    if int(amount) <= 0:
        raise ValueError("금액은 0원보다 커야 합니다.")
    if int(balance) < 0:
        raise ValueError("거래 후 잔액은 0원 이상이어야 합니다.")
    description = str(description or "").strip()
    if not description:
        raise ValueError("입금자명 또는 사용 내용을 입력해주세요.")

    transaction_datetime_value = datetime.combine(
        transaction_date,
        transaction_time,
    )
    transaction_datetime = transaction_datetime_value.strftime("%Y.%m.%d %H:%M:%S")
    signed_amount = int(amount) if direction == "입금" else -int(amount)
    hash_source = (
        f"manual|{transaction_datetime}|{direction}|{signed_amount}|"
        f"{int(balance)}|{description}|{str(memo or '').strip()}"
    )
    transaction_hash = hashlib.sha256(hash_source.encode("utf-8")).hexdigest()
    if transaction_hash in get_existing_hashes():
        raise ValueError("이미 등록된 수동 거래입니다.")

    row = {
        "transaction_hash": transaction_hash,
        "transaction_datetime": transaction_datetime,
        "transaction_date": transaction_date.isoformat(),
        "transaction_time": transaction_time.strftime("%H:%M:%S"),
        "direction": direction,
        "amount": signed_amount,
        "balance": int(balance),
        "transaction_type": "수동입력",
        "description": description,
        "memo": str(memo or "").strip(),
        "category": "회비입금" if direction == "입금" else "회비사용",
        "confirm_status": "checked",
        "bank_name": str(bank_name or "").strip() or "카카오뱅크",
        "process_status": "uploaded",
    }
    insert_transactions([row])

    transactions = list_transactions()
    processing_target = transactions[
        transactions["transaction_hash"].astype(str).eq(transaction_hash)
    ].copy()
    if processing_target.empty:
        raise RuntimeError("수동 거래는 저장되었지만 처리 결과를 확인하지 못했습니다.")

    fee_results = _apply_fee_engine(processing_target)
    if fee_results:
        return pd.DataFrame(fee_results)

    return pd.DataFrame(
        [
            {
                "거래일시": transaction_datetime,
                "입출금": direction,
                "입금자/내용": description,
                "금액": signed_amount,
                "처리결과": "저장완료",
                "사유": "회비 사용 내역으로 저장했습니다.",
            }
        ]
    )


def import_kakaobank_excel(uploaded_file) -> pd.DataFrame:
    parsed = parse_kakaobank_excel(uploaded_file)

    existing_hashes = get_existing_hashes()

    duplicated = parsed[
        parsed["transaction_hash"].astype(str).isin(existing_hashes)
    ].copy()

    new_df = parsed[
        ~parsed["transaction_hash"].astype(str).isin(existing_hashes)
    ].copy()

    result_rows = []

    for _, row in duplicated.iterrows():
        result_rows.append(
            {
                "거래일시": row.get("transaction_datetime", ""),
                "입출금": row.get("direction", ""),
                "입금자/내용": row.get("description", ""),
                "금액": row.get("amount", ""),
                "처리결과": "중복거래",
                "사유": "이미 DB에 저장된 거래",
            }
        )

    if not new_df.empty:
        rows = new_df.to_dict(orient="records")
        insert_transactions(rows)

        for _, row in new_df.iterrows():
            result_rows.append(
                {
                    "거래일시": row.get("transaction_datetime", ""),
                    "입출금": row.get("direction", ""),
                    "입금자/내용": row.get("description", ""),
                    "금액": row.get("amount", ""),
                    "처리결과": "신규저장",
                    "사유": "DB에 신규 거래 저장",
                }
            )

    # 저장 후 DB에서 transaction_id와 현재 처리상태를 확보한다.
    transactions = list_transactions()
    uploaded_hashes = set(parsed["transaction_hash"].astype(str).tolist())
    reprocessable_statuses = {"uploaded", "unmatched", "need_review"}
    processing_targets = transactions[
        transactions["transaction_hash"].astype(str).isin(uploaded_hashes)
        & transactions["process_status"].astype(str).isin(reprocessable_statuses)
    ].copy()

    fee_results = _apply_fee_engine(processing_targets)

    if fee_results:
        result_rows.extend(fee_results)

    if not result_rows:
        return pd.DataFrame(
            [
                {
                    "처리결과": "처리할 거래 없음",
                    "사유": "파일에 거래내역이 없거나 모두 처리 대상이 아닙니다.",
                }
            ]
        )

    return pd.DataFrame(result_rows)


def _apply_fee_engine(transactions: pd.DataFrame) -> list[dict]:
    if transactions.empty:
        return []

    directions = transactions.get(
        "direction",
        pd.Series("", index=transactions.index, dtype="object"),
    ).fillna("").astype(str).str.strip()
    outgoing_transactions = transactions.loc[~directions.eq("입금")]
    for _, tx in outgoing_transactions.iterrows():
        update_transaction(int(tx["transaction_id"]), {"process_status": "skipped"})

    transactions = transactions.loc[directions.eq("입금")].copy()
    if transactions.empty:
        return []

    members = list_members()

    if members.empty:
        return [
            {
                "거래일시": "",
                "입금자/내용": "",
                "금액": "",
                "처리결과": "확인필요",
                "사유": "등록된 회원이 없습니다.",
            }
        ]

    members = members.copy()
    members["deposit_name"] = members["deposit_name"].astype(str).str.strip()

    result_rows = []

    for _, tx in transactions.iterrows():
        transaction_id = int(tx["transaction_id"])
        direction = str(tx.get("direction", "")).strip()
        amount = int(tx.get("amount", 0))
        payer = str(tx.get("description", "")).strip()

        months = get_months_from_amount(amount)

        if months == 0:
            update_transaction(transaction_id, {"process_status": "need_review"})
            result_rows.append(
                {
                    "거래일시": tx.get("transaction_datetime", ""),
                    "입출금": direction,
                    "입금자/내용": payer,
                    "금액": amount,
                    "처리결과": "확인필요",
                    "사유": "2,000원 단위 입금이 아님",
                }
            )
            continue

        matched = members[members["deposit_name"] == payer]

        if matched.empty:
            update_transaction(transaction_id, {"process_status": "unmatched"})
            result_rows.append(
                {
                    "거래일시": tx.get("transaction_datetime", ""),
                    "입출금": direction,
                    "입금자/내용": payer,
                    "금액": amount,
                    "처리결과": "미매칭",
                    "사유": "입금자명과 일치하는 회원 없음",
                }
            )
            continue

        if len(matched) > 1:
            update_transaction(transaction_id, {"process_status": "need_review"})
            result_rows.append(
                {
                    "거래일시": tx.get("transaction_datetime", ""),
                    "입출금": direction,
                    "입금자/내용": payer,
                    "금액": amount,
                    "처리결과": "확인필요",
                    "사유": "동일 입금자명 회원이 2명 이상",
                }
            )
            continue

        member = matched.iloc[0]

        success, message = apply_fee_payment(
            transaction_id=transaction_id,
            member_id=int(member["member_id"]),
            paid_at=tx.get("transaction_date"),
            amount=amount,
            note=f"자동반영: {payer}",
        )

        result_rows.append(
            {
                "거래일시": tx.get("transaction_datetime", ""),
                "입출금": direction,
                "입금자/내용": payer,
                "금액": amount,
                "회원": member.get("name", ""),
                "처리결과": "회비반영완료" if success else "확인필요",
                "사유": message,
            }
        )

    return result_rows


def reprocess_transactions_for_member(member: dict) -> pd.DataFrame:
    deposit_name = str(member.get("deposit_name", "")).strip()

    if deposit_name == "":
        return pd.DataFrame()

    transactions = list_reprocessable_transactions()

    if transactions.empty:
        return pd.DataFrame()

    matched_transactions = transactions[
        transactions["description"].astype(str).str.strip() == deposit_name
    ].copy()

    result_rows = []

    for _, tx in matched_transactions.iterrows():
        transaction_id = int(tx["transaction_id"])
        amount = int(tx.get("amount", 0))
        direction = str(tx.get("direction", "")).strip()

        if direction != "입금":
            continue

        months = get_months_from_amount(amount)

        if months == 0:
            update_transaction(
                transaction_id,
                {
                    "process_status": "need_review",
                    "matched_member_id": int(member["member_id"]),
                },
            )
            continue

        success, message = apply_fee_payment(
            transaction_id=transaction_id,
            member_id=int(member["member_id"]),
            paid_at=tx.get("transaction_date"),
            amount=amount,
            note=f"회원등록 후 자동 재매칭: {deposit_name}",
        )

        result_rows.append(
            {
                "거래일시": tx.get("transaction_datetime", ""),
                "입출금": direction,
                "입금자": deposit_name,
                "금액": amount,
                "회원": member.get("name", ""),
                "처리결과": "회비반영완료" if success else "확인필요",
                "사유": message,
            }
        )

    return pd.DataFrame(result_rows)
