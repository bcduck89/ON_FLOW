import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from services.member_service import (
    annotate_removal_due_memo,
    build_member_dashboard,
    build_unpaid_fee_message,
    get_member_management_data,
)


class MemberDashboardTests(unittest.TestCase):
    def setUp(self):
        self.members = pd.DataFrame(
            [
                {
                    "member_code": "M001",
                    "name": "김활동",
                    "nickname": "활동이",
                    "gender": "남성",
                    "status": "active",
                    "joined_at": "2026-06-01",
                    "정기 참석횟수": 1,
                    "자유 참석횟수": 1,
                    "membership_end": "2026-08-31",
                    "grace_until": "2026-09-07",
                },
                {
                    "member_code": "M002",
                    "name": "이강퇴",
                    "nickname": "",
                    "gender": "남성",
                    "status": "active",
                    "joined_at": "2026-06-01",
                    "정기 참석횟수": 3,
                    "자유 참석횟수": 0,
                    "membership_end": "2026-07-31",
                    "grace_until": "2026-08-07",
                },
                {
                    "member_code": "M004",
                    "name": "최유예",
                    "nickname": "유예중",
                    "gender": "여성",
                    "status": "grace",
                    "joined_at": "2026-08-01",
                    "정기 참석횟수": 1,
                    "자유 참석횟수": 0,
                    "membership_end": "2026-07-31",
                    "grace_until": "2026-08-16",
                },
                {
                    "member_code": "M005",
                    "name": "정탈퇴",
                    "nickname": "",
                    "gender": "여성",
                    "status": "withdrawn",
                    "joined_at": "2026-01-01",
                    "정기 참석횟수": 0,
                    "자유 참석횟수": 0,
                    "membership_end": "2026-07-31",
                    "grace_until": "2026-08-07",
                },
                {
                    "member_code": "M006",
                    "name": "한예외",
                    "nickname": "사유있음",
                    "gender": "남성",
                    "status": "fee_exempt",
                    "joined_at": "2026-07-01",
                    "정기 참석횟수": 0,
                    "자유 참석횟수": 1,
                    "membership_end": "2026-07-31",
                    "grace_until": "2026-08-07",
                },
                {
                    "member_code": "M007",
                    "name": "윤미납",
                    "nickname": "",
                    "gender": "여성",
                    "status": "active",
                    "joined_at": "2026-08-01",
                    "정기 참석횟수": 1,
                    "자유 참석횟수": 0,
                    "membership_end": "2026-08-15",
                    "grace_until": "2026-08-22",
                },
            ]
        )

    def test_unpaid_is_limited_to_active_members_in_the_grace_window(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 16),
        )

        self.assertEqual(dashboard["total"], 6)
        self.assertEqual(dashboard["active"], 5)
        self.assertEqual(dashboard["withdrawn"], 1)
        self.assertEqual(dashboard["total_gender"], {"male": 3, "female": 3})
        self.assertEqual(dashboard["active_gender"], {"male": 3, "female": 2})
        self.assertEqual(dashboard["withdrawn_gender"], {"male": 0, "female": 1})
        self.assertEqual(dashboard["fee_exempt"], 1)
        self.assertEqual(dashboard["unpaid"], 2)
        self.assertEqual(
            dashboard["unpaid_members"]["이름"].tolist(),
            ["최유예", "윤미납"],
        )

    def test_members_past_grace_are_separate_removal_candidates(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 16),
        )

        self.assertEqual(dashboard["removal_due"], 1)
        self.assertEqual(
            dashboard["removal_due_members"]["이름"].tolist(),
            ["이강퇴"],
        )

    def test_management_targets_are_active_members_below_one_monthly_attendance(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 16),
        )

        self.assertEqual(dashboard["management_target"], 2)
        targets = dashboard["management_target_members"]
        self.assertEqual(targets["이름"].tolist(), ["한예외", "김활동"])
        self.assertEqual(targets["가입 경과개월"].tolist(), [2, 3])
        self.assertEqual(targets["월 평균 참석"].tolist(), [0.5, 0.67])
        self.assertNotIn("정탈퇴", targets["이름"].tolist())

    def test_grace_deadline_is_unpaid_through_the_deadline_date(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 17),
        )

        self.assertEqual(dashboard["unpaid"], 1)
        self.assertEqual(dashboard["removal_due"], 2)
        self.assertIn("최유예", dashboard["removal_due_members"]["이름"].tolist())

    def test_message_is_ready_to_copy(self):
        dashboard = build_member_dashboard(
            self.members,
            reference_date=date(2026, 8, 16),
        )
        message = build_unpaid_fee_message(dashboard["unpaid_members"])

        self.assertIn("안녕하세요, ON:FLOW입니다", message)
        self.assertIn("- 최유예(유예중)", message)
        self.assertIn("- 윤미납", message)
        self.assertIn("이미 납부하셨다면", message)

    def test_removal_due_label_is_appended_without_overwriting_memo(self):
        members = self.members.copy()
        members["memo"] = ""
        members.loc[members["name"] == "이강퇴", "memo"] = "개별 확인 필요"

        annotated = annotate_removal_due_memo(
            members,
            reference_date=date(2026, 8, 16),
        )

        removal_memo = annotated.loc[annotated["name"] == "이강퇴", "memo"].iloc[0]
        active_memo = annotated.loc[annotated["name"] == "김활동", "memo"].iloc[0]
        exempt_memo = annotated.loc[annotated["name"] == "한예외", "memo"].iloc[0]

        self.assertEqual(removal_memo, "개별 확인 필요 · 강퇴조치 대상")
        self.assertEqual(active_memo, "")
        self.assertEqual(exempt_memo, "")

    def test_member_management_data_loads_members_and_runs_once(self):
        members = self.members.copy()
        members["member_id"] = range(1, len(members) + 1)
        members["member_type"] = "member"
        members["birth_date"] = ""
        members["city"] = "부산광역시"
        members["district"] = "동래구"
        members["deposit_name"] = members["name"]
        members["membership_start"] = ""
        members["memo"] = ""
        runs = [
            {
                "run_type": "정기",
                "run_date": "2026-08-16",
                "attendee_names": ["김활동"],
            }
        ]

        with (
            patch(
                "services.member_service.list_members",
                return_value=members,
            ) as list_member_rows,
            patch(
                "services.member_service.list_regular_runs",
                return_value=runs,
            ) as list_run_rows,
        ):
            result = get_member_management_data(reference_date=date(2026, 8, 16))

        list_member_rows.assert_called_once_with()
        list_run_rows.assert_called_once_with()
        self.assertEqual(result["dashboard"]["total"], 6)
        self.assertEqual(result["members"].iloc[0]["정기 참석횟수"], 1)
        self.assertNotIn("참석 러닝 상세", result["csv"].decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
