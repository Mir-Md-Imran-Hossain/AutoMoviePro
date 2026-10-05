"""Comprehensive unit & integration tests for Step 1: Secure Login & Licensing System.
Standard library unittest implementation (zero external dependency).

Tests:
- Single PC Hardware ID (HWID) lock enforcement
- Multi-device login blocking
- Instant Remote Admin Kill-Switch
- Email/WhatsApp OTP password reset flow
- Session persistence
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.auth.hardware_id import get_hardware_fingerprint, verify_hardware_fingerprint
from app.customer_auth import (
    ACCOUNT_ACTIVE,
    ACCOUNT_DISABLED,
    AUTHENTICATED,
    authenticate,
    clear_session,
    evaluate_session,
    persist_session,
    refresh_remote_account_state,
    request_password_otp,
    reset_password,
)
from app.db import init_db
import app.db as db_module


class TestSecureAuth(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.orig_db_path = db_module.DB_PATH
        db_module.DB_PATH = Path(self.tmp_dir.name) / "test_auth.db"
        init_db()
        clear_session()

    def tearDown(self):
        clear_session()
        db_module.DB_PATH = self.orig_db_path
        self.tmp_dir.cleanup()

    def test_hardware_fingerprint_generation(self):
        """Verify HWID produces a non-empty, stable, prefixed identifier."""
        hwid1 = get_hardware_fingerprint()
        hwid2 = get_hardware_fingerprint()
        self.assertTrue(hwid1.startswith("AMP-HW-"))
        self.assertGreaterEqual(len(hwid1), 20)
        self.assertEqual(hwid1, hwid2)
        self.assertTrue(verify_hardware_fingerprint(hwid1))
        self.assertFalse(verify_hardware_fingerprint("AMP-HW-DIFFERENT999999"))

    def test_single_pc_hardware_lock_success(self):
        """First-time login locks to current hardware fingerprint."""
        with patch("app.api_client.LicenseClient.login") as mock_login, \
             patch("app.api_client.LicenseClient.me") as mock_me:
            mock_login.return_value = {
                "ok": True,
                "token": "tok_valid_first_pc",
                "customer": {
                    "id": 101,
                    "name": "Zahid Enterprise",
                    "login_id": "zahid01",
                    "status": "active",
                    "hardware_id": get_hardware_fingerprint(),
                }
            }
            mock_me.return_value = {"ok": True, "customer": {"status": "active"}}

            res = authenticate("zahid01", "SecretPass123", "https://automoviepro.com")
            self.assertTrue(res["ok"])
            self.assertEqual(res["identity"]["auth_state"], AUTHENTICATED)
            self.assertEqual(res["identity"]["customer_id"], 101)

    def test_single_pc_hardware_lock_blocked_on_different_pc(self):
        """When a different PC tries to log in to the same account, access is rejected."""
        with patch("app.api_client.LicenseClient.login") as mock_login:
            mock_login.side_effect = RuntimeError(
                "device_locked_to_another_pc:এই অ্যাকাউন্টটি ইতিমধ্যে অন্য একটি নির্দিষ্ট পিসিতে আবদ্ধ (Locked)।"
            )
            res = authenticate("zahid01", "SecretPass123", "https://automoviepro.com")
            self.assertFalse(res["ok"])
            self.assertEqual(res["error"], "device_locked")
            self.assertIn("অন্য একটি নির্দিষ্ট পিসিতে আবদ্ধ", res["message"])

    def test_remote_admin_killswitch(self):
        """When admin restricts or blocks an account, active session is instantly terminated."""
        customer = {
            "id": 102,
            "name": "Simi Media",
            "login_id": "simi02",
            "status": "active",
            "plan": "Standard",
            "entitlement": "active",
        }
        persist_session(
            login_id="simi02",
            token="tok_simi_active",
            customer=customer,
            api_base="https://automoviepro.com",
            auth_mode="license",
        )
        initial_ident = evaluate_session()
        self.assertEqual(initial_ident["auth_state"], AUTHENTICATED)

        with patch("app.api_client.LicenseClient.heartbeat") as mock_hb:
            mock_hb.side_effect = RuntimeError("ACCOUNT_BLOCKED:account_blocked:অ্যাকাউন্ট ব্লক করা হয়েছে।")
            refreshed = refresh_remote_account_state()
            self.assertNotEqual(refreshed["auth_state"], AUTHENTICATED)
            self.assertFalse(refreshed["logged_in"])

    def test_password_reset_flow(self):
        """Tests OTP request and password reset handling."""
        with patch("app.api_client.LicenseClient.request_password_otp") as mock_req, \
             patch("app.api_client.LicenseClient.reset_password_with_otp") as mock_reset:
            mock_req.return_value = {"ok": True, "message": "OTP পাঠানো হয়েছে।"}
            mock_reset.return_value = {"ok": True, "message": "পাসওয়ার্ড সফলভাবে পরিবর্তিত হয়েছে!"}

            req_res = request_password_otp("zahid01@gmail.com", "https://automoviepro.com")
            self.assertTrue(req_res["ok"])

            reset_res = reset_password("zahid01@gmail.com", "123456", "NewSuperPass2026", "https://automoviepro.com")
            self.assertTrue(reset_res["ok"])


if __name__ == "__main__":
    unittest.main()
