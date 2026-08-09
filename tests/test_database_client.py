import os
import unittest
from unittest.mock import MagicMock, patch

from database.client import _secret_value, has_supabase_admin_credentials


class DatabaseClientConfigTests(unittest.TestCase):
    def test_reads_service_role_key_from_nested_supabase_section(self):
        fake_streamlit = MagicMock()
        fake_streamlit.secrets = {
            "supabase": {"service_role_key": "nested-service-key"}
        }

        with (
            patch("database.client.st", fake_streamlit),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertTrue(has_supabase_admin_credentials())
            self.assertEqual(
                _secret_value("SUPABASE_SERVICE_ROLE_KEY"),
                "nested-service-key",
            )

    def test_accepts_service_key_alias_from_environment(self):
        fake_streamlit = MagicMock()
        fake_streamlit.secrets = {}

        with (
            patch("database.client.st", fake_streamlit),
            patch.dict(
                os.environ,
                {"SUPABASE_SERVICE_KEY": "environment-service-key"},
                clear=True,
            ),
        ):
            self.assertTrue(has_supabase_admin_credentials())

    def test_reads_streamlit_connection_section(self):
        fake_streamlit = MagicMock()
        fake_streamlit.secrets = {
            "connections": {
                "supabase": {"service_role_key": "connection-service-key"}
            }
        }

        with (
            patch("database.client.st", fake_streamlit),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(
                _secret_value("SUPABASE_SERVICE_ROLE_KEY"),
                "connection-service-key",
            )

    def test_reports_missing_admin_credentials(self):
        fake_streamlit = MagicMock()
        fake_streamlit.secrets = {}

        with (
            patch("database.client.st", fake_streamlit),
            patch.dict(os.environ, {}, clear=True),
        ):
            self.assertFalse(has_supabase_admin_credentials())


if __name__ == "__main__":
    unittest.main()
