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

BASE_DIR = Path(r"E:\AI Assistant\Automations")
sys.path.append(str(BASE_DIR))

from omni_social_hub import OmniSocialRegistry, SocialEntity
from omni_comment_agent import OmniCommentReplyAgent

LOCK_FILE = BASE_DIR / "chrome_browser.lock"
AUTOPLAY_LOCK_TIMEOUT = 900 # 15 minutes


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
                self.broadcast_status(eid, "AutoMovie Pro Posting", "Generating dynamic marketing banner and launching poster...", is_live=True)
                script = BASE_DIR / "FB_Human_Poster.py"
                from AutoMovie_Content_Bank import get_dynamic_marketing_post
                caption, banner_path = get_dynamic_marketing_post()
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
                
                # Calculate next epoch immediately
                strat = cfg.get("content_strategy", {})
                interval_hours = float(strat.get("interval_hours_min", 2.0))
                if success:
                    self.retry_counts[eid] = 0
                    next_epoch = time.time() + (interval_hours * 3600)
                    entity.append_post_history({
                        "title": "AutoMovie Pro SaaS Marketing Banner",
                        "topic": "Video Automation & Passive Income",
                        "banner": banner_path,
                        "caption_snippet": caption[:100],
                        "status": "published"
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

                    # Automated Daily Business Ad Reel & Video Generator (Directive 10 - Personal AutoMovie Pro)
                    if "automovie" in eid:
                        try:
                            from omni_ad_studio_generator import OmniAdStudioGenerator, COMMERCIAL_AD_TEMPLATES
                            if OmniAdStudioGenerator.can_publish_ad_today():
                                print(f"[COORDINATOR AD REEL] Generating daily commercial business ad reel for {eid}...", flush=True)
                                tpl = random.choice(COMMERCIAL_AD_TEMPLATES)
                                reel_ok, reel_path, audit = OmniAdStudioGenerator.compile_ad_reel(tpl)
                                if reel_ok:
                                    print(f"[COORDINATOR AD REEL] ✅ Ad Reel approved by Gemini & compiled: {reel_path.name}", flush=True)
                        except Exception as e_ad:
                            print(f"[COORDINATOR AD REEL NOTICE] {e_ad}", flush=True)

                    next_time_str = datetime.fromtimestamp(next_epoch).strftime("%I:%M %p")
                    state = self.registry.get_master_state()
                    if "target_epochs" not in state or not isinstance(state["target_epochs"], dict):
                        state["target_epochs"] = {}
                    state["target_epochs"][eid] = next_epoch
                    state["is_live_active"] = False
                    state["live_session_start_epoch"] = None
                    state["next_scheduled_event"][eid] = next_time_str
                    self.registry.update_master_state(state)
                    self.broadcast_status(eid, "Published", "Post published, verified, and audited successfully!", next_eta=next_time_str, is_live=False)
                else:
                    failures = self.retry_counts.get(eid, 0) + 1
                    self.retry_counts[eid] = failures
                    retry_backoff = 120 if failures == 1 else (600 if failures == 2 else 1800)
                    next_epoch = time.time() + retry_backoff
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
                
                strat = cfg.get("content_strategy", {})
                interval_hours = float(strat.get("interval_hours_min", 7.0))
                if success:
                    self.retry_counts[eid] = 0
                    next_epoch = time.time() + (interval_hours * 3600)
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
                    self.registry.update_master_state(state)
                    self.broadcast_status(eid, "Published", f"{eid} post published, verified, and audited successfully!", next_eta=next_time_str, is_live=False)
                else:
                    failures = self.retry_counts.get(eid, 0) + 1
                    self.retry_counts[eid] = failures
                    retry_backoff = 120 if failures == 1 else (600 if failures == 2 else 1800)
                    next_epoch = time.time() + retry_backoff
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
        """Intelligent loop checking last post times for all entities."""
        entities = self.registry.list_entities()
        if not entities:
            print("[COORDINATOR] No registered entities found.")
            return

        now_dt = datetime.now()
        now_epoch = time.time()

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

            # 2. Human-Like Nocturnal Safety Pause (11:30 PM to 05:30 AM Local Time)
            cur_hour = now_dt.hour
            cur_minute = now_dt.minute
            is_night_time = (cur_hour == 23 and cur_minute >= 30) or (cur_hour >= 0 and cur_hour < 5) or (cur_hour == 5 and cur_minute <= 30)
            if is_night_time and not cfg.get("override_night_pause", False):
                # Stagger wake-up time per entity (e.g. 06:00, 06:25, 06:50, 07:15) so they never collide
                idx = entities.index(entity) if entity in entities else 0
                stagger_offset_mins = idx * 25 # 25 minutes gap per channel
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

            strat = cfg.get("content_strategy", {})
            min_hours = float(strat.get("interval_hours_min", 2.0))
            
            # Check last post from history
            history = entity.get_history()
            last_post_time = None
            if history:
                try:
                    last_ts_str = history[-1].get("timestamp")
                    last_post_time = datetime.fromisoformat(last_ts_str)
                except Exception:
                    pass

            state = self.registry.get_master_state()
            target_epoch = state.get("target_epochs", {}).get(eid, 0)
            
            if target_epoch > now_epoch:
                remaining_mins = (target_epoch - now_epoch) / 60.0
                should_post = False
                reason = f"Scheduled epoch in future ({remaining_mins:.1f} mins remaining)."
            elif last_post_time is None:
                should_post = True
                reason = "Never posted before"
            else:
                elapsed_hours = (now_dt - last_post_time).total_seconds() / 3600.0
                # Morning window (06:00 to 10:30 AM): after overnight nocturnal pause, allow morning post if >= 4.5h elapsed
                is_morning_window = (now_dt.hour in [6, 7, 8, 9, 10])
                effective_min_hours = min(min_hours, 4.5) if is_morning_window else min_hours
                if elapsed_hours >= effective_min_hours:
                    should_post = True
                    reason = f"Interval elapsed ({elapsed_hours:.1f}h >= {effective_min_hours:.1f}h)"
                else:
                    remaining_mins = (effective_min_hours - elapsed_hours) * 60
                    reason = f"Recent post found. Waiting {remaining_mins:.0f} mins."

            if should_post:
                print(f"[BOOT / CRON CHECK] Triggering post for {eid} (Reason: {reason})")
                self.run_entity_post(entity)
                # After running, pause with a safe human buffer (30-60s) and break this cycle so others wait cleanly
                time.sleep(random.uniform(25, 45))
                break
            else:
                next_epoch = time.time() + (remaining_mins * 60)
                next_time_str = datetime.fromtimestamp(next_epoch).strftime("%I:%M %p")
                state = self.registry.get_master_state()
                if "target_epochs" not in state:
                    state["target_epochs"] = {}
                state["target_epochs"][eid] = next_epoch
                self.registry.update_master_state(state)
                self.broadcast_status(eid, "Scheduled / Waiting", f"{reason}", next_eta=next_time_str)

    def start_infinite_daemon(self):
        print("="*65)
        print(" OmniSocial Master Coordinator Daemon Running 🚀")
        print(" Connected Profiles & Pages: AutoMovie Pro & As-Sunnah Path")
        print("="*65, flush=True)

        # Boot Check immediately upon startup
        self.broadcast_status("Master", "Boot Startup Check", "Checking last post records across all profiles...")
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
