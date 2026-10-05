"""
Comprehensive multi-angle tests for Step 1:
TikTok Integration, DB Migrations, Session Vault, Lang Destinations, and Upload Service.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import db as store
from app.config import settings
from pipeline.lang_destinations import (
    merge_destination_form,
    parse_lang_destinations,
    resolve_destination,
    serialize_lang_destinations,
)
from publishers import session_vault
from publishers.login_signals import cookies_indicate_login, page_logged_in
from publishers.upload_service import upload_job


class TestTikTokStep1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary test database
        cls.orig_db = store.DB_PATH
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db = Path(cls.temp_dir) / "test.db"
        store.DB_PATH = cls.test_db
        store.init_db()

    @classmethod
    def tearDownClass(cls):
        store.DB_PATH = cls.orig_db
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_db_schema_and_migration(self):
        """Verify DB schema contains tiktok_name and tiktok_session columns."""
        with store.db() as conn:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(channels)").fetchall()]
        self.assertIn("tiktok_name", cols, "tiktok_name column missing in channels")
        self.assertIn("tiktok_session", cols, "tiktok_session column missing in channels")

    def test_02_channel_upsert_and_encryption(self):
        """Verify upsert_channel encrypts and decrypts tiktok_session and persists tiktok_name."""
        channel_data = {
            "name": "Global Factory Channel",
            "niche": "Technology & AI",
            "youtube_name": "TechGlobalYT",
            "facebook_name": "TechGlobalFB",
            "tiktok_name": "@TechGlobalTikTok",
            "tiktok_session": json.dumps({"cookies": [{"name": "sessionid", "value": "secret123"}]}),
            "enabled": 1,
        }
        cid = store.upsert_channel(channel_data)
        self.assertGreater(cid, 0)

        # Raw DB inspect: verify tiktok_session is encrypted on disk
        with store.db() as conn:
            row = conn.execute("SELECT * FROM channels WHERE id=?", (cid,)).fetchone()
            raw_tt_session = row["tiktok_session"]
            raw_tt_name = row["tiktok_name"]

        self.assertEqual(raw_tt_name, "@TechGlobalTikTok")
        # In SQLite, encrypted text will not match the plaintext secret directly
        self.assertNotIn("secret123", raw_tt_session)

        # Fetch through store: verify auto-decrypted
        fetched = store.get_channel(cid)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["tiktok_name"], "@TechGlobalTikTok")
        self.assertIn("secret123", fetched.get("tiktok_session", ""))

    def test_03_login_signals_for_tiktok(self):
        """Verify login_signals detects tiktok cookies and page signatures."""
        # Valid tiktok cookies
        valid_cookie_state = {
            "cookies": [
                {"name": "sessionid", "value": "xyz", "domain": ".tiktok.com"},
                {"name": "tt_chain_token", "value": "abc", "domain": ".tiktok.com"},
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
            json.dump(valid_cookie_state, tmp)
            tmp_path = tmp.name

        try:
            self.assertTrue(cookies_indicate_login("tiktok", tmp_path))
            self.assertFalse(cookies_indicate_login("youtube", tmp_path))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_04_lang_destinations_tiktok(self):
        """Verify per-language destinations correctly parse, serialize, and overlay TikTok."""
        dest_raw = {
            "en": {
                "youtube_name": "YT English",
                "facebook_name": "FB English",
                "tiktok_name": "TikTok English",
            },
            "bn": {
                "youtube_name": "YT Bangla",
                "facebook_name": "FB Bangla",
                "tiktok_name": "TikTok Bangla",
                "tiktok_session": "enc_session_bn",
            },
        }
        serialized = serialize_lang_destinations(dest_raw)
        parsed = parse_lang_destinations(serialized)

        self.assertIn("en", parsed)
        self.assertIn("bn", parsed)
        self.assertEqual(parsed["bn"]["tiktok_name"], "TikTok Bangla")
        self.assertEqual(parsed["bn"]["tiktok_session"], "enc_session_bn")

        # Test resolve_destination overlay
        base_channel = {
            "youtube_name": "Default YT",
            "facebook_name": "Default FB",
            "tiktok_name": "Default TT",
            "lang_destinations_json": serialized,
        }
        resolved_bn = resolve_destination(base_channel, "bn")
        self.assertEqual(resolved_bn["tiktok_name"], "TikTok Bangla")
        self.assertEqual(resolved_bn["tiktok_session"], "enc_session_bn")
        self.assertEqual(resolved_bn["_upload_lang"], "bn")

    def test_05_upload_service_tiktok_dispatch(self):
        """Verify upload_job dispatches to TikTok in dry-run mode."""
        # Create dummy video file
        dummy_video = Path(self.temp_dir) / "test_video.mp4"
        dummy_video.write_bytes(b"dummy video data")

        job_id = store.add_job(
            {
                "channel_id": 1,
                "title": "Autonomous AI Revolution",
                "description": "How AI is changing the world #AI #Tech",
                "tags": '["ai", "tech"]',
                "local_path": str(dummy_video),
                "video_type": "short",
                "upload_status": "ready",
            }
        )

        channel = {
            "id": 1,
            "youtube_name": "TechYT",
            "facebook_name": "TechFB",
            "tiktok_name": "TechTikTok",
        }

        # Force dry run
        with patch.object(settings, "dry_run_publish", True):
            res = upload_job(job_id, channel)
            self.assertTrue(res.get("ok"))
            platforms = [r.get("platform") for r in res.get("results", [])]
            self.assertIn("youtube", platforms)
            self.assertIn("facebook", platforms)
            self.assertIn("tiktok", platforms)

            tiktok_res = next(r for r in res["results"] if r.get("platform") == "tiktok")
            self.assertTrue(tiktok_res.get("ok"))
            self.assertTrue(str(tiktok_res.get("url")).startswith("dry-run://tiktok/"))

    def test_06_session_vault_tiktok_paths(self):
        """Verify session_vault resolves correct paths and handles status for TikTok."""
        st = session_vault.session_status("tiktok", channel_id=999, lang_code="en")
        self.assertIn("status", st)
        self.assertEqual(st.get("platform"), "tiktok")

        channel_dict = {"id": 999, "tiktok_name": "@Demo"}
        p_default = session_vault.paths_for_channel("tiktok", channel_dict, lang_code="en")
        self.assertIn("tiktok", str(p_default.get("user_data_dir", "")).lower())
        self.assertIn("999", str(p_default.get("user_data_dir", "")))

        p_bn = session_vault.paths_for_channel("tiktok", channel_dict, lang_code="bn")
        self.assertIn("bn", str(p_bn.get("user_data_dir", "")).lower())

    def test_07_browser_auth_start_login_tiktok(self):
        """Verify browser_auth start_login accepts tiktok platform and returns valid job."""
        from publishers.browser_auth import get_login_status, start_login

        with patch("publishers.browser_auth._run_capture") as mock_run:
            res = start_login(channel_id=1, platform="tiktok", lang_code="en")
            self.assertTrue(res.get("ok"))
            job_id = res.get("job_id")
            self.assertTrue(job_id)
            self.assertEqual(res.get("platform"), "tiktok")

            # Check status
            st = get_login_status(job_id)
            self.assertTrue(st.get("ok"))
            self.assertEqual(st.get("platform"), "tiktok")
            self.assertEqual(st.get("status"), "starting")


if __name__ == "__main__":
    unittest.main()

