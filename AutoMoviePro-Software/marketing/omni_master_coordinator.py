"""
=============================================================================
OmniSocial AI - Master Coordinator & Intelligent Boot Daemon
=============================================================================
Features:
1. Boot/Startup Smart Resume:
   - On PC startup, checks timestamp of last post for EVERY registered profile/page.
   - If interval has elapsed -> Immediately triggers posting routine.
   - If recently posted -> Calculates exact remaining sleep time and waits.
2. Concurrent Multi-Profile Orchestration:
   - Safely coordinates AutoMovie Pro, As-Sunnah Path Profile & Page, and future entities.
   - Respects mutual exclusion browser locks (`chrome_browser.lock`).
3. Comment / Inbox AI Supervision:
   - Periodically scans and replies to post comments using OmniCommentReplyAgent.
4. Live Real-time Status Broadcast:
   - Writes live status to `master_schedule_state.json` so the Desktop Widget updates live.
"""

import os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
import time
import json
import random
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = Path(r"E:\AI Assistant\Automations")
sys.path.append(str(BASE_DIR))

from omni_social_hub import OmniSocialRegistry, SocialEntity
from omni_comment_agent import OmniCommentReplyAgent

LOCK_FILE = BASE_DIR / "chrome_browser.lock"
AUTOPLAY_LOCK_TIMEOUT = 3600 # 60 minutes for extended organic human sessions


def acquire_browser_lock(timeout=600):
    start = time.time()
    while time.time() - start < timeout:
        if not LOCK_FILE.exists():
            try:
                LOCK_FILE.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
                return True
            except Exception:
                pass
        else:
            try:
                content = LOCK_FILE.read_text(encoding="utf-8").strip()
                _, ts = content.split(":")
                if time.time() - float(ts) > AUTOPLAY_LOCK_TIMEOUT:
                    print("[COORDINATOR] Overriding stale browser lock...")
                    LOCK_FILE.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
                    return True
            except Exception:
                pass
        time.sleep(3)
    return False


def release_browser_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


