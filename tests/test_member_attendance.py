import unittest

import pandas as pd

from services.member_service import add_member_attendance_counts


class MemberAttendanceTests(unittest.TestCase):
    def test_counts_regular_and_free_runs_by_name_or_nickname(self):
        members = pd.DataFrame(
            [
                {"name": "김주희", "nickname": "주히"},
                {"name": "신우식", "nickname": "우식"},
            ]
        )
        runs = [
            {"run_type": "정기", "attendee_names": ["김주희", "우식"]},
            {"run_type": "자유", "attendee_names": ["주히"]},
            {"run_type": "자유", "attendee_names": ["신우식"]},
        ]

        result = add_member_attendance_counts(members, regular_runs=runs)

        self.assertEqual(result.loc[0, "정기 참석횟수"], 1)
        self.assertEqual(result.loc[0, "자유 참석횟수"], 1)
        self.assertEqual(result.loc[1, "정기 참석횟수"], 1)
        self.assertEqual(result.loc[1, "자유 참석횟수"], 1)

    def test_includes_number_type_and_date_in_attendance_history(self):
        members = pd.DataFrame([{"name": "김주희", "nickname": "주히"}])
        runs = [
            {
                "run_type": "자유",
                "run_date": "2026-08-17",
                "attendee_names": ["주히"],
            },
            {
                "run_type": "정기",
                "run_date": "2026-08-16",
                "attendee_names": ["김주희"],
            },
        ]

        result = add_member_attendance_counts(
            members,
            regular_runs=runs,
            include_history=True,
        )

        self.assertEqual(
            result.loc[0, "참석 러닝 상세"],
            [
                {"번호": 2, "구분": "자유", "날짜": "2026-08-17"},
                {"번호": 1, "구분": "정기", "날짜": "2026-08-16"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
