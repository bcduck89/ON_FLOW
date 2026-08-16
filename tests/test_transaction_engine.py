import unittest
from unittest.mock import patch

import pandas as pd

from services.transaction_engine import _apply_fee_engine


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


if __name__ == "__main__":
    unittest.main()
