import unittest
import tempfile
from pathlib import Path

from app import db as store
from publishers.comment_reply_agent import (
    draft_comment_reply,
    reply_youtube_post,
    reply_tiktok_post,
    reply_facebook_post,
    run_comment_reply_pass,
)


class TestStep10CommunityManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.orig_db = store.DB_PATH
        cls.test_db = Path(cls.temp_dir) / "test_step10.db"
        store.DB_PATH = cls.test_db
        store.init_db()

    @classmethod
    def tearDownClass(cls):
        store.DB_PATH = cls.orig_db
        import shutil
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_draft_comment_reply_human_creator_tone(self):
        """AI comment replies must be genuine human creator answers, never robotic cliches."""
        # English question
        rep_en = draft_comment_reply(
            video_title="The Power of Compound Interest",
            comment_text="Where can I learn more about this index fund strategy?",
            channel_name="Wealth Blueprint",
            lang_code="en",
            niche="Personal Finance",
        )
        self.assertGreaterEqual(len(rep_en), 15)
        self.assertNotIn("as an ai", rep_en.lower())
        self.assertNotIn("thank you for commenting", rep_en.lower())

        # Bengali comment
        rep_bn = draft_comment_reply(
            video_title="ধৈর্যের শক্তি",
            comment_text="খুব সুন্দর আলোচনা, অনেক কিছু শিখলাম।",
            channel_name="ইসলামিক জ্ঞান",
            lang_code="bn",
            niche="Islamic Teachings",
        )
        self.assertGreaterEqual(len(rep_bn), 10)
        self.assertNotIn("as an ai", rep_bn.lower())

    def test_multi_platform_reply_dispatch_and_db_logging(self):
        """Comments replied on YouTube, TikTok, and Facebook must be logged in post_messages table."""
        ch_id = store.upsert_channel({
            "name": "Omni Channel",
            "youtube_name": "OmniYT",
            "tiktok_name": "OmniTikTok",
            "facebook_name": "OmniFB",
            "niche": "Science",
        })
        ch = store.get_channel(ch_id)

        # Create 3 posts (one for each platform)
        p_yt_id = store.upsert_post_from_upload(
            job_id=101,
            channel_id=ch_id,
            platform="youtube",
            local_path="",
            title="Cosmic Secrets",
            remote_url="dry-run://youtube.com/watch?v=mock123",
            lang_code="en",
        )
        p_tt_id = store.upsert_post_from_upload(
            job_id=102,
            channel_id=ch_id,
            platform="tiktok",
            local_path="",
            title="Cosmic Secrets",
            remote_url="dry-run://tiktok.com/@omni/video/mock456",
            lang_code="en",
        )
        p_fb_id = store.upsert_post_from_upload(
            job_id=103,
            channel_id=ch_id,
            platform="facebook",
            local_path="",
            title="Cosmic Secrets",
            remote_url="dry-run://facebook.com/watch?v=mock789",
            lang_code="en",
        )

        # Dispatch replies
        res_yt = reply_youtube_post({"id": p_yt_id, "remote_url": "dry-run://youtube.com/watch?v=mock123", "title": "Cosmic Secrets", "lang_code": "en"}, ch)
        self.assertTrue(res_yt["ok"])
        self.assertEqual(res_yt["replied"], 1)

        res_tt = reply_tiktok_post({"id": p_tt_id, "remote_url": "dry-run://tiktok.com/@omni/video/mock456", "title": "Cosmic Secrets", "lang_code": "en"}, ch)
        self.assertTrue(res_tt["ok"])
        self.assertEqual(res_tt["replied"], 1)

        res_fb = reply_facebook_post({"id": p_fb_id, "remote_url": "dry-run://facebook.com/watch?v=mock789", "title": "Cosmic Secrets", "lang_code": "en"}, ch)
        self.assertTrue(res_fb["ok"])
        self.assertEqual(res_fb["replied"], 1)

        # Verify idempotency: duplicate run must reply 0
        res_tt_dup = reply_tiktok_post({"id": p_tt_id, "remote_url": "dry-run://tiktok.com/@omni/video/mock456", "title": "Cosmic Secrets", "lang_code": "en"}, ch)
        self.assertEqual(res_tt_dup["replied"], 0)

        # Verify stored messages in DB
        posts = store.list_posts(10)
        found_platforms = {m["platform"] for p in posts for m in p.get("messages", [])}
        self.assertIn("youtube", found_platforms)
        self.assertIn("tiktok", found_platforms)
        self.assertIn("facebook", found_platforms)

    def test_run_comment_reply_pass_orchestration(self):
        """run_comment_reply_pass must iterate and handle all 3 platforms seamlessly."""
        ch_id = store.upsert_channel({
            "name": "Auto Media",
            "youtube_name": "AutoYT",
            "tiktok_name": "AutoTT",
            "facebook_name": "AutoFB",
            "niche": "Motivation",
        })
        p_id = store.upsert_post_from_upload(
            job_id=201,
            channel_id=ch_id,
            platform="tiktok",
            local_path="",
            title="Discipline Over Motivation",
            remote_url="dry-run://tiktok.com/@autott/video/mot123",
            lang_code="en",
        )
        res = run_comment_reply_pass(max_posts=5, max_replies_each=1)
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res["handled"], 1)


if __name__ == "__main__":
    unittest.main()
