import unittest

from services.home_dashboard_service import (
    build_monthly_distance_for_year,
    build_running_distance_dashboard,
)


class HomeDashboardServiceTests(unittest.TestCase):
    def test_sums_participant_weighted_distance_by_month(self):
        dashboard = build_running_distance_dashboard(
            [
                {
                    "run_date": "2026-07-12",
                    "distance_km": 5,
                    "participant_count": 3,
                },
                {
                    "run_date": "2026-07-19",
                    "distance_km": 7.5,
                    "participant_count": 2,
                },
                {
                    "run_date": "2026-08-02",
                    "distance_km": 10,
                    "participant_count": 4,
                },
            ]
        )

        self.assertEqual(dashboard["total_distance_km"], 70.0)
        self.assertEqual(dashboard["available_years"], [2026])
        self.assertEqual(
            dashboard["monthly_distance"],
            [
                {"월": "2026-07", "단체 거리 (km)": 30.0},
                {"월": "2026-08", "단체 거리 (km)": 40.0},
            ],
        )

    def test_ignores_invalid_rows_and_prevents_negative_distance(self):
        dashboard = build_running_distance_dashboard(
            [
                {
                    "run_date": "invalid",
                    "distance_km": 5,
                    "participant_count": 3,
                },
                {
                    "run_date": "2026-08-02",
                    "distance_km": -5,
                    "participant_count": 3,
                },
                {
                    "run_date": "2026-08-03",
                    "distance_km": "not-a-number",
                    "participant_count": 3,
                },
            ]
        )

        self.assertEqual(dashboard["total_distance_km"], 0.0)
        self.assertEqual(
            dashboard["monthly_distance"],
            [{"월": "2026-08", "단체 거리 (km)": 0.0}],
        )

    def test_builds_all_twelve_months_for_selected_year(self):
        monthly_rows = build_monthly_distance_for_year(
            [
                {"월": "2025-12", "단체 거리 (km)": 25.0},
                {"월": "2026-02", "단체 거리 (km)": 30.0},
                {"월": "2026-08", "단체 거리 (km)": 40.0},
            ],
            2026,
        )

        self.assertEqual(len(monthly_rows), 12)
        self.assertEqual(monthly_rows[0]["월"], "1월")
        self.assertEqual(monthly_rows[0]["단체 거리 (km)"], 0.0)
        self.assertEqual(monthly_rows[1]["단체 거리 (km)"], 30.0)
        self.assertEqual(monthly_rows[7]["단체 거리 (km)"], 40.0)
        self.assertEqual(monthly_rows[11]["월"], "12월")


if __name__ == "__main__":
    unittest.main()
