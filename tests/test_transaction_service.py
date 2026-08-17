import unittest

import pandas as pd

from services.transaction_service import split_fee_transactions


class TransactionListSplitTests(unittest.TestCase):
    def test_splits_deposits_and_expenses_and_keeps_existing_deposit_columns(self):
        transactions = pd.DataFrame(
            [
                {
                    "거래ID": 3,
                    "거래일시": "2026-08-12 13:50:41",
                    "입출금": "출금",
                    "금액": -15500,
                    "잔액": 294531,
                    "내용": "소모임 구독료",
                    "회원": "",
                    "은행": "카카오뱅크",
                    "처리상태": "건너뜀",
                },
                {
                    "거래ID": 2,
                    "거래일시": "2026-08-11 22:15:39",
                    "입출금": "입금",
                    "금액": 2000,
                    "잔액": 310031,
                    "내용": "노태석",
                    "회원": "노태석",
                    "은행": "카카오뱅크",
                    "처리상태": "회비반영완료",
                },
                {
                    "거래ID": 1,
                    "거래일시": "2026-08-06 16:25:32",
                    "입출금": "",
                    "금액": -89000,
                    "잔액": 298031,
                    "내용": "깃발 제작 비용",
                    "회원": "",
                    "은행": "카카오뱅크",
                    "처리상태": "건너뜀",
                },
            ]
        )

        deposits, expenses = split_fee_transactions(transactions)

        self.assertEqual(deposits["거래ID"].tolist(), [2])
        self.assertEqual(deposits["처리상태"].tolist(), ["회비반영완료"])
        self.assertNotIn("잔액", deposits.columns)
        self.assertEqual(expenses["거래ID"].tolist(), [3, 1])
        self.assertEqual(expenses["사용금액"].tolist(), [15500, 89000])
        self.assertNotIn("회원", expenses.columns)
        self.assertNotIn("처리상태", expenses.columns)

    def test_returns_both_empty_tables_with_display_columns(self):
        deposits, expenses = split_fee_transactions(pd.DataFrame())

        self.assertTrue(deposits.empty)
        self.assertTrue(expenses.empty)
        self.assertIn("처리상태", deposits.columns)
        self.assertIn("사용금액", expenses.columns)


if __name__ == "__main__":
    unittest.main()
