"""
Phase 1A - Step 2 Security and S-03 Protection Tests
Validates:
1. Dynamic cryptographic token verification on sensitive and UI routes
2. Rejection of unauthenticated requests (401)
3. Rejection of external cross-site origins (403)
4. Rejection of invalid Host headers (400)
5. Cookie-based media access (SameSite=Strict + HttpOnly)
6. Fail-closed behavior on Google paid slot claims (network error -> 503, duplicate -> 409)
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.security import (
    COOKIE_NAME,
    get_or_create_app_token,
    verify_app_token,
)


class TestS03SecurityAndAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = get_or_create_app_token()
        cls.client = TestClient(app, base_url="http://127.0.0.1:8787")

    def test_root_index_sets_httponly_samesite_cookie(self):
        """GET / must issue HttpOnly + SameSite=Strict amp_session_token cookie."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        cookie_header = resp.headers.get("set-cookie", "")
        self.assertIn(COOKIE_NAME, cookie_header)
        self.assertIn("samesite=strict", cookie_header.lower())
        self.assertIn("httponly", cookie_header.lower())

    def test_auth_token_endpoint_returns_valid_token(self):
        """GET /api/auth/token with session cookie must expose the active session security token."""
        client = TestClient(app, base_url="http://127.0.0.1:8787")
        client.get("/")  # receives amp_session_token cookie
        resp = client.get("/api/auth/token")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("token"), self.token)
        self.assertTrue(verify_app_token(data.get("token")))

    def test_invalid_host_header_blocked_with_400(self):
        """Requests with unauthorized Host header (DNS rebinding) must receive 400 Bad Request."""
        client = TestClient(app, base_url="http://127.0.0.1:8787")
        resp = client.get(
            "/api/health",
            headers={"Host": "attacker.malicious.com"},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data.get("error"), "invalid_host")

    def test_forbidden_cross_site_origin_blocked_with_403(self):
        """Requests with external cross-site Origin must receive 403 Forbidden."""
        client = TestClient(app, base_url="http://127.0.0.1:8787")
        resp = client.get(
            "/api/health",
            headers={"Origin": "https://evil-hacker.com"},
        )
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data.get("error"), "forbidden_origin")

    def test_forbidden_cross_site_referer_blocked_with_403(self):
        """Requests with external Referer must receive 403 Forbidden."""
        client = TestClient(app, base_url="http://127.0.0.1:8787")
        resp = client.get(
            "/api/health",
            headers={"Referer": "https://phishing-site.com/exploit.html"},
        )
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertEqual(data.get("error"), "forbidden_referer")

    def test_unauthenticated_request_to_sensitive_route_blocked_with_401(self):
        """Unauthenticated POST to /api/subscription/approve-google-paid must receive 401."""
        client = TestClient(app, base_url="http://127.0.0.1:8787")
        resp = client.post(
            "/api/subscription/approve-google-paid",
            json={"order_id": "ORD-TEST-99"},
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.json()
        self.assertIn(data.get("error"), ("unauthorized", "header_token_required"))

    def test_authenticated_via_header_passes_middleware(self):
        """Request carrying X-App-Token header passes auth middleware."""
        resp = self.client.get(
            "/api/health",
            headers={"X-App-Token": self.token},
        )
        self.assertEqual(resp.status_code, 200)

    def test_authenticated_via_cookie_passes_middleware(self):
        """Request carrying amp_session_token cookie passes auth middleware."""
        client_with_cookie = TestClient(
            app,
            base_url="http://127.0.0.1:8787",
            cookies={COOKIE_NAME: self.token},
        )
        resp = client_with_cookie.get("/api/health")
        self.assertEqual(resp.status_code, 200)

    def test_cookie_only_post_rejected_with_403(self):
        """State-changing POST request with cookie alone (no X-App-Token) must receive 403."""
        client = TestClient(
            app,
            base_url="http://127.0.0.1:8787",
            cookies={COOKIE_NAME: self.token},
        )
        resp = client.post(
            "/api/widget/action",
            json={"action": "toggle_scheduler"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "header_token_required")

    def test_cookie_plus_foreign_origin_rejected_with_403(self):
        """State-changing POST with cookie and malicious Origin must be rejected with 403."""
        client = TestClient(
            app,
            base_url="http://127.0.0.1:8787",
            cookies={COOKIE_NAME: self.token},
        )
        resp = client.post(
            "/api/widget/action",
            json={"action": "toggle_scheduler"},
            headers={"Origin": "https://malicious-cross-site.com"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error"), "forbidden_origin")

    def test_header_token_post_succeeds_with_200(self):
        """State-changing POST with X-App-Token header passes auth and succeeds."""
        client = TestClient(app, base_url="http://127.0.0.1:8787")
        resp = client.post(
            "/api/widget/action",
            json={"action": "toggle_scheduler"},
            headers={"X-App-Token": self.token},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))

    def test_cookie_only_get_media_succeeds(self):
        """GET of media/previews with cookie alone passes security middleware (not 401/403)."""
        client = TestClient(
            app,
            base_url="http://127.0.0.1:8787",
            cookies={COOKIE_NAME: self.token},
        )
        resp = client.get("/output/nonexistent_preview.mp4")
        # 404 means the security middleware permitted the request to reach the static file router!
        self.assertEqual(resp.status_code, 404)

    def test_auth_token_blocked_for_foreign_origin_and_missing_cookie(self):
        """GET /api/auth/token rejected if foreign origin (403) or no session cookie (401)."""
        client = TestClient(app, base_url="http://127.0.0.1:8787")
        # 1. No cookie -> 401
        resp_no_cookie = client.get("/api/auth/token")
        self.assertEqual(resp_no_cookie.status_code, 401)

        # 2. Foreign origin -> 403 even if cookie present
        client.get("/") # sets cookie
        resp_foreign = client.get(
            "/api/auth/token",
            headers={"Origin": "https://evil-cross-site.com"},
        )
        self.assertEqual(resp_foreign.status_code, 403)
        self.assertEqual(resp_foreign.json().get("error"), "forbidden_origin")

    def test_approve_google_paid_missing_order_id_returns_400(self):
        """With auth token but empty order_id, returns 400."""
        resp = self.client.post(
            "/api/subscription/approve-google-paid",
            json={},
            headers={"X-App-Token": self.token},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("error"), "missing_order_id")

    def test_approve_google_paid_no_user_session_returns_401(self):
        """With auth token and order_id, but unauthenticated user session, returns 401."""
        with patch("app.main._require_session", return_value=None):
            resp = self.client.post(
                "/api/subscription/approve-google-paid",
                json={"order_id": "ORD-123"},
                headers={"X-App-Token": self.token},
            )
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json().get("error"), "login_required")

    def test_approve_google_paid_server_unreachable_fails_closed(self):
        """When license backend is down, must NEVER fail open; returns 503 with Bengali message."""
        mock_session = {"customer": {"license_key": "AMP-TEST-LIC"}}
        with patch("app.main._require_session", return_value=mock_session), \
             patch("app.api_client.LicenseClient.claim_google_slot", return_value={
                 "ok": False,
                 "error": "server_unreachable",
                 "status_code": 503,
                 "message": "সার্ভারের সাথে সংযোগ স্থাপন করা যায়নি। ইন্টারনেট কানেকশন চেক করুন।"
             }), \
             patch("pipeline.dedicated_api_registry.unlock_google_paid") as mock_unlock:
            
            resp = self.client.post(
                "/api/subscription/approve-google-paid",
                json={"order_id": "ORD-123"},
                headers={"X-App-Token": self.token},
            )
            self.assertEqual(resp.status_code, 503)
            data = resp.json()
            self.assertFalse(data.get("ok"))
            self.assertIn("সার্ভারের সাথে সংযোগ স্থাপন করা যায়নি", data.get("message", ""))
            # Strictly verify unlock was NOT called (never fails open)
            mock_unlock.assert_not_called()

    def test_approve_google_paid_duplicate_claim_rejected_with_409(self):
        """Duplicate claim rejection from server returns 409 and does not unlock."""
        mock_session = {"customer": {"license_key": "AMP-TEST-LIC"}}
        with patch("app.main._require_session", return_value=mock_session), \
             patch("app.api_client.LicenseClient.claim_google_slot", return_value={
                 "ok": False,
                 "error": "already_claimed",
                 "status_code": 409,
                 "message": "এই অর্ডারের স্লট ইতিমধ্যে দাবি করা হয়েছে।"
             }), \
             patch("pipeline.dedicated_api_registry.unlock_google_paid") as mock_unlock:

            resp = self.client.post(
                "/api/subscription/approve-google-paid",
                json={"order_id": "ORD-ALREADY-CLAIMED"},
                headers={"X-App-Token": self.token},
            )
            self.assertEqual(resp.status_code, 409)
            data = resp.json()
            self.assertFalse(data.get("ok"))
            self.assertEqual(data.get("error"), "already_claimed")
            mock_unlock.assert_not_called()

    def test_approve_google_paid_valid_claim_succeeds(self):
        """Legitimate verified order claim successfully unlocks slot and returns 200."""
        mock_session = {"customer": {"license_key": "AMP-TEST-LIC"}}
        with patch("app.main._require_session", return_value=mock_session), \
             patch("app.api_client.LicenseClient.claim_google_slot", return_value={
                 "ok": True,
                 "claim_id": "CLAIM-777",
                 "status_code": 200
             }), \
             patch("app.db.approve_google_pro_order") as mock_approve_db, \
             patch("pipeline.dedicated_api_registry.unlock_google_paid", return_value=(True, "Unlocked")) as mock_unlock, \
             patch("pipeline.dedicated_api_registry.google_paid_unlocked_slot_count", return_value=2):

            resp = self.client.post(
                "/api/subscription/approve-google-paid",
                json={"order_id": "ORD-VALID-777"},
                headers={"X-App-Token": self.token},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("unlocked_slots"), 2)
            mock_approve_db.assert_called_once_with("ORD-VALID-777")
            mock_unlock.assert_called_once_with("ORDER-ORD-VALID-777", slots_to_add=1)


if __name__ == "__main__":
    unittest.main()
