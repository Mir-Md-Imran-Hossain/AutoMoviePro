"""
=============================================================================
OmniSocial AI Hub - Universal Social Platform Architecture & Metadata Engine
=============================================================================
Manages profile directories, isolated credentials/cookies, content strategies,
historical archives, comments/inbox interaction history, and live state.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

ROOT_DIR = Path(r"E:\AI Assistant\Social Media Hub")
PROFILES_DIR = ROOT_DIR / "Profiles"
LOGS_DIR = ROOT_DIR / "System_Logs"
STATE_FILE = ROOT_DIR / "master_schedule_state.json"

for d in [ROOT_DIR, PROFILES_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def atomic_write_json(filepath: Path, data: Any):
    """Safely writes JSON using a temporary file and atomic replace with Windows retry logic."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(f"{filepath.suffix}.tmp_{os.getpid()}_{time.time_ns()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        
        # Windows-safe atomic replace with retry
        replaced = False
        for attempt in range(6):
            try:
                os.replace(tmp_path, filepath)
                replaced = True
                break
            except (PermissionError, OSError):
                time.sleep(0.08)
        if not replaced:
            # Fallback if file still locked
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise e


class SocialEntity:
    """Represents a registered social channel, profile, or page."""

    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self.folder = PROFILES_DIR / entity_id
        self.config_path = self.folder / "config.json"
        self.history_path = self.folder / "history.json"
        self.comments_path = self.folder / "comments_inbox.json"
        self.assets_dir = self.folder / "assets"
        self.generated_dir = self.folder / "generated_posts"
        self._ensure_structure()

    def _ensure_structure(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(exist_ok=True)
        self.generated_dir.mkdir(exist_ok=True)

        if not self.config_path.exists():
            default_config = {
                "entity_id": self.entity_id,
                "display_name": self.entity_id.replace("_", " ").title(),
                "platform": "facebook_page", # facebook_page, facebook_profile, instagram, x_twitter
                "account_id": "",
                "username": "",
                "url": "",
                "browser_profile_dir": r"E:\AI Assistant\Automation Workspace\Social_Media_Profiles\Facebook_AssunnahPath",
                "content_strategy": {
                    "niche": "General",
                    "language": "bn",
                    "strict_authenticity": False,
                    "topics": [],
                    "posts_per_day": 3,
                    "interval_hours_min": 7.0,
                    "interval_hours_max": 8.5,
                    "guidelines": ""
                },
                "auto_reply": {
                    "enabled": True,
                    "tone": "Warm, professional, respectful",
                    "page_context": ""
                },
                "status": "active",
                "created_at": datetime.now().isoformat()
            }
            self.save_config(default_config)

        if not self.history_path.exists():
            self.history_path.write_text("[]", encoding="utf-8")

        if not self.comments_path.exists():
            self.comments_path.write_text("[]", encoding="utf-8")

    def get_config(self) -> Dict[str, Any]:
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_config(self, config: Dict[str, Any]):
        atomic_write_json(self.config_path, config)

    def get_history(self) -> List[Dict[str, Any]]:
        with open(self.history_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def append_post_history(self, post_record: Dict[str, Any]):
        hist = self.get_history()
        hist.append({
            "timestamp": datetime.now().isoformat(),
            **post_record
        })
        atomic_write_json(self.history_path, hist)

    def get_comments_inbox(self) -> List[Dict[str, Any]]:
        with open(self.comments_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def append_comment_reply(self, reply_record: Dict[str, Any]):
        inbox = self.get_comments_inbox()
        inbox.append({
            "timestamp": datetime.now().isoformat(),
            **reply_record
        })
        atomic_write_json(self.comments_path, inbox)


class OmniSocialRegistry:
    """Registry managing all active profiles, pages, and scheduler states."""

    @staticmethod
    def list_entities() -> List[SocialEntity]:
        entities = []
        if PROFILES_DIR.exists():
            for p in PROFILES_DIR.iterdir():
                if p.is_dir() and (p / "config.json").exists():
                    entities.append(SocialEntity(p.name))
        return entities

    @staticmethod
    def get_entity(entity_id: str) -> SocialEntity:
        return SocialEntity(entity_id)

    @staticmethod
    def register_entity(
        entity_id: str,
        display_name: str,
        platform: str,
        account_id: str,
        url: str,
        niche: str,
        language: str,
        posts_per_day: int,
        guidelines: str,
        strict_authenticity: bool = False,
        browser_profile_dir: str = ""
    ) -> SocialEntity:
        entity = SocialEntity(entity_id)
        cfg = entity.get_config()
        cfg.update({
            "entity_id": entity_id,
            "display_name": display_name,
            "platform": platform,
            "account_id": account_id,
            "url": url,
            "browser_profile_dir": browser_profile_dir or r"E:\AI Assistant\Automation Workspace\Social_Media_Profiles\Facebook_AssunnahPath",
            "content_strategy": {
                "niche": niche,
                "language": language,
                "strict_authenticity": strict_authenticity,
                "posts_per_day": posts_per_day,
                "interval_hours_min": round(24.0 / (posts_per_day + 0.5), 1),
                "interval_hours_max": round(24.0 / (posts_per_day - 0.2), 1),
                "guidelines": guidelines
            }
        })
        entity.save_config(cfg)
        return entity

    @staticmethod
    def get_master_state() -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_system_boot": datetime.now().isoformat(),
            "active_tasks": {},
            "status": "idle",
            "current_action": "System Initialized",
            "next_scheduled_event": {}
        }

    @staticmethod
    def update_master_state(patch: Dict[str, Any]):
        state = OmniSocialRegistry.get_master_state()
        state.update(patch)
        atomic_write_json(STATE_FILE, state)


# Initialize default profiles for AutoMovie Pro and As-Sunnah Path
def seed_default_profiles():
    # 1. AutoMovie Pro Official Page
    OmniSocialRegistry.register_entity(
        entity_id="automovie_pro_page",
        display_name="AutoMovie Pro Official Page",
        platform="facebook_page",
        account_id="AutoMoviePro",
        url="https://www.facebook.com/me/",
        niche="Industrial Video Automation SaaS, Passive Income, YouTube Faceless",
        language="bn",
        posts_per_day=24, # Every 45-65 mins
        guidelines="Full marketing banners, Omni Video Automation ৳3999, FB Business Manager ৳2999, FB Profile Auto Pilot ৳1999, Addon ৳499, hotline +880 1684-355055, official payment agents (01756160993, 01611-824811, 01717820998). Human pre/post scroll 3-7 mins."
    )

    # 2. As-Sunnah Path Profile
    OmniSocialRegistry.register_entity(
        entity_id="assunnah_path_profile",
        display_name="As-Sunnah Path (Personal Profile)",
        platform="facebook_profile",
        account_id="61595114556629",
        url="https://www.facebook.com/profile.php?id=61595114556629",
        niche="Authentic Quran & Hadith, Islamic Wisdom, Spiritual Serenity",
        language="en",
        posts_per_day=3,
        strict_authenticity=True,
        guidelines="Verified Quran Ayahs & Sahih Hadiths in English translations only. Authentic gold emblem banners. Strictly English content."
    )

    # 3. As-Sunnah Path Facebook Page
    OmniSocialRegistry.register_entity(
        entity_id="assunnah_path_page",
        display_name="As-Sunnah Path (Official Facebook Page)",
        platform="facebook_page",
        account_id="61594165271828",
        url="https://www.facebook.com/profile.php?id=61594165271828",
        niche="Authentic Quran & Hadith, Islamic Wisdom, Global Dawah",
        language="en",
        posts_per_day=3,
        strict_authenticity=True,
        guidelines="Verified Quran Ayahs & Sahih Hadiths with pure transparent gold emblem banner. Strictly English content."
    )


if __name__ == "__main__":
    seed_default_profiles()
    print("OmniSocial Registry & Profiles Initialized successfully at:", PROFILES_DIR)
