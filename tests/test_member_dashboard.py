import unittest
from datetime import date

import pandas as pd

from services.member_service import build_member_dashboard, build_unpaid_fee_message


class MemberDashboardTests(unittest.TestCase):
    def setUp(self):
        self.members = pd.DataFrame(
            [
                {
                    "member_code": "M001",
                    "name": "김활동",
                    "nickname": "활동이",
                    "status": "active",
                    "grace_until": "2026-08-31",
                },
                {
                    "member_code": "M002",
                    "name": "이미납",
                    "nickname": "",
                    "status": "active",
                    "grace_until": "",
                },
                {
                    "member_code": "M003",
                    "name": "박휴면",
                    "nickname": "휴면이",
                    "status": "dormant",
                    "grace_until": "2026-08-15",
                },
                {
                    "member_code": "M004",
                    "name": "최유예",
                    "nickname": "유예중",
                    "status": "grace",
                    "grace_until": "2026-08-16",
                },
                {
                    "member_code": "M005",
                    "name": "정탈퇴",
                    "nickname": "",
                    "status": "withdrawn",
                    "grace_until": "",
                },
            ]
        )

    def test_builds_status_counts_and_excludes_withdrawn_from_unpaid(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 16),
        )

        self.assertEqual(dashboard["total"], 5)
        self.assertEqual(dashboard["active"], 2)
        self.assertEqual(dashboard["dormant"], 1)
        self.assertEqual(dashboard["withdrawn"], 1)
        self.assertEqual(dashboard["unpaid"], 2)
        self.assertEqual(
            dashboard["unpaid_members"]["이름"].tolist(),
            ["이미납", "박휴면"],
        )

    def test_grace_deadline_is_included_through_the_deadline_date(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 17),
        )

        self.assertEqual(dashboard["unpaid"], 3)
        self.assertIn("최유예", dashboard["unpaid_members"]["이름"].tolist())

    def test_message_is_ready_to_copy(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 16),
        )
        message = build_unpaid_fee_message(dashboard["unpaid_members"])

        self.assertIn("안녕하세요, ON:FLOW입니다", message)
        self.assertIn("- 이미납", message)
        self.assertIn("- 박휴면(휴면이)", message)
        self.assertIn("이미 납부하셨다면", message)


if __name__ == "__main__":
    unittest.main()
