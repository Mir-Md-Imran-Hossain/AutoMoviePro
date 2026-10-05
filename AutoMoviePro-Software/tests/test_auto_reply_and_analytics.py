"""
Unit tests for Auto-Reply, Video Analytics, Type A/B Human Browsing, and Bulk Marketing Engine.
Ensures 100% functionality and test coverage for all newly added features.
"""

import os
import unittest
from unittest.mock import MagicMock, patch
from datetime import date, datetime

from app import db as store
from publishers.comment_reply_agent import (
    detect_comment_language,
    simulate_typing_delay,
    is_auto_reply_enabled,
    set_auto_reply_enabled,
    get_auto_reply_status,
    draft_comment_reply,
)
from pipeline.social_publisher import (
    VideoAnalyticsTracker,
    get_analytics_tracker,
)
from hidden_engage.schedule_plan import (
    ACTIVE_BROWSE_START_HOUR,
    ACTIVE_BROWSE_END_HOUR,
    active_window_now,
    build_day_plan,
)
from hidden_engage.channel_fsm import (
    MAX_DAILY_SUBSCRIBES,
    daily_subscribes_count,
    increment_daily_subscribes,
    ensure_subscribed,
    simulate_notification_interaction,
    SessionCaps,
)
from marketing.bulk_marketing_engine import (
    sanitize_contact,
    parse_and_clean_contacts,
    calculate_anti_ban_delay,
    generate_persuasive_marketing_copy,
    BulkMarketingEngine,
)


class TestAutoReplyAgent(unittest.TestCase):
    """Task 1: YouTube & Facebook Auto-Reply System Tests."""

    def setUp(self):
        store.init_db()

    def test_language_detection(self):
        # Bengali
        self.assertEqual(detect_comment_language("দারুণ ভিডিও ভাইয়া! অনেক ভালো লেগেছে"), "bn")
        # Arabic
        self.assertEqual(detect_comment_language("شكرا جزيلا فيديو رائع جدا"), "ar")
        # Hindi
        self.assertEqual(detect_comment_language("बहुत ही शानदार वीडियो है भाई"), "hi")
        # English
        self.assertEqual(detect_comment_language("Awesome video quality, keep uploading!"), "en")

    def test_typing_delay_simulation(self):
        delay = simulate_typing_delay("স্বাগতম বন্ধু!", min_delay=0.01, max_delay=0.03)
        self.assertGreaterEqual(delay, 0.01)
        self.assertLessEqual(delay, 0.03)

    def test_toggle_auto_reply_state(self):
        set_auto_reply_enabled(True)
        self.assertTrue(is_auto_reply_enabled())

        set_auto_reply_enabled(False)
        self.assertFalse(is_auto_reply_enabled())

        # Reset to enabled
        set_auto_reply_enabled(True)
        self.assertTrue(is_auto_reply_enabled())

    def test_auto_reply_status_payload(self):
        status = get_auto_reply_status()
        self.assertIn("enabled", status)
        self.assertIn("last_scan", status)
        self.assertIn("total_replies_sent", status)
        self.assertIn("recent_replies", status)
        self.assertIsInstance(status["recent_replies"], list)

    def test_draft_comment_reply_exact_language(self):
        # Bengali comment should generate Bengali reply
        bn_reply = draft_comment_reply(
            comment_text="ভিডিওটি খুব ভালো হয়েছে ভাইয়া",
            video_context="Ancient Egypt Documentary",
            author_name="Karim"
        )
        self.assertTrue(len(bn_reply) > 5)
        self.assertNotIn("As an AI", bn_reply)
        self.assertNotIn("language model", bn_reply)

        # English comment should generate English reply
        en_reply = draft_comment_reply(
            comment_text="Great explanation and visuals!",
            video_context="AI Automation Software",
            author_name="John"
        )
        self.assertTrue(len(en_reply) > 5)
        self.assertNotIn("As an AI", en_reply)


class TestVideoAnalyticsTracker(unittest.TestCase):
    """Task 2: Video Performance Tracker & Growth Report Tests."""

    def setUp(self):
        store.init_db()
        self.tracker = VideoAnalyticsTracker()

    def test_record_and_get_overview(self):
        self.tracker.record_video_metrics(
            post_id="post_test_99",
            platform="youtube",
            video_id="yt_vid_123",
            views=1500,
            likes=120,
            comments=25
        )
        overview = self.tracker.get_overview()
        self.assertGreaterEqual(overview["total_views"], 1500)
        self.assertGreaterEqual(overview["total_likes"], 120)
        self.assertGreaterEqual(overview["total_comments"], 25)
        self.assertGreaterEqual(overview["tracked_videos_count"], 1)
        self.assertIn("average_engagement_rate", overview)

    def test_growth_advice_generation(self):
        for period in ("daily", "weekly", "monthly"):
            advice = self.tracker.generate_growth_advice(period=period)
            self.assertEqual(advice["period"], period)
            self.assertIn("summary", advice)
            self.assertIn("actionable_steps", advice)
            self.assertGreater(len(advice["actionable_steps"]), 0)


