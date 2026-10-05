"""Comprehensive unit & integration tests for Step 2: Channel, Page, Language Package & Assets Setup.
Standard library unittest implementation (zero external dependency).

Tests:
- User profile & niche setup
- Tier-based language unlocking (2999 BDT base, 999 BDT addon, 4999 BDT full)
- Multi-platform channel profiles per language (YouTube, Facebook, TikTok)
- Separate Long/Short upload schedules per language
- Dedicated Logo & Intro video paths per language
- Lock enforcement for unpurchased languages
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))

from app.setup.channel_setup import (
    LANGUAGE_CATALOG,
    SUPPORTED_NICHES,
    SetupManager,
)


class TestChannelSetup(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.manager = SetupManager(data_dir=Path(self.tmp_dir.name))

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_user_profile_and_niche(self):
        """Validates saving user contact details and choosing a supported niche."""
        self.assertIn("Technology & AI Innovations", SUPPORTED_NICHES)
        res = self.manager.update_user_profile(
            user_name="Zahid Hasan",
            mobile_number="01756160993",
            channel_niche="Islamic History & Moral Stories",
        )
        self.assertEqual(res["user_name"], "Zahid Hasan")
        self.assertEqual(res["mobile_number"], "01756160993")
        self.assertEqual(res["channel_niche"], "Islamic History & Moral Stories")

    def test_base_package_tier_unlocks_two_languages(self):
        """Base 2999 BDT package unlocks English + 1 optional language (e.g. Bangla)."""
        res = self.manager.set_package_tier("base_2999", selected_optional_lang="bn")
        self.assertEqual(res["package_tier"], "base_2999")
        self.assertEqual(sorted(res["unlocked_languages"]), ["bn", "en"])
        self.assertIn("en", res["profiles_by_language"])
        self.assertIn("bn", res["profiles_by_language"])

    def test_full_package_tier_unlocks_all_six_languages(self):
        """Full 4999 BDT package unlocks all 6 supported languages simultaneously."""
        res = self.manager.set_package_tier("full_4999")
        self.assertEqual(res["package_tier"], "full_4999")
        self.assertEqual(len(res["unlocked_languages"]), 6)
        for code in ["en", "bn", "hi", "ur", "ta", "ml"]:
            self.assertIn(code, res["unlocked_languages"])
            self.assertIn(code, res["profiles_by_language"])

    def test_addon_language_unlock_and_lock_rejection(self):
        """Adding a 999 BDT addon unlocks an individual language; locked languages throw error."""
        self.manager.set_package_tier("base_2999", selected_optional_lang="bn")

        # Attempting to configure Hindi before unlocking must raise PermissionError
        with self.assertRaises(PermissionError):
            self.manager.update_language_profile(
                "hi",
                youtube_channel_name="Hindi Tech Zone",
            )

        # Unlock Hindi via addon
        res = self.manager.unlock_additional_language("hi")
        self.assertIn("hi", res["unlocked_languages"])

        # Now configuration should succeed without error
        updated = self.manager.update_language_profile(
            "hi",
            youtube_channel_name="Hindi Tech Zone",
            facebook_page_name="Hindi Tech FB",
            tiktok_account_name="hinditech_tiktok",
        )
        hi_prof = updated["profiles_by_language"]["hi"]
        self.assertEqual(hi_prof["youtube_channel_name"], "Hindi Tech Zone")
        self.assertEqual(hi_prof["facebook_page_name"], "Hindi Tech FB")
        self.assertEqual(hi_prof["tiktok_account_name"], "hinditech_tiktok")

    def test_separate_schedules_and_brand_assets(self):
        """Verifies distinct Long/Short video schedules and Logo/Intro assets per language."""
        self.manager.set_package_tier("base_2999", selected_optional_lang="bn")

        self.manager.update_language_profile(
            "bn",
            youtube_channel_name="Bangla History Hub",
            facebook_page_name="Bangla History Page",
            short_schedule="09:30",
            long_schedule="21:00",
            logo_path="/assets/bn_logo.png",
            intro_video_path="/assets/bn_intro.mp4",
            cookie_file="/cookies/bn_fb_yt.json",
            official_api_enabled=True,
            official_api_key="AIzaSyBnApiKey123",
        )

        prof = self.manager.get_profile()["profiles_by_language"]["bn"]
        self.assertEqual(prof["short_schedule"], "09:30")
        self.assertEqual(prof["long_schedule"], "21:00")
        self.assertEqual(prof["logo_path"], "/assets/bn_logo.png")
        self.assertEqual(prof["intro_video_path"], "/assets/bn_intro.mp4")
        self.assertEqual(prof["cookie_file"], "/cookies/bn_fb_yt.json")
        self.assertTrue(prof["official_api_enabled"])
        self.assertEqual(prof["official_api_key"], "AIzaSyBnApiKey123")

    def test_pricing_package_definitions(self):
        """Verifies pricing packages match requirements:
        - Base: 2999 BDT (en + 1 optional)
        - Addon: 999 BDT (per unlocked new language)
        - Full: 4999 BDT (all 6 languages)
        """
        pricing = self.manager.get_pricing_info()
        self.assertEqual(pricing["base_price_bdt"], 2999)
        self.assertEqual(pricing["addon_price_bdt"], 999)
        self.assertEqual(pricing["full_price_bdt"], 4999)

        base_pkg = pricing["base_package"]
        self.assertEqual(base_pkg["price_bdt"], 2999)
        self.assertEqual(base_pkg["included_languages_count"], 2)
        self.assertIn("ইংরেজি + ১টি ঐচ্ছিক ভাষা", base_pkg["description"])

        addon_pkg = pricing["language_addon"]
        self.assertEqual(addon_pkg["price_bdt"], 999)
        self.assertTrue(addon_pkg["per_language"])

        full_pkg = pricing["full_package"]
        self.assertEqual(full_pkg["price_bdt"], 4999)
        self.assertEqual(full_pkg["included_languages_count"], 6)
        self.assertEqual(sorted(full_pkg["included_languages"]), ["bn", "en", "hi", "ml", "ta", "ur"])

    def test_separate_platform_objects_per_language(self):
        """Verifies youtube, facebook, and tiktok are stored as separate dedicated objects."""
        self.manager.set_package_tier("base_2999", selected_optional_lang="bn")
        updated = self.manager.update_language_profile(
            "bn",
            youtube={
                "channel_name": "Bangla Tube Pro",
                "channel_id": "UC_Bangla123",
                "official_api_enabled": True,
                "official_api_key": "AIzaSyTestKey",
            },
            facebook={
                "page_name": "Bangla Page Pro",
                "page_id": "FB_PAGE_999",
            },
            tiktok={
                "tiktok_id": "@banglamovie_official",
                "account_name": "Bangla Movie Pro",
            },
        )
        bn_prof = updated["profiles_by_language"]["bn"]

        # 1. Distinct YouTube object
        self.assertIsInstance(bn_prof["youtube"], dict)
        self.assertEqual(bn_prof["youtube"]["channel_name"], "Bangla Tube Pro")
        self.assertEqual(bn_prof["youtube"]["channel_id"], "UC_Bangla123")
        self.assertTrue(bn_prof["youtube"]["official_api_enabled"])
        self.assertEqual(bn_prof["youtube"]["official_api_key"], "AIzaSyTestKey")

        # 2. Distinct Facebook object
        self.assertIsInstance(bn_prof["facebook"], dict)
        self.assertEqual(bn_prof["facebook"]["page_name"], "Bangla Page Pro")
        self.assertEqual(bn_prof["facebook"]["page_id"], "FB_PAGE_999")

        # 3. Distinct TikTok object
        self.assertIsInstance(bn_prof["tiktok"], dict)
        self.assertEqual(bn_prof["tiktok"]["tiktok_id"], "@banglamovie_official")
        self.assertEqual(bn_prof["tiktok"]["account_name"], "Bangla Movie Pro")

        # 4. Backward-compatible top-level convenience mirrors
        self.assertEqual(bn_prof["youtube_channel_name"], "Bangla Tube Pro")
        self.assertEqual(bn_prof["facebook_page_name"], "Bangla Page Pro")
        self.assertEqual(bn_prof["tiktok_id"], "@banglamovie_official")
        self.assertEqual(bn_prof["tiktok_account_name"], "Bangla Movie Pro")


if __name__ == "__main__":
    unittest.main()

