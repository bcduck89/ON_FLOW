import unittest
from unittest.mock import patch

import pandas as pd

from services.transaction_engine import _apply_fee_engine, import_kakaobank_excel


class ApplyFeeEngineTests(unittest.TestCase):
    def test_includes_direction_in_fee_processing_result(self):
        transactions = pd.DataFrame(
            [
                {
                    "transaction_id": 1,
                    "transaction_datetime": "2026.08.16 12:00:00",
                    "transaction_date": "2026-08-16",
                    "direction": "입금",
                    "amount": 2000,
                    "description": "미등록입금자",
                }
            ]
        )
        members = pd.DataFrame(
            [
                {
                    "member_id": 1,
                    "name": "등록회원",
                    "deposit_name": "다른입금자",
                }
            ]
        )

        with (
            patch(
                "services.transaction_engine.list_members",
                return_value=members,
            ),
            patch("services.transaction_engine.update_transaction"),
        ):
            result = _apply_fee_engine(transactions)

        self.assertEqual(result[0]["입출금"], "입금")
        self.assertEqual(result[0]["처리결과"], "미매칭")

    def test_applies_four_thousand_won_as_two_months(self):
        parsed = pd.DataFrame(
            [
                {
                    "transaction_hash": "existing-hash",
                    "transaction_datetime": "2026.08.16 12:00:00",
                    "transaction_date": "2026-08-16",
                    "direction": "입금",
                    "amount": 4000,
                    "description": "등록입금자",
                }
            ]
        )
        saved = parsed.assign(
            transaction_id=7,
            process_status="need_review",
        )
        members = pd.DataFrame(
            [
                {
                    "member_id": 3,
                    "name": "등록회원",
                    "deposit_name": "등록입금자",
                }
            ]
        )

        with (
            patch(
                "services.transaction_engine.parse_kakaobank_excel",
                return_value=parsed,
            ),
            patch(
                "services.transaction_engine.get_existing_hashes",
                return_value={"existing-hash"},
            ),
            patch("services.transaction_engine.insert_transactions") as insert,
            patch(
                "services.transaction_engine.list_transactions",
                return_value=saved,
            ),
            patch(
                "services.transaction_engine.list_members",
                return_value=members,
            ),
            patch(
                "services.transaction_engine.apply_fee_payment",
                return_value=(True, "2개월 회비 반영 완료"),
            ) as apply_fee,
        ):
            result = import_kakaobank_excel(object())

        insert.assert_not_called()
        apply_fee.assert_called_once_with(
            transaction_id=7,
            member_id=3,
            paid_at="2026-08-16",
            amount=4000,
            note="자동반영: 등록입금자",
        )
        self.assertIn("회비반영완료", result["처리결과"].tolist())


if __name__ == "__main__":
    unittest.main()
