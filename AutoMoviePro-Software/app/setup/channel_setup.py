"""AutoMovie Pro — Channel, Page, Language Package & Intro/Logo Setup Engine.

Manages:
- User Profile: Name, Mobile Number, Channel Niche/Category
- Tier-based Multilingual Engine:
    * Base Package (2999 BDT): English (default) + 1 selected language (2 total)
    * Add-on (999 BDT/language): Unlocks additional individual language slots
    * Complete Package (4999 BDT): Unlocks all 6 languages (en, bn, hi, ur, ta, ml)
- Multi-Platform Channel Profiles per Unlocked Language:
    * YouTube Channel Name
    * Facebook Page Name
    * TikTok Profile Name
    * Dedicated Browser Automation Cookie Button / Official API settings
- Separate Upload Schedules (Long vs. Short Video) per Language
- Custom Brand Assets per Language: Logo watermark and Intro video
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Supported language catalog
LANGUAGE_CATALOG: Dict[str, str] = {
    "en": "English",
    "bn": "বাংলা (Bangla)",
    "hi": "हिन्दी (Hindi)",
    "ur": "اردو (Urdu)",
    "ta": "தமிழ் (Tamil)",
    "ml": "മലയാളം (Malayalam)",
}

# Standard niches / categories
SUPPORTED_NICHES: List[str] = [
    "Technology & AI Innovations",
    "Islamic History & Moral Stories",
    "Science, Mystery & Facts",
    "Business, Finance & Entrepreneurship",
    "Health, Fitness & Lifestyle",
    "Documentary & Biographies",
    "World History & Geopolitics",
    "Motivation & Self Improvement",
]

# Package tiers & definitions
PACKAGE_BASE_PRICE = 2999
PACKAGE_ADDON_PRICE = 999
PACKAGE_FULL_PRICE = 4999

PRICING_PACKAGES: Dict[str, Dict[str, Any]] = {
    "base_2999": {
        "id": "base_2999",
        "name": "Base Package",
        "name_bn": "বেস প্যাকেজ",
        "price_bdt": PACKAGE_BASE_PRICE,
        "description": "ইংরেজি + ১টি ঐচ্ছিক ভাষা (মোট ২টি ভাষা)",
        "included_languages_count": 2,
        "default_languages": ["en"],
        "allows_optional_selection": True,
    },
    "addon_999": {
        "id": "addon_999",
        "name": "Language Add-on",
        "name_bn": "ভাষা অ্যাড-অন",
        "price_bdt": PACKAGE_ADDON_PRICE,
        "description": "প্রতিটি নতুন ভাষা আনলক (৯৯৯ ৳ প্রতি ভাষা)",
        "per_language": True,
    },
    "full_4999": {
        "id": "full_4999",
        "name": "Full Multilingual Package",
        "name_bn": "ফুল প্যাকেজ",
        "price_bdt": PACKAGE_FULL_PRICE,
        "description": "সম্পূর্ণ ৬টি ভাষা একসাথে (en, bn, hi, ur, ta, ml)",
        "included_languages": ["en", "bn", "hi", "ur", "ta", "ml"],
        "included_languages_count": 6,
    },
}


def _create_platform_profile(
    *,
    youtube: Optional[Dict[str, Any]] = None,
    facebook: Optional[Dict[str, Any]] = None,
    tiktok: Optional[Dict[str, Any]] = None,
    schedule: Optional[Dict[str, Any]] = None,
    branding: Optional[Dict[str, Any]] = None,
    # Flat fields for convenience / legacy inputs:
    youtube_channel_name: str = "",
    youtube_channel_id: str = "",
    facebook_page_name: str = "",
    facebook_page_id: str = "",
    tiktok_account_name: str = "",
    tiktok_id: str = "",
    cookie_file: str = "",
    official_api_enabled: bool = False,
    official_api_key: str = "",
    short_schedule: str = "12:00",
    long_schedule: str = "19:00",
    logo_path: str = "",
    intro_video_path: str = "",
    google_pro_key: str = "",
) -> Dict[str, Any]:
    """Builds a standardized language profile dictionary containing separate objects
    for YouTube, Facebook, and TikTok, alongside synchronized flat keys for backward compatibility.
    """
    yt = dict(youtube or {})
    fb = dict(facebook or {})
    tt = dict(tiktok or {})
    sch = dict(schedule or {})
    br = dict(branding or {})

    # Extract YouTube fields
    yt_name = str(yt.get("channel_name") or youtube_channel_name or "").strip()
    yt_id = str(yt.get("channel_id") or youtube_channel_id or "").strip()
    yt_cookie = str(yt.get("cookie_file") or cookie_file or "").strip()
    yt_api_en = bool(yt.get("official_api_enabled") if "official_api_enabled" in yt else official_api_enabled)
    yt_api_k = str(yt.get("official_api_key") or official_api_key or "").strip()

    # Extract Facebook fields
    fb_name = str(fb.get("page_name") or facebook_page_name or "").strip()
    fb_id = str(fb.get("page_id") or facebook_page_id or "").strip()
    fb_cookie = str(fb.get("cookie_file") or cookie_file or "").strip()

    # Extract TikTok fields
    tt_acc = str(tt.get("account_name") or tiktok_account_name or "").strip()
    tt_id = str(tt.get("tiktok_id") or tiktok_id or tt_acc).strip()
    tt_cookie = str(tt.get("cookie_file") or cookie_file or "").strip()

    # Extract Schedules
    short_s = str(sch.get("short_schedule") or short_schedule or "12:00").strip()
    long_s = str(sch.get("long_schedule") or long_schedule or "19:00").strip()

    # Extract Branding
    logo_p = str(br.get("logo_path") or logo_path or "").strip()
    intro_p = str(br.get("intro_video_path") or intro_video_path or "").strip()

    youtube_obj = {
        "channel_name": yt_name,
        "channel_id": yt_id,
        "cookie_file": yt_cookie,
        "official_api_enabled": yt_api_en,
        "official_api_key": yt_api_k,
    }

    facebook_obj = {
        "page_name": fb_name,
        "page_id": fb_id,
        "cookie_file": fb_cookie,
    }

    tiktok_obj = {
        "tiktok_id": tt_id,
        "account_name": tt_acc,
        "cookie_file": tt_cookie,
    }

    schedule_obj = {
        "short_schedule": short_s,
        "long_schedule": long_s,
    }

    branding_obj = {
        "logo_path": logo_p,
        "intro_video_path": intro_p,
    }

    return {
        # Distinct, separate platform objects (Requirement 2):
        "youtube": youtube_obj,
        "facebook": facebook_obj,
        "tiktok": tiktok_obj,
        "schedule": schedule_obj,
        "branding": branding_obj,
        # Flat convenience mirrors (100% backward compatibility):
        "youtube_channel_name": yt_name,
        "youtube_channel_id": yt_id,
        "facebook_page_name": fb_name,
        "facebook_page_id": fb_id,
        "tiktok_account_name": tt_acc,
        "tiktok_id": tt_id,
        "cookie_file": yt_cookie or fb_cookie or tt_cookie,
        "official_api_enabled": yt_api_en,
        "official_api_key": yt_api_k,
        "short_schedule": short_s,
        "long_schedule": long_s,
        "logo_path": logo_p,
        "intro_video_path": intro_p,
        "google_pro_key": str(google_pro_key or "").strip(),
    }


class SetupManager:
    """Central manager for user profile, multilingual channels, and assets."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent / "data" / "setup"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.data_dir / "channel_setup.json"
        self.assets_dir = self.data_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self._cache = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Normalize existing profiles so separate objects are guaranteed
                    profiles = data.get("profiles_by_language") or {}
                    normalized_profiles = {}
                    for lang, prof in profiles.items():
                        normalized_profiles[lang] = _create_platform_profile(
                            youtube=prof.get("youtube"),
                            facebook=prof.get("facebook"),
                            tiktok=prof.get("tiktok"),
                            schedule=prof.get("schedule"),
                            branding=prof.get("branding"),
                            youtube_channel_name=prof.get("youtube_channel_name", ""),
                            youtube_channel_id=prof.get("youtube_channel_id", ""),
                            facebook_page_name=prof.get("facebook_page_name", ""),
                            facebook_page_id=prof.get("facebook_page_id", ""),
                            tiktok_account_name=prof.get("tiktok_account_name", ""),
                            tiktok_id=prof.get("tiktok_id", ""),
                            cookie_file=prof.get("cookie_file", ""),
                            official_api_enabled=prof.get("official_api_enabled", False),
                            official_api_key=prof.get("official_api_key", ""),
                            short_schedule=prof.get("short_schedule", "12:00"),
                            long_schedule=prof.get("long_schedule", "19:00"),
                            logo_path=prof.get("logo_path", ""),
                            intro_video_path=prof.get("intro_video_path", ""),
                        )
                    data["profiles_by_language"] = normalized_profiles
                    return data
            except Exception as e:
                logger.error("Failed to load channel setup: %s", e)
        return self._default_config()

    def _save(self) -> None:
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save channel setup: %s", e)

    def _default_config(self) -> Dict[str, Any]:
        return {
            "user_name": "",
            "mobile_number": "",
            "channel_niche": SUPPORTED_NICHES[0],
            "package_tier": "base_2999",  # 'base_2999' (2999 ৳), 'addon_999' (999 ৳), 'full_4999' (4999 ৳)
            "unlocked_languages": ["en", "bn"],  # English + 1 optional language (2 total) by default
            "profiles_by_language": {
                "en": _create_platform_profile(short_schedule="10:00", long_schedule="18:00"),
                "bn": _create_platform_profile(short_schedule="11:00", long_schedule="20:00"),
            },
        }

    def get_pricing_info(self) -> Dict[str, Any]:
        """Returns pricing tier catalog with descriptions and prices in BDT."""
        return {
            "base_package": PRICING_PACKAGES["base_2999"],
            "language_addon": PRICING_PACKAGES["addon_999"],
            "full_package": PRICING_PACKAGES["full_4999"],
            "base_price_bdt": PACKAGE_BASE_PRICE,
            "addon_price_bdt": PACKAGE_ADDON_PRICE,
            "full_price_bdt": PACKAGE_FULL_PRICE,
        }

    def get_profile(self) -> Dict[str, Any]:
        """Returns the complete setup state."""
        return dict(self._cache)

    def get_channel_profile(self) -> Dict[str, Any]:
        """Alias for get_profile()."""
        return self.get_profile()

    def update_user_profile(
        self,
        *,
        user_name: Optional[str] = None,
        mobile_number: Optional[str] = None,
        channel_niche: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates basic user details and niche."""
        if user_name is not None:
            self._cache["user_name"] = str(user_name).strip()
        if mobile_number is not None:
            self._cache["mobile_number"] = str(mobile_number).strip()
        if channel_niche is not None:
            self._cache["channel_niche"] = str(channel_niche).strip()
        self._save()
        return self.get_profile()

    def set_package_tier(self, tier: str, selected_optional_lang: str = "bn") -> Dict[str, Any]:
        """Configures unlocked languages based on purchase tier:
        - 'base_2999': 2999 ৳ - English + 1 optional selected language (total 2 languages)
        - 'full_4999': 4999 ৳ - All 6 supported languages (en, bn, hi, ur, ta, ml)
        - 'addon_999': 999 ৳ - Retains current unlocked languages for further individual additions
        """
        tier = tier.lower().strip()
        self._cache["package_tier"] = tier

        if tier in ("full_4999", "full"):
            self._cache["unlocked_languages"] = list(LANGUAGE_CATALOG.keys())
        elif tier in ("base_2999", "base"):
            opt = selected_optional_lang if selected_optional_lang in LANGUAGE_CATALOG else "bn"
            self._cache["unlocked_languages"] = ["en", opt] if opt != "en" else ["en"]

        # Ensure profiles exist for all unlocked languages
        for lang in self._cache["unlocked_languages"]:
            if lang not in self._cache["profiles_by_language"]:
                self._cache["profiles_by_language"][lang] = _create_platform_profile(
                    short_schedule="12:00",
                    long_schedule="19:00",
                )

        self._save()
        return self.get_profile()

    def unlock_additional_language(self, lang_code: str) -> Dict[str, Any]:
        """Unlocks an additional language slot (via 999 ৳ add-on)."""
        lang = lang_code.lower().strip()
        if lang not in LANGUAGE_CATALOG:
            raise ValueError(f"Language '{lang}' is not supported in catalog.")

        current = list(self._cache.get("unlocked_languages") or [])
        if lang not in current:
            current.append(lang)
            self._cache["unlocked_languages"] = current
            if lang not in self._cache["profiles_by_language"]:
                self._cache["profiles_by_language"][lang] = _create_platform_profile(
                    short_schedule="12:00",
                    long_schedule="19:00",
                )
            self._save()
        return self.get_profile()

    def update_language_profile(
        self,
        lang_code: str,
        *,
        youtube: Optional[Dict[str, Any]] = None,
        facebook: Optional[Dict[str, Any]] = None,
        tiktok: Optional[Dict[str, Any]] = None,
        schedule: Optional[Dict[str, Any]] = None,
        branding: Optional[Dict[str, Any]] = None,
        youtube_channel_name: Optional[str] = None,
        youtube_channel_id: Optional[str] = None,
        facebook_page_name: Optional[str] = None,
        facebook_page_id: Optional[str] = None,
        tiktok_account_name: Optional[str] = None,
        tiktok_id: Optional[str] = None,
        cookie_file: Optional[str] = None,
        official_api_enabled: Optional[bool] = None,
        official_api_key: Optional[str] = None,
        short_schedule: Optional[str] = None,
        long_schedule: Optional[str] = None,
        logo_path: Optional[str] = None,
        intro_video_path: Optional[str] = None,
        google_pro_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates specific platform profiles, schedules, or assets for a language.
        Saves YouTube channel, Facebook page, and TikTok profile into separate distinct objects.
        """
        lang = lang_code.lower().strip()
        if lang not in self._cache["unlocked_languages"]:
            raise PermissionError(f"Language '{lang}' is locked. Please unlock it via language pack.")

        existing = self._cache["profiles_by_language"].get(lang) or {}
        curr_yt = existing.get("youtube") if isinstance(existing.get("youtube"), dict) else {}
        curr_fb = existing.get("facebook") if isinstance(existing.get("facebook"), dict) else {}
        curr_tt = existing.get("tiktok") if isinstance(existing.get("tiktok"), dict) else {}
        curr_sch = existing.get("schedule") if isinstance(existing.get("schedule"), dict) else {}
        curr_br = existing.get("branding") if isinstance(existing.get("branding"), dict) else {}

        # Merge YouTube
        merged_yt = dict(curr_yt)
        if youtube:
            merged_yt.update(youtube)
        if youtube_channel_name is not None:
            merged_yt["channel_name"] = str(youtube_channel_name).strip()
        if youtube_channel_id is not None:
            merged_yt["channel_id"] = str(youtube_channel_id).strip()
        if cookie_file is not None:
            merged_yt["cookie_file"] = str(cookie_file).strip()
        if official_api_enabled is not None:
            merged_yt["official_api_enabled"] = bool(official_api_enabled)
        if official_api_key is not None:
            merged_yt["official_api_key"] = str(official_api_key).strip()

        # Merge Facebook
        merged_fb = dict(curr_fb)
        if facebook:
            merged_fb.update(facebook)
        if facebook_page_name is not None:
            merged_fb["page_name"] = str(facebook_page_name).strip()
        if facebook_page_id is not None:
            merged_fb["page_id"] = str(facebook_page_id).strip()
        if cookie_file is not None:
            merged_fb["cookie_file"] = str(cookie_file).strip()

        # Merge TikTok
        merged_tt = dict(curr_tt)
        if tiktok:
            merged_tt.update(tiktok)
        if tiktok_account_name is not None:
            merged_tt["account_name"] = str(tiktok_account_name).strip()
        if tiktok_id is not None:
            merged_tt["tiktok_id"] = str(tiktok_id).strip()
        elif tiktok_account_name is not None and not merged_tt.get("tiktok_id"):
            merged_tt["tiktok_id"] = str(tiktok_account_name).strip()
        if cookie_file is not None:
            merged_tt["cookie_file"] = str(cookie_file).strip()

        # Merge Schedule
        merged_sch = dict(curr_sch)
        if schedule:
            merged_sch.update(schedule)
        if short_schedule is not None:
            merged_sch["short_schedule"] = str(short_schedule).strip()
        if long_schedule is not None:
            merged_sch["long_schedule"] = str(long_schedule).strip()

        # Merge Branding
        merged_br = dict(curr_br)
        if branding:
            merged_br.update(branding)
        if logo_path is not None:
            merged_br["logo_path"] = str(logo_path).strip()
        if intro_video_path is not None:
            merged_br["intro_video_path"] = str(intro_video_path).strip()

        # Merge Google Pro Key
        merged_google_pro_key = (
            str(google_pro_key).strip()
            if google_pro_key is not None
            else str(existing.get("google_pro_key") or "").strip()
        )

        # Build clean profile with separate objects and synced convenience fields
        updated_profile = _create_platform_profile(
            youtube=merged_yt,
            facebook=merged_fb,
            tiktok=merged_tt,
            schedule=merged_sch,
            branding=merged_br,
            google_pro_key=merged_google_pro_key,
        )

        self._cache["profiles_by_language"][lang] = updated_profile
        self._save()
        return self.get_profile()

    def set_google_pro_key(self, lang_code: str, key: str) -> Dict[str, Any]:
        """Sets Google Pro API Key for a specific language profile."""
        return self.update_language_profile(lang_code, google_pro_key=key)

    def get_google_pro_key(self, lang_code: str) -> str:
        """Retrieves Google Pro API Key configured for a language."""
        lang = lang_code.lower().strip()
        prof = self._cache.get("profiles_by_language", {}).get(lang) or {}
        return str(prof.get("google_pro_key") or "").strip()

    def get_active_channels_count(self) -> int:
        """Returns the total number of distinct active channels configured."""
        unlocked = self._cache.get("unlocked_languages") or []
        count = 0
        for lang in unlocked:
            prof = self._cache.get("profiles_by_language", {}).get(lang, {})
            yt = prof.get("youtube") if isinstance(prof.get("youtube"), dict) else {}
            fb = prof.get("facebook") if isinstance(prof.get("facebook"), dict) else {}
            tt = prof.get("tiktok") if isinstance(prof.get("tiktok"), dict) else {}

            has_yt = bool(yt.get("channel_name") or prof.get("youtube_channel_name"))
            has_fb = bool(fb.get("page_name") or prof.get("facebook_page_name"))
            has_tt = bool(tt.get("account_name") or tt.get("tiktok_id") or prof.get("tiktok_account_name"))

            if has_yt or has_fb or has_tt:
                count += 1
        return count


ChannelSetupManager = SetupManager
channel_manager = SetupManager()