class MasterCoordinator:
    """Intelligent Multi-Entity Social Daemon."""

    def __init__(self):
        self.registry = OmniSocialRegistry
        self.retry_counts = {}
        self.retry_until_epochs = {}

    def broadcast_status(self, entity_id: str, action: str, details: str, next_eta: str = "", is_live: bool = False):
        state = self.registry.get_master_state()
        state["last_updated"] = datetime.now().isoformat()
        state["current_entity"] = entity_id
        state["current_action"] = action
        state["details"] = details
        state["is_live_active"] = is_live
        if is_live:
            if not state.get("live_session_start_epoch"):
                state["live_session_start_epoch"] = time.time()
        else:
            state["live_session_start_epoch"] = None

        if "next_scheduled_event" not in state or not isinstance(state["next_scheduled_event"], dict):
            state["next_scheduled_event"] = {}
        if next_eta:
            state["next_scheduled_event"][entity_id] = next_eta

        self.registry.update_master_state(state)
        print(f"[{datetime.now().strftime('%I:%M:%S %p')}] [{entity_id}] {action}: {details}", flush=True)

    def calculate_catchup_and_interval(self, entity: SocialEntity) -> Tuple[float, bool, int, int, float]:
        """
        Calculates effective interval based on downtime, daily target, and catch-up mode.
        Returns: (interval_seconds, is_catchup, count_today, daily_target, elapsed_hours)
        """
        eid = entity.entity_id
        cfg = entity.get_config()
        now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")

        history = entity.get_history()
        today_posts = [
            p for p in history
            if p.get("timestamp", "").startswith(today_str)
            and p.get("status") in ("published", "published_and_verified")
        ]
        count_today = len(today_posts)

        # Target daily posts
        if eid == "automovie_pro_page":
            daily_target = 10 # 10 posts/ads per day (alternating 5 banners + 5 videos)
        else:
            daily_target = int(cfg.get("content_strategy", {}).get("posts_per_day", 3))

        last_post_time = None
        if history:
            for entry in reversed(history):
                if entry.get("status") in ("published", "published_and_verified"):
                    ts = entry.get("timestamp")
                    if ts:
                        try:
                            last_post_time = datetime.fromisoformat(ts)
                            break
                        except Exception:
                            pass

        elapsed_hours = (now_dt - last_post_time).total_seconds() / 3600.0 if last_post_time else 999.0

        # Check if today's daily target has already been reached
        if count_today >= daily_target:
            # Plan for tomorrow morning 06:00 AM (staggered per channel)
            try:
                entities = self.registry.list_entities()
                idx = [e.entity_id for e in entities].index(eid) if eid in [e.entity_id for e in entities] else 0
            except Exception:
                idx = 0
            stagger_mins = idx * 25
            base_morning = now_dt.replace(hour=6, minute=0, second=0, microsecond=0)
            if now_dt.hour >= 6:
                base_morning = base_morning + timedelta(days=1)
            next_morning_dt = base_morning + timedelta(minutes=stagger_mins)
            interval_secs = max(3600.0, (next_morning_dt - now_dt).total_seconds())
            is_catchup = False
            return interval_secs, is_catchup, count_today, daily_target, elapsed_hours

        # User Directive: If PC was offline for hours or during daytime/evening while quota is not complete,
        # accelerate posting (catch-up mode):
        # - AutoMovie Pro: 20 to 25 mins interval between posts (alternating Banner & Video Ad)
        # - As-Sunnah Path: 35 to 45 mins interval between posts (completes 3 posts in ~1.5 to 2 hours)
        is_catchup = True

        if eid == "automovie_pro_page":
            interval_secs = random.uniform(20.0, 25.0) * 60.0 # 20-25 mins between alternating posts
        else:
            interval_secs = random.uniform(35.0, 45.0) * 60.0 # 35-45 mins for As-Sunnah channels

        return interval_secs, is_catchup, count_today, daily_target, elapsed_hours

    def run_entity_post(self, entity: SocialEntity):
        cfg = entity.get_config()
        eid = entity.entity_id

        self.broadcast_status(eid, "Acquiring Lock", "Waiting for exclusive browser lock...", is_live=False)
        if not acquire_browser_lock(timeout=300):
            self.broadcast_status(eid, "Lock Failed", "Browser busy. Will retry next cycle.", is_live=False)
            return False

        python_bin = sys.executable
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        try:
            if eid == "automovie_pro_page":
                # Alternating Format Selection (Image Banner vs Video Ad Reel)
                history = entity.get_history()
                last_format = "image"
                for entry in reversed(history):
                    if entry.get("status") in ("published", "published_and_verified"):
                        if entry.get("format") == "video" or "video_path" in entry:
                            last_format = "video"
                            break
                        elif entry.get("format") == "image" or "banner" in entry:
                            last_format = "image"
                            break

                next_format = "video" if last_format == "image" else "image"
                success = False
                caption_for_sentinel = ""

                if next_format == "video":
                    # --- Alternating Turn: Commercial Video Ad Reel ---
                    self.broadcast_status(eid, "AutoMovie Pro Video Ad", "অল্টারনেটিং সাইকেল: কাইনেটিক ভিডিও অ্যাড প্রোডাকশন ও রিল আপলোড শুরু...", is_live=True)
                    from omni_ad_studio_generator import OmniAdStudioGenerator, COMMERCIAL_AD_TEMPLATES
                    from omni_reel_publisher import OmniReelPublisher

                    video_to_post = None
                    tpl = random.choice(COMMERCIAL_AD_TEMPLATES)
                    ad_theme = tpl.get("theme", "AutoMovie Pro AI Video Marketing")

                    print(f"[COORDINATOR AD REEL] 🎬 Compiling fresh commercial video ad: {ad_theme}...", flush=True)
                    self.broadcast_status(eid, "ভিডিও অ্যাড রেন্ডারিং", f"কাইনেটিক অ্যাড রিল তৈরি হচ্ছে: {ad_theme[:35]}...", is_live=True)
                    reel_ok, reel_path, audit = OmniAdStudioGenerator.compile_ad_reel(tpl)

                    if reel_ok and reel_path and Path(reel_path).exists():
                        video_to_post = Path(reel_path)
                    else:
                        # Fallback to approved vault
                        vault_dir = Path(r"E:\AI Assistant\Social Media Hub\ad_marathon_vault\approved")
                        if vault_dir.exists():
                            vault_vids = list(vault_dir.glob("*.mp4"))
                            if vault_vids:
                                video_to_post = random.choice(vault_vids)

                    if video_to_post and video_to_post.exists():
                        pub = OmniReelPublisher(eid)
                        caption_text = pub.generate_dynamic_caption(topic=ad_theme)
                        caption_for_sentinel = caption_text
                        self.broadcast_status(eid, "রিল আপলোড হচ্ছে", f"ভিডিও রিল আপলোড শুরু (ব্যাকগ্রাউন্ড মোড): {video_to_post.name}", is_live=True)
                        res = pub.publish_video_reel(video_to_post, caption_text, topic=ad_theme)
                        success = res.get("success", False)

                        if success:
                            OmniAdStudioGenerator.record_ad_published({
                                "theme": ad_theme,
                                "file_path": str(video_to_post)
                            })
                            entity.append_post_history({
                                "format": "video",
                                "title": f"AutoMovie Pro Commercial Ad Reel ({ad_theme})",
                                "topic": ad_theme,
                                "video_path": str(video_to_post),
                                "caption_snippet": caption_text[:120],
                                "proof": res.get("proof", ""),
                                "status": "published_and_verified"
                            })
                    else:
                        print("[COORDINATOR] Failed to compile or locate video ad.", flush=True)
                        success = False

                else:
                    # --- Alternating Turn: Image Marketing Banner ---
                    self.broadcast_status(eid, "AutoMovie Pro Banner", "অল্টারনেটিং সাইকেল: হাই-কনভার্টিং মার্কেটিং ব্যানার প্রস্তুত ও পোস্ট...", is_live=True)
                    script = BASE_DIR / "FB_Human_Poster.py"
                    from AutoMovie_Content_Bank import get_dynamic_marketing_post
                    caption, banner_path = get_dynamic_marketing_post()
                    caption_for_sentinel = caption
                    self.broadcast_status(eid, "Posting Live", f"Selected banner: {Path(banner_path).name}", is_live=True)
                    proc = subprocess.Popen(
                        [python_bin, "-u", str(script), caption, banner_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        creationflags=creation_flags
                    )
                    for line in proc.stdout:
                        clean_line = line.strip()
                        if clean_line:
                            print(f"[{eid} SUB] {clean_line}", flush=True)
                    proc.wait()
                    success = (proc.returncode == 0)

                    if success:
                        entity.append_post_history({
                            "format": "image",
                            "title": "AutoMovie Pro SaaS Marketing Banner",
                            "topic": "Video Automation & Passive Income",
                            "banner": banner_path,
                            "caption_snippet": caption[:100],
                            "status": "published"
                        })

                if success:
                    self.retry_counts[eid] = 0
                    self.retry_until_epochs.pop(eid, None)
                    interval_secs, is_catchup, count_today, daily_target, el_hrs = self.calculate_catchup_and_interval(entity)
                    next_epoch = time.time() + interval_secs

                    # Automated Post Integrity & Self-Healing Audit (Directive 1)
                    try:
                        from omni_post_integrity_sentinel import PostIntegrityInspector
                        inspector = PostIntegrityInspector(eid)
                        inspector.execute_self_healing(caption_for_sentinel)
                    except Exception as e_insp:
                        print(f"[COORDINATOR SENTINEL NOTICE] {e_insp}", flush=True)

                    # Automated Organic Niche Sharing (Max 1-2 daily, Directive 2)
                    try:
                        from omni_social_sharer import SmartSocialSharer
                        sharer = SmartSocialSharer(eid)
                        if sharer.can_share_today():
                            sharer.execute_targeted_share(caption_for_sentinel)
                    except Exception as e_sh:
                        print(f"[COORDINATOR SHARER NOTICE] {e_sh}", flush=True)

                    # Automated Daily Story Publisher (Directive 3)
                    try:
                        from omni_story_publisher import OmniStoryPublisher
                        story_pub = OmniStoryPublisher(eid)
                        if not story_pub.has_uploaded_today():
                            story_pub.publish_daily_story()
                    except Exception as e_st:
                        print(f"[COORDINATOR STORY NOTICE] {e_st}", flush=True)

                    next_time_str = datetime.fromtimestamp(next_epoch).strftime("%I:%M %p")
                    state = self.registry.get_master_state()
                    if "target_epochs" not in state or not isinstance(state["target_epochs"], dict):
                        state["target_epochs"] = {}
                    state["target_epochs"][eid] = next_epoch
                    state["is_live_active"] = False
                    state["live_session_start_epoch"] = None
                    state["next_scheduled_event"][eid] = next_time_str
                    self.registry.update_master_state(state)

                    next_up_format = "ভিডিও অ্যাড (Reel)" if next_format == "image" else "ইমেজ ব্যানার (Banner)"
                    if count_today >= daily_target:
                        status_msg = f"{'ইমেজ ব্যানার' if next_format == 'image' else 'ভিডিও অ্যাড'} পোস্ট সফল! 🎉 আজকের দৈনিক কোটা সম্পন্ন ({count_today}/{daily_target})! পরবর্তী শিডিউল: আগামীকাল ভোর {next_time_str}"
                    else:
                        mode_text = f"🚀 ক্যাচ-আপ অ্যাক্সিলারেশন ({interval_secs/60:.0f} মি. বিরতি)"
                        status_msg = f"{'ইমেজ ব্যানার' if next_format == 'image' else 'ভিডিও অ্যাড'} পোস্ট সফল! {mode_text} (আজকে: {count_today}/{daily_target}) | পরবর্তী: {next_up_format} ({next_time_str}-এ)"

                    self.broadcast_status(
                        eid,
                        "Published",
                        status_msg,
                        next_eta=next_time_str,
                        is_live=False
                    )
                else:
                    failures = self.retry_counts.get(eid, 0) + 1
                    self.retry_counts[eid] = failures
                    retry_backoff = 120 if failures == 1 else (600 if failures == 2 else 1800)
                    next_epoch = time.time() + retry_backoff
                    self.retry_until_epochs[eid] = next_epoch
                    next_time_str = datetime.fromtimestamp(next_epoch).strftime("%I:%M:%S %p")
                    state = self.registry.get_master_state()
                    if "target_epochs" not in state or not isinstance(state["target_epochs"], dict):
                        state["target_epochs"] = {}
                    state["target_epochs"][eid] = next_epoch
                    state["is_live_active"] = False
                    state["live_session_start_epoch"] = None
                    state["next_scheduled_event"][eid] = next_time_str
                    self.registry.update_master_state(state)
                    mins_wait = int(retry_backoff // 60)
                    secs_wait = int(retry_backoff % 60)
                    self.broadcast_status(eid, "রিট্রাই করা হচ্ছে • RETRYING", f"পোস্টিং ব্যর্থ (চেষ্টা #{failures})। {mins_wait:02d}m:{secs_wait:02d}s পর পুনরায় রিট্রাই করা হচ্ছে...", next_eta=next_time_str, is_live=False)
                return success

            elif "assunnah" in eid:
                self.broadcast_status(eid, "As-Sunnah Posting", f"Preparing authentic Quran/Hadith post for {eid}...", is_live=True)
                from Assunnah_Content_Bank import get_dynamic_assunnah_post
                lang = "bn" if "bangla" in eid else "en"
                caption, banner_path = get_dynamic_assunnah_post(lang)

                script = BASE_DIR / "Assunnah_Poster.py"
                proc = subprocess.Popen(
                    [python_bin, "-u", str(script), eid],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    creationflags=creation_flags
                )
                for line in proc.stdout:
                    clean_line = line.strip()
                    if clean_line:
                        print(f"[{eid} SUB] {clean_line}", flush=True)
                proc.wait()
                success = (proc.returncode == 0)

                if success:
                    self.retry_counts[eid] = 0
                    self.retry_until_epochs.pop(eid, None)
                    interval_secs, is_catchup, count_today, daily_target, el_hrs = self.calculate_catchup_and_interval(entity)
                    next_epoch = time.time() + interval_secs
                    entity.append_post_history({
                        "title": f"Islamic Quran & Sunnah Post ({eid})",
                        "topic": "Authentic Hadith & Quran Reminders",
                        "banner": banner_path if banner_path else "Transparent Gold Emblem Banner",
                        "caption_snippet": caption[:120],
                        "status": "published",
                        "target": eid
                    })

                    # Automated Post Integrity & Self-Healing Audit (Directive 1)
                    try:
                        from omni_post_integrity_sentinel import PostIntegrityInspector
                        inspector = PostIntegrityInspector(eid)
                        inspector.execute_self_healing(caption)
                    except Exception as e_insp:
                        print(f"[COORDINATOR SENTINEL NOTICE] {e_insp}", flush=True)

                    # Automated Organic Niche Sharing (Max 1-2 daily, Directive 2)
                    try:
                        from omni_social_sharer import SmartSocialSharer
                        sharer = SmartSocialSharer(eid)
                        if sharer.can_share_today():
                            sharer.execute_targeted_share(caption)
                    except Exception as e_sh:
                        print(f"[COORDINATOR SHARER NOTICE] {e_sh}", flush=True)

                    # Automated Daily Story Publisher (Directive 3)
                    try:
                        from omni_story_publisher import OmniStoryPublisher
                        story_pub = OmniStoryPublisher(eid)
                        if not story_pub.has_uploaded_today():
                            story_pub.publish_daily_story()
                    except Exception as e_st:
                        print(f"[COORDINATOR STORY NOTICE] {e_st}", flush=True)

                    next_time_str = datetime.fromtimestamp(next_epoch).strftime("%I:%M %p")
                    state = self.registry.get_master_state()
                    if "target_epochs" not in state or not isinstance(state["target_epochs"], dict):
                        state["target_epochs"] = {}
                    state["target_epochs"][eid] = next_epoch
                    state["is_live_active"] = False
                    state["live_session_start_epoch"] = None
                    state["next_scheduled_event"][eid] = next_time_str
                    if count_today >= daily_target:
                        status_msg = f"{eid} পোস্ট সফল! 🎉 আজকের দৈনিক কোটা সম্পন্ন ({count_today}/{daily_target})! পরবর্তী শিডিউল: আগামীকাল ভোর {next_time_str}"
                    else:
                        mode_text = f"🚀 ক্যাচ-আপ মোড ({interval_secs/60:.0f} মি. বিরতি)"
                        status_msg = f"{eid} পোস্ট সফল! {mode_text} (আজকে: {count_today}/{daily_target}) | পরবর্তী: {next_time_str}-এ"
                    self.broadcast_status(eid, "Published", status_msg, next_eta=next_time_str, is_live=False)
                else:
                    failures = self.retry_counts.get(eid, 0) + 1
                    self.retry_counts[eid] = failures
                    retry_backoff = 120 if failures == 1 else (600 if failures == 2 else 1800)
                    next_epoch = time.time() + retry_backoff
                    self.retry_until_epochs[eid] = next_epoch
                    next_time_str = datetime.fromtimestamp(next_epoch).strftime("%I:%M:%S %p")
                    state = self.registry.get_master_state()
                    if "target_epochs" not in state or not isinstance(state["target_epochs"], dict):
                        state["target_epochs"] = {}
                    state["target_epochs"][eid] = next_epoch
                    state["is_live_active"] = False
                    state["live_session_start_epoch"] = None
                    state["next_scheduled_event"][eid] = next_time_str
                    self.registry.update_master_state(state)
                    mins_wait = int(retry_backoff // 60)
                    secs_wait = int(retry_backoff % 60)
                    self.broadcast_status(eid, "রিট্রাই করা হচ্ছে • RETRYING", f"পোস্টিং ব্যর্থ (চেষ্টা #{failures})। {mins_wait:02d}m:{secs_wait:02d}s পর পুনরায় রিট্রাই করা হচ্ছে...", next_eta=next_time_str, is_live=False)
                return success

        except Exception as e:
            failures = self.retry_counts.get(eid, 0) + 1
            self.retry_counts[eid] = failures
            retry_backoff = 120 if failures == 1 else 600
            next_epoch = time.time() + retry_backoff
            self.retry_until_epochs[eid] = next_epoch
            next_time_str = datetime.fromtimestamp(next_epoch).strftime("%I:%M:%S %p")
            state = self.registry.get_master_state()
            if "target_epochs" not in state or not isinstance(state["target_epochs"], dict):
                state["target_epochs"] = {}
            state["target_epochs"][eid] = next_epoch
            self.registry.update_master_state(state)
            self.broadcast_status(eid, "রিট্রাই করা হচ্ছে • RETRYING", f"ত্রুটি: {str(e)}। রিট্রাই নির্ধারণ করা হচ্ছে...", next_eta=next_time_str, is_live=False)
            return False
        finally:
            state = self.registry.get_master_state()
            state["is_live_active"] = False
            state["live_session_start_epoch"] = None
            self.registry.update_master_state(state)
            release_browser_lock()

    def check_and_run_all(self):
        """Intelligent loop checking last post times for all entities with starvation prevention."""
        raw_entities = self.registry.list_entities()
        if not raw_entities:
            print("[COORDINATOR] No registered entities found.")
            return

        now_dt = datetime.now()
        now_epoch = time.time()

        # Prioritization: Sort entities by urgency (Least Recently Posted First)
        # Channels that have gone without posting the longest get absolute priority!
        def entity_urgency_score(ent):
            eid = ent.entity_id
            cfg = ent.get_config()
            if cfg.get("status") != "active":
                return -1000.0

            # If in retry backoff, deprioritize until backoff passes
            if eid in self.retry_until_epochs and now_epoch < self.retry_until_epochs[eid]:
                return -500.0

            history = ent.get_history()
            last_ts = None
            for p in reversed(history):
                if p.get("status") in ("published", "published_and_verified"):
                    ts = p.get("timestamp")
                    if ts:
                        try:
                            last_ts = datetime.fromisoformat(ts)
                            break
                        except Exception:
                            pass
            if not last_ts:
                return 999999.0  # Never posted -> Absolute Priority
            return (now_dt - last_ts).total_seconds()

        entities = sorted(raw_entities, key=entity_urgency_score, reverse=True)

        for entity in entities:
            cfg = entity.get_config()
            eid = entity.entity_id
            if cfg.get("status") != "active":
                continue

            # 1. Manual Pause & Safe Cooldown Check (Directive 5)
            pause_until = float(cfg.get("paused_until_epoch", 0))
            if pause_until > now_epoch:
                rem_pause_m = int((pause_until - now_epoch) / 60)
                next_time_str = datetime.fromtimestamp(pause_until).strftime("%I:%M %p")
                self.broadcast_status(eid, "পজ করা হয়েছে • PAUSED", f"ম্যানুয়াল/অটো বিরতি সক্রিয় ({rem_pause_m} মিনিট বাকি)", next_eta=next_time_str)
                continue

            # 2. Check if entity is in active retry backoff
            retry_until = self.retry_until_epochs.get(eid, 0)
            if now_epoch < retry_until:
                rem_backoff = retry_until - now_epoch
                m = int(rem_backoff // 60)
                s = int(rem_backoff % 60)
                next_time_str = datetime.fromtimestamp(retry_until).strftime("%I:%M:%S %p")
                self.broadcast_status(eid, "রিট্রাই অপেক্ষমান • RETRY QUEUED", f"ব্যর্থতার পর কুলডাউন সক্রিয় ({m:02d}m:{s:02d}s বাকি)", next_eta=next_time_str)
                continue

            # 3. Human-Like Nocturnal Safety Pause (11:30 PM to 05:30 AM Local Time)
            cur_hour = now_dt.hour
            cur_minute = now_dt.minute
            is_night_time = (cur_hour == 23 and cur_minute >= 30) or (cur_hour >= 0 and cur_hour < 5) or (cur_hour == 5 and cur_minute <= 30)
            if is_night_time and not cfg.get("override_night_pause", False):
                # Stagger wake-up time per entity so they never collide
                idx = raw_entities.index(entity) if entity in raw_entities else 0
                stagger_offset_mins = idx * 25  # 25 minutes gap per channel
                base_morning_dt = now_dt.replace(hour=6, minute=0, second=0, microsecond=0)
                if cur_hour >= 23:
                    base_morning_dt = base_morning_dt.replace(day=now_dt.day + 1)

                next_morning_dt = base_morning_dt + timedelta(minutes=stagger_offset_mins)
                next_epoch = next_morning_dt.timestamp()
                next_time_str = next_morning_dt.strftime("%I:%M %p")
                state = self.registry.get_master_state()
                if "target_epochs" not in state: state["target_epochs"] = {}
                state["target_epochs"][eid] = next_epoch
                self.registry.update_master_state(state)
                self.broadcast_status(eid, "রাত্রিকালীন বিরতি • SLEEP PAUSE", f"হিউম্যান-লাইক অ্যাক্টিভিটি বজায় রাখতে রাত ১১:৩০ থেকে ভোর শিডিউলিং স্থগিত (ভোর {next_time_str}-এ এক্টিভ হবে)।", next_eta=next_time_str)
                continue

            # Calculate dynamic interval and catch-up mode
            interval_secs, is_catchup, count_today, daily_target, elapsed_hours = self.calculate_catchup_and_interval(entity)

            # Check if today's daily target has already been reached
            if count_today >= daily_target:
                try:
                    idx = [e.entity_id for e in raw_entities].index(eid) if eid in [e.entity_id for e in raw_entities] else 0
                except Exception:
                    idx = 0
                stagger_offset_mins = idx * 25
                base_morning_dt = now_dt.replace(hour=6, minute=0, second=0, microsecond=0)
                if now_dt.hour >= 6:
                    base_morning_dt = base_morning_dt + timedelta(days=1)
                next_morning_dt = base_morning_dt + timedelta(minutes=stagger_offset_mins)
                next_epoch = next_morning_dt.timestamp()
                next_time_str = next_morning_dt.strftime("%I:%M %p")
                state = self.registry.get_master_state()
                if "target_epochs" not in state: state["target_epochs"] = {}
                state["target_epochs"][eid] = next_epoch
                self.registry.update_master_state(state)
                self.broadcast_status(
                    eid,
                    "দৈনিক কোটা সম্পন্ন",
                    f"আজকের দৈনিক কোটা সম্পন্ন ({count_today}/{daily_target}) | পরবর্তী শিডিউল: আগামীকাল ভোর {next_time_str}",
                    next_eta=next_time_str
                )
                continue

            # Check last post from history
            history = entity.get_history()
            last_post_time = None
            if history:
                for entry in reversed(history):
                    if entry.get("status") in ("published", "published_and_verified"):
                        ts = entry.get("timestamp")
                        if ts:
                            try:
                                last_post_time = datetime.fromisoformat(ts)
                                break
                            except Exception:
                                pass

            should_post = False
            if last_post_time is None:
                should_post = True
                reason = f"আজকের প্রথম পোস্ট প্রস্তুত ({count_today}/{daily_target}) | Catchup: {is_catchup}"
                next_epoch = now_epoch
                next_time_str = now_dt.strftime("%I:%M %p")
            else:
                elapsed_secs = (now_dt - last_post_time).total_seconds()
                next_due_dt = last_post_time + timedelta(seconds=interval_secs)
                next_due_epoch = next_due_dt.timestamp()

                if now_epoch >= next_due_epoch:
                    should_post = True
                    reason = f"বিরতি অতিক্রান্ত ({elapsed_secs/60:.0f} মি. >= {interval_secs/60:.0f} মি.) | Catchup: {is_catchup} | আজকের পোস্ট: {count_today}/{daily_target}"
                    next_epoch = now_epoch
                    next_time_str = now_dt.strftime("%I:%M %p")
                else:
                    remaining_mins = (next_due_epoch - now_epoch) / 60.0
                    reason = f"অপেক্ষমান ({remaining_mins:.0f} মি. বাকি) | Catchup: {is_catchup} | আজকের পোস্ট: {count_today}/{daily_target}"
                    next_epoch = next_due_epoch
                    next_time_str = next_due_dt.strftime("%I:%M %p")

            # Always update target_epochs and next_scheduled_event in state
            state = self.registry.get_master_state()
            if "target_epochs" not in state: state["target_epochs"] = {}
            state["target_epochs"][eid] = next_epoch
            self.registry.update_master_state(state)

            if should_post:
                print(f"[BOOT / CRON CHECK] Triggering post for {eid} (Reason: {reason})")
                self.run_entity_post(entity)
                # After running, pause with a safe human buffer (25-45s) and break this cycle so others wait cleanly
                time.sleep(random.uniform(25, 45))
                break
            else:
                self.broadcast_status(eid, "Scheduled / Waiting", f"{reason}", next_eta=next_time_str)

        # Autonomous Scheduled Video Reels & Shorts Cycle
        self.check_and_run_reels()

    def check_and_run_reels(self):
        """Intelligent autonomous Reel & Short schedule coordinator."""
        try:
            from omni_reel_publisher import OmniReelPublisher
            entities = self.registry.list_entities()
            for entity in entities:
                eid = entity.entity_id
                # Video reels for AutoMovie Pro are orchestrated directly in the alternating hourly cycle
                if eid == "automovie_pro_page":
                    continue
                cfg = entity.get_config()
                if cfg.get("status") != "active":
                    continue
                pub = OmniReelPublisher(eid)
                due_slot = pub.get_due_schedule_slot()
                can_pub, reason = pub.can_publish_reel_today()
                if due_slot and can_pub:
                    print(f"[REEL SCHEDULE] Slot [{due_slot}] is due for {eid}! Triggering autonomous reel publication...", flush=True)
                    self.broadcast_status(eid, "রিল আপলোড সক্রিয় • REEL PUBLISHING", f"শিডিউল স্লট [{due_slot}] এর জন্য ভিডিও রিল আপলোড শুরু হচ্ছে...", is_live=True)
                    res = pub.publish_scheduled_reel(force=False)
                    if res.get("success"):
                        self.broadcast_status(eid, "রিল পাবলিশ সফল • REEL PUBLISHED", f"স্লট [{due_slot}] সফলভাবে প্রকাশিত! প্রমাণ: {Path(res.get('proof', '')).name}", is_live=False)
                    else:
                        self.broadcast_status(eid, "রিল আপলোড ব্যর্থ", f"ত্রুটি: {res.get('error') or res.get('reason')}", is_live=False)
                    time.sleep(15)
                    break
        except Exception as e:
            print(f"[COORDINATOR REEL NOTICE] {e}", flush=True)

    def start_infinite_daemon(self):
        print("="*65)
        print(" AutoMovie Pro - Social Media & Ad Automation Suite 🚀")
        print(" Connected Channels: AutoMovie Pro Official & As-Sunnah Path")
        print("="*65, flush=True)

        # Boot Check immediately upon startup
        self.broadcast_status("Master", "Boot Startup Check", "Checking last post records across all channels...")
        self.check_and_run_all()

        while True:
            # Check every 60 seconds
            time.sleep(60)
            
            # Autonomous Self-Healing Diagnostic Cycle
            try:
                from omni_self_healing_agent import OmniSelfHealingSentinel
                sentinel = OmniSelfHealingSentinel()
                sentinel.execute_full_health_cycle()
            except Exception as e:
                print(f"[COORDINATOR SENTINEL NOTICE] {e}", flush=True)

            self.check_and_run_all()


if __name__ == "__main__":
    coordinator = MasterCoordinator()
    coordinator.start_infinite_daemon()
