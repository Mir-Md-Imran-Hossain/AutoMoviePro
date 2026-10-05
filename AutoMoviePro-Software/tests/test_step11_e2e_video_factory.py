import unittest
import tempfile
import json
import shutil
from pathlib import Path

from app import db as store
from pipeline.niche_director import _fallback_plan
from pipeline.content_humanizer import find_ai_tells
from pipeline.media_assets import render_high_aesthetic_thumbnail
from pipeline.subtitle_burn import font_size_for_canvas, margin_v_for_canvas, srt_to_styled_ass
from pipeline.subtitle_align import proportional_cues, cues_to_srt, validate_cues
from pipeline.audio_design.mix_policy import MixPolicy
from pipeline.lang_destinations import serialize_lang_destinations, parse_lang_destinations
from publishers.upload_service import upload_job
from publishers.comment_reply_agent import run_comment_reply_pass
from app.scheduler_service import SchedulerService


class TestStep11E2EVideoFactory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig_db = store.DB_PATH
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db = Path(cls.temp_dir) / "test_e2e.db"
        store.DB_PATH = cls.test_db
        store.init_db()

    @classmethod
    def tearDownClass(cls):
        store.DB_PATH = cls.orig_db
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_e2e_video_factory_complete_lifecycle(self):
        """Complete verification of the 24/7 autonomous Video Factory pipeline."""
        # 1. Multi-Platform Channel Setup with Multi-Language Slots (English + Bengali)
        lang_dest = {
            "en": {
                "youtube_name": "OmniFactoryEn",
                "facebook_name": "OmniFactoryEnFB",
                "tiktok_name": "@OmniFactoryEnTT",
                "youtube_session": "enc_yt_en",
                "facebook_session": "enc_fb_en",
                "tiktok_session": "enc_tt_en",
            },
            "bn": {
                "youtube_name": "OmniFactoryBn",
                "facebook_name": "OmniFactoryBnFB",
                "tiktok_name": "@OmniFactoryBnTT",
                "youtube_session": "enc_yt_bn",
                "facebook_session": "enc_fb_bn",
                "tiktok_session": "enc_tt_bn",
            },
        }
        cid = store.upsert_channel({
            "name": "Omni Video Factory",
            "niche": "Islamic Teachings",
            "youtube_name": "OmniFactoryEn",
            "facebook_name": "OmniFactoryEnFB",
            "tiktok_name": "@OmniFactoryEnTT",
            "lang_slots": 2,
            "purchased_slots": 0,
            "languages_json": json.dumps(["en", "bn"]),
            "lang_destinations_json": serialize_lang_destinations(lang_dest),
            "enabled": 1,
        })
        ch = store.get_channel(cid)
        self.assertIsNotNone(ch)
        parsed_dests = parse_lang_destinations(ch.get("lang_destinations_json", ""))
        self.assertEqual(len(parsed_dests), 2)
        self.assertIn("tiktok_name", parsed_dests["bn"])

        # 2. Dynamic Industrial Script & Niche Fallback Generation
        plan = _fallback_plan(
            niche="Islamic Teachings",
            topic="Steadfastness in Hardship",
            video_type="short",
            max_seconds=45,
            channel_name="Omni Video Factory",
        )
        self.assertGreaterEqual(len(plan["scenes"]), 4)
        for sc in plan["scenes"]:
            tells = find_ai_tells(sc["narration"])
            self.assertEqual(len(tells), 0, f"Found AI tells: {tells}")
            self.assertNotIn("papyrus", sc["narration"].lower())
            self.assertNotIn("artemis", sc["narration"].lower())

        # 3. Audio Mastering & Sidechain Ducking Policy Verification
        policy = MixPolicy()
        self.assertEqual(policy.duck_music_db, -16.0)
        self.assertLessEqual(policy.duck_music_db, -14.0)
        self.assertGreaterEqual(policy.duck_music_db, -18.0)

        # 4. Native High-Aesthetic Thumbnail Generation
        thumb_path = Path(self.temp_dir) / "factory_thumb.jpg"
        render_high_aesthetic_thumbnail(
            title="The Unshakable Heart — Timeless Lessons of Patience",
            subject="Steadfastness",
            out_path=thumb_path,
            niche="Islamic Teachings",
        )
        self.assertTrue(thumb_path.is_file())
        self.assertGreater(thumb_path.stat().st_size, 15000)

        # 5. Dynamic Short-Form Subtitle Engine Verification
        short_narration = "True patience is not passivity. It is strength under intense pressure."
        cues = proportional_cues(short_narration, duration_sec=5.0, is_short=True)
        self.assertGreaterEqual(len(cues), 3)
        val = validate_cues(cues, duration_sec=5.0, spoken_text=short_narration)
        self.assertTrue(val["passed"])

        srt_path = Path(self.temp_dir) / "short.srt"
        ass_path = Path(self.temp_dir) / "short.ass"
        srt_path.write_text(cues_to_srt(cues), encoding="utf-8")
        res_ass = srt_to_styled_ass(srt_path, ass_path, size="1080x1920", lang="en", is_short=True)
        self.assertTrue(res_ass.is_file())
        ass_content = res_ass.read_text(encoding="utf-8")
        self.assertIn("PlayResX: 1080", ass_content)
        self.assertIn("&H0000FFFF", ass_content)  # Yellow font
        self.assertIn(",60,80,", ass_content)     # Safe platform margins

        # 6. Autonomous Multi-Platform Localized Dispatch (Dry-Run)
        dummy_video = Path(self.temp_dir) / "master.mp4"
        dummy_video.write_bytes(b"dummy video binary")
        localized_dir = Path(self.temp_dir) / "LOCALIZED" / "bn"
        localized_dir.mkdir(parents=True, exist_ok=True)
        dummy_bn = localized_dir / "video.mp4"
        dummy_bn.write_bytes(b"dummy bengali video binary")
        (localized_dir / "meta.json").write_text(
            json.dumps({"title": "অটল হৃদয়", "description": "ধৈর্যের শিক্ষা"}),
            encoding="utf-8",
        )

        job_id = store.add_job({
            "channel_id": cid,
            "title": "The Unshakable Heart",
            "description": "Patience in adversity #Patience #Steadfastness",
            "tags": '["patience", "faith"]',
            "local_path": str(dummy_video),
            "video_type": "short",
            "upload_status": "ready",
        })

        ch = store.get_channel(cid)
        from app.config import settings
        from unittest.mock import patch

        with patch.object(settings, "dry_run_publish", True):
            upload_res = upload_job(
                job_id,
                channel=ch,
            )
            self.assertTrue(upload_res["ok"])
            results = upload_res.get("results", [])
            # English + Bengali * 3 platforms = 6 total dispatched uploads
            self.assertEqual(len(results), 6)
            platforms = [r.get("platform") for r in results]
            self.assertIn("youtube", platforms)
            self.assertIn("facebook", platforms)
            self.assertIn("tiktok", platforms)
            self.assertIn("youtube_bn", platforms)
            self.assertIn("facebook_bn", platforms)
            self.assertIn("tiktok_bn", platforms)

        # 7. AI Multi-Platform Community Management Verification
        reply_pass = run_comment_reply_pass(max_posts=6, max_replies_each=1)
        self.assertTrue(reply_pass["ok"])
        self.assertGreaterEqual(reply_pass["handled"], 1)

        # Check that replies are logged in database
        posts = store.list_posts(10)
        self.assertGreaterEqual(len(posts), 6)
        all_replies = [m["reply"] for p in posts for m in p.get("messages", [])]
        self.assertGreaterEqual(len(all_replies), 1)
        for r in all_replies:
            self.assertNotIn("as an ai", r.lower())

        # 8. Cadence / Overdue Catch-up Verification
        sched = SchedulerService()
        self.assertTrue(sched._is_time_or_overdue("09:30", "09:00"))
        self.assertFalse(sched._is_time_or_overdue("08:30", "09:00"))


if __name__ == "__main__":
    unittest.main()
