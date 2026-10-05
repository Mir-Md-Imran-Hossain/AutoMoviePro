"""
Multi-angle unit tests for Step 3:
Daily Autonomous Cadence (1 Long + 1 Short Scheduler, Catch-up, and Multi-Platform Multi-Lang Dispatch).
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import db as store
from app.config import settings
from app.scheduler_service import SchedulerService
from publishers.upload_service import upload_job


class TestStep3Cadence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db = Path(cls.temp_dir) / "test.db"
        store.DB_PATH = cls.test_db
        store.init_db()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_timing_and_overdue_catchup(self):
        """Verify scheduler triggers on exact time or catches up missed upload windows."""
        # Target time is 12:00 PM
        target = "12:00"

        # Morning: before target -> False
        self.assertFalse(SchedulerService._is_time_or_overdue("11:30", target))
        self.assertFalse(SchedulerService._is_time_or_overdue("11:59", target))

        # Exactly at target -> True
        self.assertTrue(SchedulerService._is_time_or_overdue("12:00", target))

        # Afternoon: PC was sleeping or restarted -> True (catch-up)
        self.assertTrue(SchedulerService._is_time_or_overdue("12:05", target))
        self.assertTrue(SchedulerService._is_time_or_overdue("14:30", target))

    def test_02_daily_idempotency_governor(self):
        """Verify day_key guarantees strictly 1 upload per type per day."""
        service = SchedulerService()
        channel = {
            "id": 101,
            "short_upload_time": "12:00",
            "long_upload_time": "18:00",
            "youtube_name": "TestYT",
            "facebook_name": "TestFB",
            "tiktok_name": "TestTT",
            "enabled": 1,
        }

        today = datetime.now().date().isoformat()
        day_key = f"upload_101_short_{today}"

        # Ensure not uploaded yet
        self.assertNotEqual(store.get_meta(day_key), "1")

        # Mock claim_or_generate & upload_job
        dummy_video = Path(self.temp_dir) / "short_test.mp4"
        dummy_video.write_bytes(b"dummy")

        job_id = store.add_job(
            {
                "channel_id": 101,
                "video_type": "short",
                "title": "Short Test Video",
                "local_path": str(dummy_video),
                "upload_status": "ready_to_upload",
            }
        )

        with patch.object(service, "_claim_or_generate", return_value=job_id):
            with patch("publishers.upload_service.upload_job", return_value={"ok": True, "results": []}) as mock_up:
                # Trigger upload at 13:00 (overdue catch-up)
                service._maybe_upload(channel, "short", "12:00", "13:00")
                mock_up.assert_called_once()
                self.assertEqual(store.get_meta(day_key), "1")

                # Try triggering again 5 minutes later on the same day -> must be ignored!
                mock_up.reset_mock()
                service._maybe_upload(channel, "short", "12:00", "13:05")
                mock_up.assert_not_called()

    def test_03_multilingual_localized_upload_dispatch(self):
        """Verify upload_job dispatches master video and localized video to language destinations."""
        work_dir = Path(self.temp_dir) / "job_multilang"
        work_dir.mkdir(parents=True, exist_ok=True)
        master_video = work_dir / "final_video.mp4"
        master_video.write_bytes(b"master_en_data")

        # Create localized Bangla video package
        loc_dir = work_dir / "LOCALIZED" / "Bangla"
        loc_dir.mkdir(parents=True, exist_ok=True)
        bn_video = loc_dir / "video.mp4"
        bn_video.write_bytes(b"bangla_video_data")
        (loc_dir / "meta.json").write_text(
            json.dumps({"title": "বাংলা টাইটেল", "description": "বাংলা বিবরণ"}),
            encoding="utf-8",
        )

        job_id = store.add_job(
            {
                "channel_id": 202,
                "video_type": "long",
                "title": "Master English Title",
                "description": "Master English Description",
                "local_path": str(master_video),
                "upload_status": "ready_to_upload",
            }
        )

        channel = {
            "id": 202,
            "youtube_name": "MainEnglishYT",
            "facebook_name": "MainEnglishFB",
            "tiktok_name": "@MainEnglishTT",
            "languages_json": json.dumps(["en", "bn"]),
            "lang_destinations_json": json.dumps(
                {
                    "en": {
                        "youtube_name": "MainEnglishYT",
                        "facebook_name": "MainEnglishFB",
                        "tiktok_name": "@MainEnglishTT",
                    },
                    "bn": {
                        "youtube_name": "BanglaAutoMovieYT",
                        "facebook_name": "BanglaAutoMovieFB",
                        "tiktok_name": "@BanglaAutoMovieTT",
                    },
                }
            ),
        }

        with patch.object(settings, "dry_run_publish", True):
            res = upload_job(job_id, channel)
            self.assertTrue(res.get("ok"))
            results = res.get("results", [])

            # Check that both English (master) and Bangla (localized) accounts received uploads
            platforms = [r.get("platform") for r in results]
            self.assertIn("youtube", platforms)
            self.assertIn("facebook", platforms)
            self.assertIn("tiktok", platforms)
            self.assertIn("youtube_bn", platforms)
            self.assertIn("facebook_bn", platforms)
            self.assertIn("tiktok_bn", platforms)


if __name__ == "__main__":
    unittest.main()
