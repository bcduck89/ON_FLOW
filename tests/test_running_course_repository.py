import unittest
from unittest.mock import MagicMock, patch

from repositories.running_course_repository import (
    delete_course,
    list_courses,
    update_course,
)


def query_client(rows):
    client = MagicMock()
    client.table.return_value.select.return_value.order.return_value.execute.return_value.data = rows
    return client


class RunningCourseRepositoryTests(unittest.TestCase):
    def test_updates_course_by_activity_id_with_admin_client(self):
        admin_client = MagicMock()
        admin_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
            {"activity_id": 17, "name": "수정 코스"}
        ]

        with patch(
            "repositories.running_course_repository.get_supabase_admin_client",
            return_value=admin_client,
        ):
            result = update_course(17, {"name": "수정 코스"})

        admin_client.table.assert_called_once_with("running_activities")
        update_query = admin_client.table.return_value.update
        update_query.assert_called_once_with({"name": "수정 코스"})
        update_query.return_value.eq.assert_called_once_with("activity_id", 17)
        self.assertEqual(result["name"], "수정 코스")

    def test_deletes_course_by_activity_id_with_admin_client(self):
        admin_client = MagicMock()

        with patch(
            "repositories.running_course_repository.get_supabase_admin_client",
            return_value=admin_client,
        ):
            delete_course(17)

        admin_client.table.assert_called_once_with("running_activities")
        delete_query = admin_client.table.return_value.delete.return_value
        delete_query.eq.assert_called_once_with("activity_id", 17)
        delete_query.eq.return_value.execute.assert_called_once_with()

    def test_uses_admin_client_for_course_list_when_available(self):
        admin_client = query_client([{"activity_id": 1, "name": "동래 코스"}])

        with (
            patch(
                "repositories.running_course_repository.get_supabase_admin_client",
                return_value=admin_client,
            ),
            patch(
                "repositories.running_course_repository.get_supabase_client"
            ) as public_client,
        ):
            courses = list_courses()

        self.assertEqual(courses[0]["name"], "동래 코스")
        public_client.assert_not_called()

    def test_falls_back_to_public_client_without_service_role_key(self):
        public_client = query_client([{"activity_id": 2, "name": "공개 코스"}])

        with (
            patch(
                "repositories.running_course_repository.get_supabase_admin_client",
                side_effect=RuntimeError("missing service role key"),
            ),
            patch(
                "repositories.running_course_repository.get_supabase_client",
                return_value=public_client,
            ),
        ):
            courses = list_courses()

        self.assertEqual(courses[0]["name"], "공개 코스")


if __name__ == "__main__":
    unittest.main()
