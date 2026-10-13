"""Unit tests for Customer Product Tiers, License Authority and Onboarding integration."""
import unittest

from app.customer_tiers import (
    FEATURE_AI_BANNER_STUDIO,
    FEATURE_FB_BUSINESS_ADS,
    FEATURE_FB_PROFILE_AUTOPILOT,
    FEATURE_HUMAN_SCROLLING,
    FEATURE_MULTILINGUAL_50,
    FEATURE_SUBTITLE_BURNING,
    FEATURE_VIDEO_GENERATION,
    FEATURE_YOUTUBE_OAUTH_PUBLISH,
    TIER_DEV,
    TIER_ENTERPRISE,
    TIER_FB_BUSINESS_AD,
    TIER_FB_PROFILE_AUTOPILOT,
    TIER_OMNI_VIDEO_STUDIO,
    get_tier_spec,
    is_feature_allowed,
    normalize_tier_id,
    validate_license_for_customer,
)


class TestCustomerTiers(unittest.TestCase):
    def test_normalize_tier_ids(self):
        self.assertEqual(normalize_tier_id("omni_video_studio"), TIER_OMNI_VIDEO_STUDIO)
        self.assertEqual(normalize_tier_id("video_studio"), TIER_OMNI_VIDEO_STUDIO)
        self.assertEqual(normalize_tier_id("3999"), TIER_OMNI_VIDEO_STUDIO)

        self.assertEqual(normalize_tier_id("fb_business_ad"), TIER_FB_BUSINESS_AD)
        self.assertEqual(normalize_tier_id("business_manager"), TIER_FB_BUSINESS_AD)
        self.assertEqual(normalize_tier_id("2999"), TIER_FB_BUSINESS_AD)

        self.assertEqual(normalize_tier_id("fb_profile_autopilot"), TIER_FB_PROFILE_AUTOPILOT)
        self.assertEqual(normalize_tier_id("human_poster"), TIER_FB_PROFILE_AUTOPILOT)
        self.assertEqual(normalize_tier_id("1999"), TIER_FB_PROFILE_AUTOPILOT)

        self.assertEqual(normalize_tier_id("enterprise"), TIER_ENTERPRISE)
        self.assertEqual(normalize_tier_id("dev"), TIER_DEV)

    def test_omni_video_studio_tier_spec(self):
        spec = get_tier_spec(TIER_OMNI_VIDEO_STUDIO)
        self.assertEqual(spec.price_bdt, 3999)
        self.assertEqual(spec.max_channels, 5)
        self.assertTrue(is_feature_allowed(TIER_OMNI_VIDEO_STUDIO, FEATURE_VIDEO_GENERATION))
        self.assertTrue(is_feature_allowed(TIER_OMNI_VIDEO_STUDIO, FEATURE_SUBTITLE_BURNING))
        self.assertTrue(is_feature_allowed(TIER_OMNI_VIDEO_STUDIO, FEATURE_MULTILINGUAL_50))
        self.assertTrue(is_feature_allowed(TIER_OMNI_VIDEO_STUDIO, FEATURE_YOUTUBE_OAUTH_PUBLISH))
        # Profile autopilot and FB Ads are separate products
        self.assertFalse(is_feature_allowed(TIER_OMNI_VIDEO_STUDIO, FEATURE_FB_BUSINESS_ADS))
        self.assertFalse(is_feature_allowed(TIER_OMNI_VIDEO_STUDIO, FEATURE_FB_PROFILE_AUTOPILOT))

    def test_fb_business_ad_tier_spec(self):
        spec = get_tier_spec(TIER_FB_BUSINESS_AD)
        self.assertEqual(spec.price_bdt, 2999)
        self.assertTrue(is_feature_allowed(TIER_FB_BUSINESS_AD, FEATURE_FB_BUSINESS_ADS))
        self.assertTrue(is_feature_allowed(TIER_FB_BUSINESS_AD, FEATURE_AI_BANNER_STUDIO))
        self.assertFalse(is_feature_allowed(TIER_FB_BUSINESS_AD, FEATURE_VIDEO_GENERATION))
        self.assertFalse(is_feature_allowed(TIER_FB_BUSINESS_AD, FEATURE_HUMAN_SCROLLING))

    def test_fb_profile_autopilot_tier_spec(self):
        spec = get_tier_spec(TIER_FB_PROFILE_AUTOPILOT)
        self.assertEqual(spec.price_bdt, 1999)
        self.assertTrue(is_feature_allowed(TIER_FB_PROFILE_AUTOPILOT, FEATURE_FB_PROFILE_AUTOPILOT))
        self.assertTrue(is_feature_allowed(TIER_FB_PROFILE_AUTOPILOT, FEATURE_HUMAN_SCROLLING))
        self.assertTrue(is_feature_allowed(TIER_FB_PROFILE_AUTOPILOT, FEATURE_AI_BANNER_STUDIO))
        self.assertFalse(is_feature_allowed(TIER_FB_PROFILE_AUTOPILOT, FEATURE_VIDEO_GENERATION))
        self.assertFalse(is_feature_allowed(TIER_FB_PROFILE_AUTOPILOT, FEATURE_FB_BUSINESS_ADS))

    def test_validate_license_for_customer(self):
        customer = {
            "id": 101,
            "login_id": "customer_3999",
            "plan": "omni_video_studio",
            "status": "active",
        }
        val = validate_license_for_customer(customer)
        self.assertTrue(val["valid"])
        self.assertEqual(val["tier_id"], TIER_OMNI_VIDEO_STUDIO)
        self.assertEqual(val["price_bdt"], 3999)
        self.assertIn(FEATURE_VIDEO_GENERATION, val["allowed_features"])
        self.assertTrue(val["has_lifetime_license"])

    def test_customer_onboarding_checklist_integration(self):
        from app.customer_onboarding import build_checklist

        identity = {
            "account_state": "ACTIVE",
            "entitlement_state": "ACTIVE",
            "production_access": True,
            "auth_state": "AUTHENTICATED",
            "plan": "omni_video_studio",
        }
        foundation = {
            "application": "READY",
            "media": "AVAILABLE",
            "production": "READY",
        }
        channels = [{
            "id": 1,
            "youtube_name": "Test Studio",
            "youtube_oauth_connected": 1,
            "youtube_channel_title": "My Connected Channel",
        }]

        items = build_checklist(
            identity=identity,
            foundation=foundation,
            access=None,
            channels=channels,
            api_readiness=None,
        )

        item_ids = {it["id"] for it in items}
        self.assertIn("tier.validated", item_ids)
        self.assertIn("youtube_oauth.connected", item_ids)

        tier_item = next(it for it in items if it["id"] == "tier.validated")
        self.assertEqual(tier_item["state"], "COMPLETE")
        self.assertIn("3999", tier_item["message"])

        oauth_item = next(it for it in items if it["id"] == "youtube_oauth.connected")
        self.assertEqual(oauth_item["state"], "COMPLETE")
        self.assertIn("My Connected Channel", oauth_item["message"])


if __name__ == "__main__":
    unittest.main()
