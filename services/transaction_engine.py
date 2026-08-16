import pandas as pd

from parsers.kakaobank_parser import parse_kakaobank_excel
from repositories.member_repository import list_members
from repositories.transaction_repository import (
    list_transactions,
    get_existing_hashes,
    insert_transactions,
    update_transaction,
)
from services.fee_engine import get_months_from_amount, apply_fee_payment

from repositories.transaction_repository import list_reprocessable_transactions
from services.fee_engine import get_months_from_amount, apply_fee_payment


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

    # 저장 후 새 거래들을 다시 DB에서 읽어서 transaction_id 확보
    transactions = list_transactions()
    new_hashes = set(new_df["transaction_hash"].astype(str).tolist()) if not new_df.empty else set()
    saved_new = transactions[
        transactions["transaction_hash"].astype(str).isin(new_hashes)
    ].copy()

    fee_results = _apply_fee_engine(saved_new)

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

        if direction != "입금":
            update_transaction(transaction_id, {"process_status": "skipped"})
            continue

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
                    "사유": "2,000원 또는 6,000원 입금이 아님",
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
