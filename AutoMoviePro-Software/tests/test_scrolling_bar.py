import os
import sys
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.notification.scrolling_bar import ScrollingNotificationManager

class TestScrollingNotification(unittest.TestCase):
    def setUp(self):
        self.manager = ScrollingNotificationManager()

    def test_get_announcements_localization(self):
        notices_bn = self.manager.get_announcements(language="bn")
        self.assertGreater(len(notices_bn), 0)
        # Verify at least one contains Bengali greeting or announcement
        all_texts_bn = [n["text"] for n in notices_bn]
        self.assertTrue(any("অটোমুভি" in t or "সার্ভার" in t for t in all_texts_bn))

        notices_en = self.manager.get_announcements(language="en")
        self.assertGreater(len(notices_en), 0)
        all_texts_en = [n["text"] for n in notices_en]
        self.assertTrue(any("Welcome" in t or "maintenance" in t for t in all_texts_en))

    def test_add_announcement(self):
        res = self.manager.add_announcement(
            title_en="Special update released!",
            title_bn="বিশেষ আপডেট প্রকাশ করা হয়েছে!",
            notice_type="info",
            priority="normal"
        )
        self.assertTrue(res["ok"])
        notice = res["notice"]
        self.assertEqual(notice["priority"], "normal")

        # Verify it appears in localized list
        bn_list = self.manager.get_announcements(language="bn")
        self.assertEqual(bn_list[0]["text"], "বিশেষ আপডেট প্রকাশ করা হয়েছে!")

    def test_marquee_settings(self):
        settings = self.manager.get_marquee_settings("fast")
        self.assertEqual(settings["scroll_speed_px_sec"], 80)
        self.assertTrue(settings["pause_on_hover"])


if __name__ == "__main__":
    unittest.main()
