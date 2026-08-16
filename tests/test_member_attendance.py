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


if __name__ == "__main__":
    unittest.main()
