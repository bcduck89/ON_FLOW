import unittest
from unittest.mock import MagicMock, patch

from services.auth_service import verify_admin_password


class AuthServiceTests(unittest.TestCase):
    def test_verifies_configured_admin_password(self):
        fake_streamlit = MagicMock()
        fake_streamlit.secrets = {"ADMIN_PASSWORD": "correct-password"}

        with patch("services.auth_service.st", fake_streamlit):
            self.assertTrue(verify_admin_password("correct-password"))
            self.assertFalse(verify_admin_password("wrong-password"))

    def test_rejects_password_when_admin_secret_is_empty(self):
        fake_streamlit = MagicMock()
        fake_streamlit.secrets = {"ADMIN_PASSWORD": ""}

        with patch("services.auth_service.st", fake_streamlit):
            self.assertFalse(verify_admin_password(""))


if __name__ == "__main__":
    unittest.main()
