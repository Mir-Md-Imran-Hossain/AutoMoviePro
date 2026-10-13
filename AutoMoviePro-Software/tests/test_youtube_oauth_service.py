"""Unit tests for YouTube Data API v3 1-Click Customer Channel OAuth Service."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from app import db as store
from publishers.youtube_oauth_service import (
    DEFAULT_REDIRECT_URI,
    GOOGLE_AUTH_URL,
    YOUTUBE_SCOPES,
    YouTubeOAuthService,
    ensure_youtube_oauth_columns,
)


class TestYouTubeOAuthService(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.db_path = self.td / "test_oauth.db"

        self._orig_db = store.DB_PATH
        store.DB_PATH = self.db_path
        store.init_db()
        ensure_youtube_oauth_columns()

        self.service = YouTubeOAuthService(mock_mode=True)
        # Create a test channel
        self.channel_id = store.upsert_channel({
            "youtube_name": "Test Tech Channel",
            "owner_login_id": "test_user_01",
        })

    def tearDown(self):
        store.DB_PATH = self._orig_db

    def test_authorization_url_generation(self):
        url = self.service.get_authorization_url(state="test_customer_123")
        self.assertIn(GOOGLE_AUTH_URL, url)
        self.assertIn("client_id=", url)
        self.assertIn("redirect_uri=", url)
        self.assertIn("response_type=code", url)
        self.assertIn("access_type=offline", url)
        self.assertIn("prompt=consent", url)
        self.assertIn("state=test_customer_123", url)
        for scope in YOUTUBE_SCOPES:
            # URL encoded scope
            self.assertTrue("youtube.upload" in url and "youtube.readonly" in url)

    def test_code_exchange_mock_flow(self):
        res = self.service.exchange_code_for_tokens("mock_code_abc123456789")
        self.assertTrue(res["ok"])
        self.assertTrue(res["access_token"].startswith("ya29.mock_access_token_"))
        self.assertTrue(res["refresh_token"].startswith("1//mock_refresh_token_"))
        self.assertEqual(res["expires_in"], 3600)
        self.assertTrue(res["mock"])

    def test_code_exchange_empty_error(self):
        with self.assertRaises(ValueError):
            self.service.exchange_code_for_tokens("")

    def test_fetch_channel_profile_mock(self):
        prof = self.service.fetch_channel_profile("ya29.mock_token")
        self.assertTrue(prof["ok"])
        self.assertEqual(prof["channel_id"], "UC_MOCK_CHANNEL_12345")
        self.assertEqual(prof["channel_title"], "AutoMovie Creator Channel")
        self.assertEqual(prof["custom_url"], "@automovie_creator")
        self.assertGreater(prof["video_count"], 0)

    def test_connect_customer_channel_1click(self):
        res = self.service.connect_customer_channel_1click(
            channel_id=self.channel_id,
            auth_code_or_tokens="mock_code_xyz987654321",
            login_id="test_user_01",
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["connected"])
        self.assertEqual(res["channel_id"], self.channel_id)
        self.assertFalse(res["token_exposed"])

        # Verify DB row updated and encrypted
        ch = store.get_channel(self.channel_id)
        self.assertEqual(ch["youtube_oauth_connected"], 1)
        self.assertEqual(ch["youtube_channel_id"], "UC_MOCK_CHANNEL_12345")
        self.assertEqual(ch["youtube_channel_title"], "AutoMovie Creator Channel")
        self.assertTrue(len(ch["youtube_access_token"]) > 0)
        self.assertTrue(len(ch["youtube_refresh_token"]) > 0)

    def test_connect_customer_channel_scope_denied(self):
        with self.assertRaises(PermissionError):
            self.service.connect_customer_channel_1click(
                channel_id=self.channel_id,
                auth_code_or_tokens="mock_code_xyz",
                login_id="different_hacker_user",
            )

    def test_get_valid_channel_token_auto_refresh(self):
        # First connect channel
        self.service.connect_customer_channel_1click(
            channel_id=self.channel_id,
            auth_code_or_tokens="mock_code_active_tok",
            login_id="test_user_01",
        )

        # 1. Active unexpired token returned directly
        tok1 = self.service.get_valid_channel_token(self.channel_id)
        self.assertTrue(tok1.startswith("ya29.mock_access_token_"))

        # 2. Expire the token in DB manually
        with store.db() as conn:
            conn.execute(
                "UPDATE channels SET youtube_token_expires_at = ? WHERE id = ?",
                ((datetime.now() - timedelta(hours=2)).isoformat(), self.channel_id)
            )

        # 3. Requesting token again must automatically trigger refresh
        tok2 = self.service.get_valid_channel_token(self.channel_id)
        self.assertTrue(tok2.startswith("ya29.mock_refreshed_"))

    def test_customer_publish_provider_integration(self):
        from publishers.customer_publish_provider import YouTubeDataApiProvider

        provider = YouTubeDataApiProvider()

        # Channel before OAuth connect
        ch_unconnected = store.get_channel(self.channel_id)
        val_unconnected = provider.validate_configuration(ch_unconnected)
        self.assertFalse(val_unconnected["ok"])
        self.assertEqual(val_unconnected["error_code"], "AUTH_FAILURE")

        # Connect 1-click OAuth
        self.service.connect_customer_channel_1click(
            channel_id=self.channel_id,
            auth_code_or_tokens="mock_code_pub_test",
            login_id="test_user_01",
        )

        # Channel after OAuth connect
        ch_connected = store.get_channel(self.channel_id)
        val_connected = provider.validate_configuration(ch_connected)
        self.assertTrue(val_connected["ok"])
        self.assertTrue(val_connected["oauth_configured"])
        self.assertTrue(val_connected["one_click_connected"])


if __name__ == "__main__":
    unittest.main()