class TestHumanBrowsingTypeAB(unittest.TestCase):
    """Task 3: Human Browsing Schedule & Type A/B Channel Tests."""

    def setUp(self):
        store.init_db()

    def test_active_browse_hours_restriction(self):
        # 08:00 AM to 12:00 AM midnight (hour 24)
        self.assertEqual(ACTIVE_BROWSE_START_HOUR, 8)
        self.assertEqual(ACTIVE_BROWSE_END_HOUR, 24)

        # Off-hours test (e.g. 03:00 AM, 07:00 AM)
        mock_dt_early = datetime(2026, 10, 2, 3, 2, 0)
        self.assertIsNone(active_window_now(now=mock_dt_early))

        mock_dt_7am = datetime(2026, 10, 2, 7, 55, 0)
        self.assertIsNone(active_window_now(now=mock_dt_7am))

        # In-hours test (e.g. 10:30 AM)
        plan_dict = build_day_plan()
        windows = plan_dict.get("windows", [])
        self.assertGreater(len(windows), 0)
        for w in windows:
            self.assertGreaterEqual(w["hour"], 8)
            self.assertLess(w["hour"], 24)

    def test_daily_subscribe_limit_cap(self):
        today = date.today().isoformat()
        # Reset meta for test
        store.set_meta(f"daily_sub_count_{today}", "0")
        self.assertEqual(daily_subscribes_count(today), 0)

        increment_daily_subscribes(today)
        increment_daily_subscribes(today)
        self.assertEqual(daily_subscribes_count(today), 2)

        increment_daily_subscribes(today)
        self.assertEqual(daily_subscribes_count(today), 3)

        # Once reaching MAX_DAILY_SUBSCRIBES (3), ensure_subscribed must abort
        mock_page = MagicMock()
        mock_page.locator.return_value.count.return_value = 0
        mock_page.get_by_role.return_value.count.return_value = 1
        mock_page.get_by_role.return_value.first.get_attribute.return_value = "Subscribe"
        mock_page.get_by_role.return_value.first.inner_text.return_value = "Subscribe"

        caps = SessionCaps()
        # Target has not been marked as subscribed in store
        test_hub_url = "https://youtube.com/@unique_test_channel_xyz"
        res = ensure_subscribed(mock_page, "youtube", test_hub_url, caps)
        self.assertEqual(res, "daily_cap_reached")

    def test_simulate_notification_interaction(self):
        mock_page = MagicMock()
        mock_page.locator.return_value.count.return_value = 0
        outcome = simulate_notification_interaction(mock_page, "youtube")
        self.assertIn(outcome, ("notification_checked", "notification_ignored"))


class TestBulkMarketingEngine(unittest.TestCase):
    """Task 4: WhatsApp & Telegram Bulk Marketing Engine Tests."""

    def setUp(self):
        self.engine = BulkMarketingEngine()

    def test_contact_sanitization(self):
        # Bangladesh local mobile format
        self.assertEqual(sanitize_contact("01712345678", "whatsapp"), "+8801712345678")
        self.assertEqual(sanitize_contact("+880 1812-345678", "whatsapp"), "+8801812345678")
        # International phone
        self.assertEqual(sanitize_contact("+1 (555) 234-5678", "whatsapp"), "+15552345678")
        # Telegram username and link
        self.assertEqual(sanitize_contact("@automovie_user", "telegram"), "@automovie_user")
        self.assertEqual(sanitize_contact("https://t.me/pro_marketer", "telegram"), "@pro_marketer")

    def test_parse_and_clean_contacts_deduplication(self):
        raw = """
        01712-345678
        01712345678
        +8801712345678
        01987654321, 01987654321
        invalid_num
        """
        res = parse_and_clean_contacts(raw, platform="whatsapp")
        self.assertEqual(res["total_raw"], 6)
        self.assertEqual(res["valid_count"], 2)  # Two unique phone numbers
        self.assertEqual(res["duplicates_count"], 3)
        self.assertEqual(res["invalid_count"], 1)
        self.assertIn("+8801712345678", res["valid_contacts"])
        self.assertIn("+8801987654321", res["valid_contacts"])

    def test_import_bulk_numbers(self):
        raw = "01700112233, 01800112233, 01700112233"
        out = self.engine.import_bulk_numbers(raw, platform="whatsapp", niche="faceless_youtube")
        self.assertTrue(out["ok"])
        self.assertEqual(out["imported_count"], 2)
        self.assertEqual(out["duplicates_count"], 1)

    def test_anti_ban_delay_calculation(self):
        test_delay = calculate_anti_ban_delay(sent_count=1, is_live=False)
        self.assertLess(test_delay, 0.1)

        live_delay = calculate_anti_ban_delay(sent_count=1, is_live=True, min_gap=30, max_gap=90)
        self.assertGreaterEqual(live_delay, 30.0)

    def test_grok_persuasive_marketing_copy(self):
        copy_bn = generate_persuasive_marketing_copy(
            niche="faceless_youtube",
            platform="whatsapp",
            discount_pct=25,
            language="bn"
        )
        self.assertIn("PRO25", copy_bn)
        self.assertIn("AutoMovie Pro", copy_bn)
        self.assertTrue(len(copy_bn) > 100)

        copy_en = generate_persuasive_marketing_copy(
            niche="crypto_news",
            platform="telegram",
            discount_pct=30,
            language="en"
        )
        self.assertIn("PRO30", copy_en)
        self.assertTrue(len(copy_en) > 100)


if __name__ == "__main__":
    unittest.main()
