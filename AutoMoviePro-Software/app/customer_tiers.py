"""
AutoMovie Pro - Customer Product Tiers & License Authority
=========================================================
Formal definitions and access gating for the 3 official commercial products:

1. video_studio (৳৩,৯৯৯)
   - Omni Social Media Content Automation (Video Studio)
   - Full Video Studio, 50+ Global Languages, HarfBuzz Subtitles, TTS, BGM
   - YouTube Data API v3 1-Click Publishing, Facebook Video Reels
   - Render Studio, Social Publisher, Ads, Products

2. fb_business (৳২,৯৯৯)
   - Omni FB Business Manager & Ad Content Automation
   - Meta Business Suite Automation, Ad Campaign Generator, Targeted Ads
   - Promotional Graphic Banners, Product Ads, Group Sharer, Comment Agent
   - CANNOT generate full video studio long/short videos without upgrade

3. profile_page (৳১,৯৯৯)
   - Omni FB Profile & Page Post Automation
   - Profile & Page Quotes, Lifestyle/Religious Banners, Timeline Autopilot
   - Human-like Feed Scrolling, Organic Posts
   - CANNOT generate video studio videos or run full business ad campaigns
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# Canonical Product Tier Identifiers (৳3,999 / ৳2,999 / ৳1,999)
TIER_VIDEO_STUDIO = "video_studio"
TIER_FB_BUSINESS = "fb_business"
TIER_PROFILE_PAGE = "profile_page"
TIER_DEV = "dev"
TIER_ENTERPRISE = "enterprise"

# Aliases for backwards compatibility
TIER_OMNI_VIDEO_STUDIO = TIER_VIDEO_STUDIO
TIER_FB_BUSINESS_AD = TIER_FB_BUSINESS
TIER_FB_PROFILE_AUTOPILOT = TIER_PROFILE_PAGE

# Feature Capabilities
FEATURE_VIDEO_GENERATION = "video_generation"
FEATURE_SUBTITLE_BURNING = "subtitle_burning"
FEATURE_MULTILINGUAL_50 = "multilingual_50"
FEATURE_YOUTUBE_OAUTH_PUBLISH = "youtube_oauth_publish"
FEATURE_FACEBOOK_REELS_PUBLISH = "facebook_reels_publish"
FEATURE_FB_BUSINESS_ADS = "fb_business_ads"
FEATURE_FB_PROFILE_AUTOPILOT = "fb_profile_autopilot"
FEATURE_HUMAN_SCROLLING = "human_scrolling"
FEATURE_AI_BANNER_STUDIO = "ai_banner_studio"
FEATURE_RENDER_STUDIO = "render_studio"
FEATURE_SOCIAL_PUBLISHER = "social_publisher"
FEATURE_ADS = "ads"
FEATURE_PRODUCTS = "products"
FEATURE_COMMENT_AGENT = "comment_agent"
FEATURE_GROUP_SHARER = "group_sharer"

# Authoritative Bengali Upgrade Messages
TIER_UPGRADE_MESSAGE_VIDEO_STUDIO = (
    "আপনার বর্তমান প্ল্যানে ফুল ভিডিও স্টুডিও অন্তর্ভুক্ত নয়। "
    "ভিডিও তৈরি করতে ৳৩,৯৯৯ ভিডিও স্টুডিও প্যাকেজে আপগ্রেড করুন।"
)
TIER_UPGRADE_MESSAGE_FB_BUSINESS = (
    "আপনার বর্তমান প্ল্যানে ফেসবুক বিজনেস ম্যানেজার ও অ্যাড ক্যাম্পেইন অন্তর্ভুক্ত নয়। "
    "অ্যাড ক্যাম্পেইন চালাতে ৳২,৯৯৯ ফেসবুক বিজনেস ম্যানেজার প্যাকেজে আপগ্রেড করুন।"
)


@dataclass(frozen=True)
class TierSpecification:
    tier_id: str
    display_name_en: str
    display_name_bn: str
    price_bdt: int
    regular_price_bdt: int
    allowed_features: Set[str]
    max_channels: int = 1
    max_daily_jobs: int = 10
    has_lifetime_license: bool = True
    support_level: str = "standard"


SPEC_VIDEO_STUDIO = TierSpecification(
    tier_id=TIER_VIDEO_STUDIO,
    display_name_en="Omni Social Media Content Automation (Video Studio)",
    display_name_bn="অমনি সোশ্যাল মিডিয়া কনটেন্ট অটোমেশন (ভিডিও স্টুডিও)",
    price_bdt=3999,
    regular_price_bdt=10000,
    allowed_features={
        FEATURE_VIDEO_GENERATION,
        FEATURE_SUBTITLE_BURNING,
        FEATURE_MULTILINGUAL_50,
        FEATURE_YOUTUBE_OAUTH_PUBLISH,
        FEATURE_FACEBOOK_REELS_PUBLISH,
        FEATURE_AI_BANNER_STUDIO,
        FEATURE_RENDER_STUDIO,
        FEATURE_SOCIAL_PUBLISHER,
        FEATURE_ADS,
        FEATURE_PRODUCTS,
    },
    max_channels=5,
    max_daily_jobs=50,
)

SPEC_FB_BUSINESS = TierSpecification(
    tier_id=TIER_FB_BUSINESS,
    display_name_en="Omni FB Business Manager & Ad Content Automation",
    display_name_bn="ফেসবুক বিজনেস ম্যানেজার ও অ্যাড পাওয়ারহাউজ",
    price_bdt=2999,
    regular_price_bdt=8500,
    allowed_features={
        FEATURE_FB_BUSINESS_ADS,
        FEATURE_FACEBOOK_REELS_PUBLISH,
        FEATURE_AI_BANNER_STUDIO,
        FEATURE_COMMENT_AGENT,
        FEATURE_GROUP_SHARER,
        FEATURE_ADS,
        FEATURE_PRODUCTS,
    },
    max_channels=3,
    max_daily_jobs=30,
)

SPEC_PROFILE_PAGE = TierSpecification(
    tier_id=TIER_PROFILE_PAGE,
    display_name_en="Omni FB Profile & Page Post Automation",
    display_name_bn="ফেসবুক প্রোফাইল ও পেজ অটো পাইলট",
    price_bdt=1999,
    regular_price_bdt=6500,
    allowed_features={
        FEATURE_FB_PROFILE_AUTOPILOT,
        FEATURE_HUMAN_SCROLLING,
        FEATURE_AI_BANNER_STUDIO,
    },
    max_channels=2,
    max_daily_jobs=20,
)

SPEC_DEV = TierSpecification(
    tier_id=TIER_DEV,
    display_name_en="Local Developer / Full Suite",
    display_name_bn="লোকাল ডেভেলপার / ফুল স্যুট",
    price_bdt=0,
    regular_price_bdt=0,
    allowed_features={
        FEATURE_VIDEO_GENERATION,
        FEATURE_SUBTITLE_BURNING,
        FEATURE_MULTILINGUAL_50,
        FEATURE_YOUTUBE_OAUTH_PUBLISH,
        FEATURE_FACEBOOK_REELS_PUBLISH,
        FEATURE_FB_BUSINESS_ADS,
        FEATURE_FB_PROFILE_AUTOPILOT,
        FEATURE_HUMAN_SCROLLING,
        FEATURE_AI_BANNER_STUDIO,
        FEATURE_RENDER_STUDIO,
        FEATURE_SOCIAL_PUBLISHER,
        FEATURE_ADS,
        FEATURE_PRODUCTS,
        FEATURE_COMMENT_AGENT,
        FEATURE_GROUP_SHARER,
    },
    max_channels=99,
    max_daily_jobs=999,
    support_level="unlimited",
)

SPEC_ENTERPRISE = TierSpecification(
    tier_id=TIER_ENTERPRISE,
    display_name_en="Enterprise All-In-One Lifetime Suite",
    display_name_bn="এন্টারপ্রাইজ অল-ইন-ওয়ান লাইফটাইম স্যুট",
    price_bdt=8999,
    regular_price_bdt=25000,
    allowed_features={
        FEATURE_VIDEO_GENERATION,
        FEATURE_SUBTITLE_BURNING,
        FEATURE_MULTILINGUAL_50,
        FEATURE_YOUTUBE_OAUTH_PUBLISH,
        FEATURE_FACEBOOK_REELS_PUBLISH,
        FEATURE_FB_BUSINESS_ADS,
        FEATURE_FB_PROFILE_AUTOPILOT,
        FEATURE_HUMAN_SCROLLING,
        FEATURE_AI_BANNER_STUDIO,
        FEATURE_RENDER_STUDIO,
        FEATURE_SOCIAL_PUBLISHER,
        FEATURE_ADS,
        FEATURE_PRODUCTS,
        FEATURE_COMMENT_AGENT,
        FEATURE_GROUP_SHARER,
    },
    max_channels=20,
    max_daily_jobs=200,
    support_level="priority_vip",
)

OFFICIAL_TIERS: Dict[str, TierSpecification] = {
    TIER_VIDEO_STUDIO: SPEC_VIDEO_STUDIO,
    "omni_video_studio": SPEC_VIDEO_STUDIO,
    TIER_FB_BUSINESS: SPEC_FB_BUSINESS,
    "fb_business_ad": SPEC_FB_BUSINESS,
    TIER_PROFILE_PAGE: SPEC_PROFILE_PAGE,
    "fb_profile_autopilot": SPEC_PROFILE_PAGE,
    TIER_DEV: SPEC_DEV,
    TIER_ENTERPRISE: SPEC_ENTERPRISE,
}


def normalize_tier_id(raw_tier: Optional[str]) -> str:
    """Map user/customer plan string to official tier id."""
    if not raw_tier:
        return TIER_DEV  # default offline fallback
    low = str(raw_tier).strip().lower()
    # ৳3,999 - Video Studio
    if low in ("video_studio", "omni_video_studio", "video_automation", "studio", "3999", "omni_social"):
        return TIER_VIDEO_STUDIO
    # ৳2,999 - FB Business Manager & Ad
    if low in ("fb_business", "fb_business_ad", "business_ad", "business_manager", "ad_manager", "2999", "business"):
        return TIER_FB_BUSINESS
    # ৳1,999 - FB Profile & Page Autopilot
    if low in ("profile_page", "fb_profile_autopilot", "profile_autopilot", "autopilot", "human_poster", "1999", "profile", "page"):
        return TIER_PROFILE_PAGE
    # Enterprise & Dev
    if low in ("enterprise", "all_in_one", "all", "bundle"):
        return TIER_ENTERPRISE
    if low in ("dev", "local", "developer", "test", "admin", "local_dev"):
        return TIER_DEV
    # Fallback: strictly profile_page to prevent unauthorized leakage to video studio
    return TIER_PROFILE_PAGE


def extract_tier(customer_plan: Optional[Any] = None) -> str:
    """Extract and normalize tier identifier from string, dict, or current session."""
    if customer_plan is None:
        try:
            from app import db as store

            sess = store.get_session()
            if sess:
                c = sess.get("customer") or {}
                raw = c.get("tier") or c.get("plan") or sess.get("plan")
                if raw:
                    return normalize_tier_id(str(raw))
                if str(sess.get("auth_mode") or "") == "local_dev" or str(sess.get("token") or "").startswith("local-"):
                    return TIER_DEV
        except Exception:
            pass
        return TIER_DEV
    if isinstance(customer_plan, dict):
        raw = (
            customer_plan.get("tier")
            or customer_plan.get("plan")
            or customer_plan.get("plan_name")
            or customer_plan.get("plan_label")
        )
        if not raw and customer_plan.get("mode") == "local_dev":
            return TIER_DEV
        return normalize_tier_id(str(raw) if raw else None)
    return normalize_tier_id(str(customer_plan))


def can_produce_video_studio(customer_plan: Optional[Any] = None) -> bool:
    """Only True for video_studio, dev, or enterprise.

    ৳1,999 (profile_page) and ৳2,999 (fb_business) are strictly blocked from video production.
    """
    tier = extract_tier(customer_plan)
    return tier in (TIER_VIDEO_STUDIO, TIER_DEV, TIER_ENTERPRISE)


def can_access_fb_business(customer_plan: Optional[Any] = None) -> bool:
    """True for fb_business and video_studio (and dev/enterprise).

    ৳1,999 (profile_page) is blocked from FB business manager and ads.
    """
    tier = extract_tier(customer_plan)
    return tier in (TIER_FB_BUSINESS, TIER_VIDEO_STUDIO, TIER_DEV, TIER_ENTERPRISE)


def can_access_profile_page(customer_plan: Optional[Any] = None) -> bool:
    """True for all commercial tiers (profile_page, fb_business, video_studio)."""
    tier = extract_tier(customer_plan)
    return tier in (TIER_PROFILE_PAGE, TIER_FB_BUSINESS, TIER_VIDEO_STUDIO, TIER_DEV, TIER_ENTERPRISE)


def get_tier_spec(tier_id: Optional[str]) -> TierSpecification:
    norm = normalize_tier_id(tier_id)
    return OFFICIAL_TIERS.get(norm, OFFICIAL_TIERS[TIER_DEV])


def is_feature_allowed(tier_id: Optional[str], feature: str) -> bool:
    spec = get_tier_spec(tier_id)
    return feature in spec.allowed_features


def validate_license_for_customer(customer: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate customer license and resolve official product tier details."""
    c = customer or {}
    raw_plan = c.get("tier") or c.get("plan") or c.get("plan_name") or "dev"
    tier_id = normalize_tier_id(raw_plan)
    spec = get_tier_spec(tier_id)

    is_valid = bool(tier_id in OFFICIAL_TIERS)
    return {
        "valid": is_valid,
        "tier_id": spec.tier_id,
        "display_name_en": spec.display_name_en,
        "display_name_bn": spec.display_name_bn,
        "price_bdt": spec.price_bdt,
        "max_channels": spec.max_channels,
        "allowed_features": sorted(list(spec.allowed_features)),
        "has_lifetime_license": spec.has_lifetime_license,
    }
