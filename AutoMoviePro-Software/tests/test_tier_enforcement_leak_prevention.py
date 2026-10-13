"""
AutoMovie Pro - 3-Tier License Enforcement & Leak Prevention Test Suite
=====================================================================
Rigorous tests verifying complete isolation and gating across:
  * ৳1,999 -> profile_page (FB Profile & Page Autopilot)
  * ৳2,999 -> fb_business (FB Business Manager & Ad Content)
  * ৳3,999 -> video_studio (Full Omni Social Video Content Automation)

Ensures 100% leak prevention:
  - profile_page cannot generate videos or create ad campaigns (HTTP 403).
  - fb_business cannot generate short/long videos in Video Studio (HTTP 403).
  - video_studio has complete unhindered production access.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.customer_tiers import (
    TIER_VIDEO_STUDIO,
    TIER_FB_BUSINESS,
    TIER_PROFILE_PAGE,
    TIER_DEV,
    TIER_ENTERPRISE,
    can_produce_video_studio,
    can_access_fb_business,
    can_access_profile_page,
    normalize_tier_id,
    extract_tier,
    TIER_UPGRADE_MESSAGE_VIDEO_STUDIO,
    TIER_UPGRADE_MESSAGE_FB_BUSINESS,
)
from app.main import app


class TestCustomerTiersPermissions(unittest.TestCase):
    """Direct validation of tier resolution, normalization and permission helpers."""

    def test_tier_normalization(self):
        # ৳3,999 Video Studio variants
        self.assertEqual(normalize_tier_id("video_studio"), TIER_VIDEO_STUDIO)
        self.assertEqual(normalize_tier_id("omni_video_studio"), TIER_VIDEO_STUDIO)
        self.assertEqual(normalize_tier_id("3999"), TIER_VIDEO_STUDIO)
        self.assertEqual(normalize_tier_id("omni_social"), TIER_VIDEO_STUDIO)

        # ৳2,999 FB Business variants
        self.assertEqual(normalize_tier_id("fb_business"), TIER_FB_BUSINESS)
        self.assertEqual(normalize_tier_id("fb_business_ad"), TIER_FB_BUSINESS)
        self.assertEqual(normalize_tier_id("business_manager"), TIER_FB_BUSINESS)
        self.assertEqual(normalize_tier_id("2999"), TIER_FB_BUSINESS)

        # ৳1,999 FB Profile variants
        self.assertEqual(normalize_tier_id("profile_page"), TIER_PROFILE_PAGE)
        self.assertEqual(normalize_tier_id("fb_profile_autopilot"), TIER_PROFILE_PAGE)
        self.assertEqual(normalize_tier_id("1999"), TIER_PROFILE_PAGE)
        self.assertEqual(normalize_tier_id("autopilot"), TIER_PROFILE_PAGE)

        # Fail-closed leak prevention: unknown plans fallback to profile_page (never video_studio)
        self.assertEqual(normalize_tier_id("attacker_unauthorized_plan"), TIER_PROFILE_PAGE)
        self.assertEqual(normalize_tier_id("unknown_tier"), TIER_PROFILE_PAGE)

    def test_extract_tier(self):
        self.assertEqual(extract_tier("video_studio"), TIER_VIDEO_STUDIO)
        self.assertEqual(extract_tier({"tier": "video_studio"}), TIER_VIDEO_STUDIO)
        self.assertEqual(extract_tier({"plan": "fb_business"}), TIER_FB_BUSINESS)
        self.assertEqual(extract_tier({"plan_name": "profile_page"}), TIER_PROFILE_PAGE)
        self.assertEqual(extract_tier({"plan_label": "3999"}), TIER_VIDEO_STUDIO)

    def test_can_produce_video_studio(self):
        # ONLY video_studio, dev, and enterprise are allowed
        self.assertTrue(can_produce_video_studio(TIER_VIDEO_STUDIO))
        self.assertTrue(can_produce_video_studio(TIER_DEV))
        self.assertTrue(can_produce_video_studio(TIER_ENTERPRISE))
        self.assertTrue(can_produce_video_studio({"tier": "video_studio"}))

        # ৳1,999 and ৳2,999 MUST BE STRICTLY BLOCKED
        self.assertFalse(can_produce_video_studio(TIER_FB_BUSINESS))
        self.assertFalse(can_produce_video_studio("fb_business"))
        self.assertFalse(can_produce_video_studio("2999"))
        self.assertFalse(can_produce_video_studio({"tier": "fb_business"}))

        self.assertFalse(can_produce_video_studio(TIER_PROFILE_PAGE))
        self.assertFalse(can_produce_video_studio("profile_page"))
        self.assertFalse(can_produce_video_studio("1999"))
        self.assertFalse(can_produce_video_studio({"tier": "profile_page"}))

        # Unrecognized input MUST NOT grant access
        self.assertFalse(can_produce_video_studio("unauthorized"))

    def test_can_access_fb_business(self):
        # fb_business, video_studio, dev, enterprise allowed
        self.assertTrue(can_access_fb_business(TIER_FB_BUSINESS))
        self.assertTrue(can_access_fb_business(TIER_VIDEO_STUDIO))
        self.assertTrue(can_access_fb_business(TIER_DEV))
        self.assertTrue(can_access_fb_business({"tier": "fb_business"}))

        # profile_page (৳1,999) MUST BE BLOCKED
        self.assertFalse(can_access_fb_business(TIER_PROFILE_PAGE))
        self.assertFalse(can_access_fb_business("profile_page"))
        self.assertFalse(can_access_fb_business("1999"))
        self.assertFalse(can_access_fb_business({"tier": "profile_page"}))

    def test_can_access_profile_page(self):
        # All tiers have access to profile & page quotes and posting
        self.assertTrue(can_access_profile_page(TIER_PROFILE_PAGE))
        self.assertTrue(can_access_profile_page(TIER_FB_BUSINESS))
        self.assertTrue(can_access_profile_page(TIER_VIDEO_STUDIO))
        self.assertTrue(can_access_profile_page(TIER_DEV))


class TestCustomerAuthTierEnforcement(unittest.TestCase):
    """Validation of customer_auth authority gating."""

    def test_can_customer_produce_blocks_lower_tiers(self):
        from app.customer_auth import can_customer_produce

        # 1. Test profile_page identity
        profile_identity = {
            "auth_state": "AUTHENTICATED",
            "account_state": "ACTIVE",
            "entitlement_state": "ACTIVE",
            "production_access": True,
            "logged_in": True,
            "tier": "profile_page",
            "plan": "profile_page",
        }
        with patch("app.customer_auth.evaluate_session", return_value=profile_identity):
            res = can_customer_produce()
            self.assertFalse(res["allowed"])
            self.assertEqual(res["block_reason"], "tier_upgrade_required")
            self.assertEqual(res["message"], TIER_UPGRADE_MESSAGE_VIDEO_STUDIO)

        # 2. Test fb_business identity
        biz_identity = {
            "auth_state": "AUTHENTICATED",
            "account_state": "ACTIVE",
            "entitlement_state": "ACTIVE",
            "production_access": True,
            "logged_in": True,
            "tier": "fb_business",
            "plan": "fb_business",
        }
        with patch("app.customer_auth.evaluate_session", return_value=biz_identity):
            res = can_customer_produce()
            self.assertFalse(res["allowed"])
            self.assertEqual(res["block_reason"], "tier_upgrade_required")
            self.assertEqual(res["message"], TIER_UPGRADE_MESSAGE_VIDEO_STUDIO)


class TestHttpTierEnforcement(unittest.TestCase):
    """End-to-end API gating tests on FastAPI endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def _make_mock_session(self, tier: str) -> dict:
        return {
            "id": 1,
            "login_id": f"user_{tier}",
            "token": "test-valid-session-token",
            "api_base_url": "https://automoviepro.com",
            "auth_mode": "license",
            "plan": tier,
            "tier": tier,
            "customer": {
                "id": 42,
                "name": f"Test User {tier}",
                "login_id": f"user_{tier}",
                "status": "active",
                "tier": tier,
                "plan": tier,
            },
        }

    def test_profile_page_tier_strictly_blocked_from_video_studio(self):
        mock_sess = self._make_mock_session("profile_page")
        with patch("app.main._require_session", return_value=mock_sess):
            # 1. /api/generate/short
            r1 = self.client.post("/api/generate/short", json={"channel_id": 1})
            self.assertEqual(r1.status_code, 403)
            self.assertFalse(r1.json()["ok"])
            self.assertEqual(r1.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r1.json()["message"])

            # 2. /api/generate/long
            r2 = self.client.post("/api/generate/long", json={"channel_id": 1})
            self.assertEqual(r2.status_code, 403)
            self.assertFalse(r2.json()["ok"])
            self.assertEqual(r2.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r2.json()["message"])

            # 3. /api/job/start
            r3 = self.client.post("/api/job/start", json={"channel_id": 1})
            self.assertEqual(r3.status_code, 403)
            self.assertFalse(r3.json()["ok"])
            self.assertEqual(r3.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r3.json()["message"])

            # 4. /api/jobs/create
            r4 = self.client.post("/api/jobs/create", json={"channel_id": 1})
            self.assertEqual(r4.status_code, 403)
            self.assertFalse(r4.json()["ok"])
            self.assertEqual(r4.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r4.json()["message"])

            # 5. /api/generate
            r5 = self.client.post("/api/generate", json={"channel_id": 1, "video_type": "short"})
            self.assertEqual(r5.status_code, 403)
            self.assertFalse(r5.json()["ok"])
            self.assertEqual(r5.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r5.json()["message"])

            # 6. /api/workspace/generate
            r6 = self.client.post("/api/workspace/generate", json={"channel_id": 1})
            self.assertEqual(r6.status_code, 403)
            self.assertFalse(r6.json()["ok"])
            self.assertEqual(r6.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r6.json()["message"])

            # 7. FB Business Ad Generation (blocked for profile_page tier)
            r7 = self.client.post("/api/products/prod_1/generate-ad", json={})
            self.assertEqual(r7.status_code, 403)
            self.assertFalse(r7.json()["ok"])
            self.assertIn("বিজনেস ম্যানেজার", r7.json()["message"])

    def test_fb_business_tier_strictly_blocked_from_video_studio(self):
        mock_sess = self._make_mock_session("fb_business")
        with patch("app.main._require_session", return_value=mock_sess):
            # 1. /api/generate/short (Must be 403)
            r1 = self.client.post("/api/generate/short", json={"channel_id": 1})
            self.assertEqual(r1.status_code, 403)
            self.assertFalse(r1.json()["ok"])
            self.assertEqual(r1.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r1.json()["message"])

            # 2. /api/generate/long (Must be 403)
            r2 = self.client.post("/api/generate/long", json={"channel_id": 1})
            self.assertEqual(r2.status_code, 403)
            self.assertFalse(r2.json()["ok"])
            self.assertEqual(r2.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r2.json()["message"])

            # 3. /api/job/start (Must be 403)
            r3 = self.client.post("/api/job/start", json={"channel_id": 1})
            self.assertEqual(r3.status_code, 403)
            self.assertFalse(r3.json()["ok"])
            self.assertEqual(r3.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r3.json()["message"])

            # 4. /api/jobs/create (Must be 403)
            r4 = self.client.post("/api/jobs/create", json={"channel_id": 1})
            self.assertEqual(r4.status_code, 403)
            self.assertFalse(r4.json()["ok"])
            self.assertEqual(r4.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r4.json()["message"])

            # 5. /api/generate (Must be 403)
            r5 = self.client.post("/api/generate", json={"channel_id": 1, "video_type": "short"})
            self.assertEqual(r5.status_code, 403)
            self.assertFalse(r5.json()["ok"])
            self.assertEqual(r5.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r5.json()["message"])

            # 6. /api/workspace/generate (Must be 403)
            r6 = self.client.post("/api/workspace/generate", json={"channel_id": 1})
            self.assertEqual(r6.status_code, 403)
            self.assertFalse(r6.json()["ok"])
            self.assertEqual(r6.json()["error"], "tier_upgrade_required")
            self.assertIn("ভিডিও স্টুডিও অন্তর্ভুক্ত নয়", r6.json()["message"])

            # 7. FB Business Ad Generation is PERMITTED for fb_business
            with patch("app.product_service.ProductService.create_ad_campaign", return_value={"campaign_id": "c1"}):
                r7 = self.client.post("/api/products/prod_1/generate-ad", json={})
                self.assertNotEqual(r7.status_code, 403)
                self.assertTrue(r7.json()["ok"])

    def test_video_studio_tier_has_full_production_access(self):
        mock_sess = self._make_mock_session("video_studio")
        with patch("app.main._require_session", return_value=mock_sess):
            # When video_studio attempts video generation, tier check passes (NO 403)!
            # We mock the subsequent pipeline generation call to return success
            mock_generate_resp = {"ok": True, "job_id": 999, "status": "QUEUED"}
            with patch("app.main.generate", return_value=mock_generate_resp):
                r1 = self.client.post("/api/generate/short", json={"channel_id": 1})
                self.assertNotEqual(r1.status_code, 403)
                self.assertTrue(r1.json()["ok"])

                r2 = self.client.post("/api/generate/long", json={"channel_id": 1})
                self.assertNotEqual(r2.status_code, 403)
                self.assertTrue(r2.json()["ok"])

                r3 = self.client.post("/api/job/start", json={"channel_id": 1})
                self.assertNotEqual(r3.status_code, 403)
                self.assertTrue(r3.json()["ok"])

                r4 = self.client.post("/api/jobs/create", json={"channel_id": 1})
                self.assertNotEqual(r4.status_code, 403)
                self.assertTrue(r4.json()["ok"])


if __name__ == "__main__":
    unittest.main()
