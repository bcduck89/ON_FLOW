import unittest
from unittest.mock import MagicMock, patch

from repositories.regular_run_repository import (
    delete_regular_run,
    list_regular_run_distance_rows,
)


class RegularRunRepositoryTests(unittest.TestCase):
    def test_reads_only_public_distance_dashboard_fields(self):
        client = MagicMock()
        client.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
            {
                "run_date": "2026-08-02",
                "distance_km": 5,
                "participant_count": 3,
            }
        ]

        with patch(
            "repositories.regular_run_repository.get_supabase_client",
            return_value=client,
        ):
            result = list_regular_run_distance_rows()

        client.table.assert_called_once_with("regular_runs")
        client.table.return_value.select.assert_called_once_with(
            "run_date,distance_km,participant_count"
        )
        self.assertEqual(result[0]["participant_count"], 3)

    def test_deletes_regular_run_by_id_with_admin_client(self):
        admin_client = MagicMock()

        with patch(
            "repositories.regular_run_repository.get_supabase_admin_client",
            return_value=admin_client,
        ):
            delete_regular_run(17)

        admin_client.table.assert_called_once_with("regular_runs")
        delete_query = admin_client.table.return_value.delete.return_value
        delete_query.eq.assert_called_once_with("regular_run_id", 17)
        delete_query.eq.return_value.execute.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
