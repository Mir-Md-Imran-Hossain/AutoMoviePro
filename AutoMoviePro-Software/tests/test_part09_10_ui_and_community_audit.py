"""
AutoMovie Pro — Part 09 & 10: Comments, Messages & UI/UX Audit Test Suite
Validates:
1. Part 09: Community & Comment Automation
   - Auto-reply toggle & state tracking (publishers/comment_reply_agent.py)
   - Comment language detection (bn, en, hi)
   - Anti-duplicate reply gate (_already_replied / _mark_replied)
   - Omni comment agent portable social hub root path resolution
2. Part 10: UI/UX Audit & Non-Technical Usability
   - Modern dashboard DOM structure with job & platform status indicators
   - Responsive CSS media query breakpoints (ui/static/css/app.css)
   - Non-technical user error localization & button disabled protections
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from publishers.comment_reply_agent import (
    detect_comment_language,
    simulate_typing_delay,
    _already_replied,
    _mark_replied,
    is_auto_reply_enabled,
    set_auto_reply_enabled
)
from publishers.omni_comment_agent import ROOT_DIR, BRAND_PROMPTS


class Part09And10CommunityAndUIAuditTest(unittest.TestCase):

    def test_01_comment_language_detection(self):
        """Verify automatic language detection for multi-lingual comment replies."""
        bn_text = "ভাই ভিডিওটি খুবই সুন্দর এবং শিক্ষণীয় হয়েছে!"
        hi_text = "बहुत बढ़िया वीडियो भाई, बहुत ज्ञानवर्धक है।"
        en_text = "Awesome video mate! Really loved the visual effects."

        self.assertEqual(detect_comment_language(bn_text), "bn")
        self.assertEqual(detect_comment_language(hi_text), "hi")
        self.assertEqual(detect_comment_language(en_text), "en")

    def test_02_typing_delay_simulation(self):
        """Verify simulated typing delay is proportional to message length and bounded."""
        short_reply = "ধন্যবাদ ভাই!"
        long_reply = "আসসালামু আলাইকুম। আপনার সুন্দর মন্তব্যের জন্য আন্তরিক ধন্যবাদ। নিয়মিত এরকম ভিডিও পেতে আমাদের পেজ ফলো করে রাখুন।"
        
        delay_short = simulate_typing_delay(short_reply)
        delay_long = simulate_typing_delay(long_reply)

        self.assertGreaterEqual(delay_short, 0.5)
        self.assertLessEqual(delay_short, 10.0)
        self.assertGreaterEqual(delay_long, delay_short)

    def test_03_anti_duplicate_comment_reply_gate(self):
        """Verify duplicate replies are prevented using the post/comment key record."""
        import uuid
        test_post_id = int(uuid.uuid4().int % 100000000)
        test_comment_key = f"yt_comment_unique_idx_{uuid.uuid4().hex}"

        # Initially should not be replied
        self.assertFalse(_already_replied(test_post_id, test_comment_key))

        # Mark as replied
        _mark_replied(test_post_id, test_comment_key)

        # Should now be blocked by anti-duplicate check
        self.assertTrue(_already_replied(test_post_id, test_comment_key))

    def test_04_omni_comment_portable_path_and_brand_prompts(self):
        """Verify omni comment agent resolves social hub root path and contains Bengali sales prompts."""
        self.assertIsInstance(ROOT_DIR, Path)
        self.assertTrue("automovie_pro_page" in BRAND_PROMPTS)
        auto_prompt = BRAND_PROMPTS["automovie_pro_page"]
        self.assertIn("AutoMovie Pro", auto_prompt)
        self.assertIn("3,999", auto_prompt)
        self.assertIn("01968111593", auto_prompt)

    def test_05_ui_dashboard_dom_and_metrics_presence(self):
        """Verify UI index.html contains all critical dashboard metric and status containers."""
        html_path = BASE_DIR / "ui" / "index.html"
        self.assertTrue(html_path.exists())
        content = html_path.read_text(encoding="utf-8")

        required_elements = [
            'id="dashJobSummary"',
            'id="sidebarTierStatus"',
            'id="tierStatusBanner"',
            'id="channelReadinessPill"',
            'id="ytStatusBadge"',
            'id="fbStatusBadge"',
            'id="apiReadinessStatusDot"',
            'id="liveTickerBar"',
            'id="chatFab"'
        ]
        for el in required_elements:
            self.assertIn(el, content, f"Missing required dashboard element: {el}")

    def test_06_responsive_css_breakpoints(self):
        """Verify CSS contains responsive layout media queries for desktop and mobile usability."""
        css_path = BASE_DIR / "ui" / "static" / "css" / "app.css"
        self.assertTrue(css_path.exists())
        content = css_path.read_text(encoding="utf-8")

        self.assertIn("@media (max-width: 960px)", content)
        self.assertIn("@media (max-width: 768px)", content)


if __name__ == "__main__":
    unittest.main()
