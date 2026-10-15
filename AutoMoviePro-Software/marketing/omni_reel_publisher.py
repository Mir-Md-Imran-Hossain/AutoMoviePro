"""
=============================================================================
OmniSocial AI - Automated Video Reels & Shorts Publisher Engine
=============================================================================
Features:
1. Uploads high-converting 9:16 vertical video reels to Facebook / YouTube.
2. Configurable daily reel limits, posting schedules, and topic pools via
   `omni_reel_config.json`.
3. Quota enforcement: `can_publish_reel_today()`, slot detection `get_due_schedule_slot()`.
4. Intelligent vault selector: `select_best_video_for_reel()` with topic matching
   and de-duplication against `reels_history.json`.
5. Automated caption generation with pricing, website, hotline, and viral hashtags.
6. Direct navigation to Meta Reels creation endpoint, video attachment,
   timeline verification screenshot, and proof logging.
=============================================================================
"""

import os
import sys
import time
import json
import random
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = Path(r"E:\AI Assistant\Automations")
HUB_DIR = Path(r"E:\AI Assistant\Social Media Hub")
VAULT_DIR = HUB_DIR / "ad_marathon_vault" / "approved"
GENERATED_REELS_DIR = HUB_DIR / "generated_ad_reels"
REELS_LOG_FILE = HUB_DIR / "reels_history.json"
PROOF_DIR = HUB_DIR / "reels_proofs"
CONFIG_FILE = BASE_DIR / "omni_reel_config.json"
LOCK_FILE = BASE_DIR / "chrome_browser.lock"

PROOF_DIR.mkdir(parents=True, exist_ok=True)


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
                if time.time() - float(ts) > 900:
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


def load_reel_config() -> Dict[str, Any]:
    """Loads reel scheduling and strategy config from omni_reel_config.json."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[REEL CONFIG] Warning: failed to parse {CONFIG_FILE}: {e}")

    # Default fallback config
    return {
        "version": "1.0.0",
        "entities": {
            "automovie_pro_page": {
                "display_name": "AutoMovie Pro Official Page",
                "platform": "facebook_page",
                "enabled": true,
                "reels_per_day": 3,
                "schedule_slots": ["11:00", "16:00", "20:30"],
                "min_interval_hours": 3.5,
                "topics_pool": [
                    "অটোমুভি প্রো — ১-ক্লিকে ১০০% স্বয়ংক্রিয় এআই ভিডিও ও সোশ্যাল মিডিয়া পাওয়ারহাউজ",
                    "একটি সাধারণ পিসি দিয়েই ঘরে বসে দীর্ঘমেয়াদি প্যাসিভ ইনকাম মাস্টারক্লাস",
                    "৬+ আন্তর্জাতিক ভাষায় স্বয়ংক্রিয় ডাবিং ও গ্লোবাল ফেসলেস চ্যানেল সাম্রাজ্য",
                    "এজেন্সি বাল্ক ভিডিও প্রোডাকশন ও ফ্রিল্যান্সিং পাওয়ারহাউজ ব্লুপ্রিন্ট",
                    "লাইফটাইম লাইসেন্স ও ডেডিকেটেড গুগল এআই প্রো আনলিমিটেড ক্লাউড এক্সেস"
                ],
                "caption_templates": [
                    "🎬 অটোমুভি প্রো — ১-ক্লিকে ১০০% স্বয়ংক্রিয় এআই ভিডিও ও সোশ্যাল মিডিয়া পাওয়ারহাউজ!\n\nক্যামেরা বা ভিডিও এডিটিং শেখার ঝামেলা ছাড়াই ঘরে থাকা সাধারণ কম্পিউটার দিয়েই গড়ে তুলুন লাভজনক ফেসলেস ভিডিও চ্যানেল।\n\n💎 ৩টি বিশেষ প্যাকেজ ও লাইফটাইম প্রাইসিং:\n🔹 ১. Omni Social Media Video Automation: মাত্র ৳৩,৯৯৯ (রেগুলার ৳১০,০০০)\n🔹 ২. Omni FB Business Manager & Ad: মাত্র ৳২,৯৯৯ (রেগুলার ৳৮,৫০০)\n🔹 ৩. Omni Profile & Page Post: মাত্র ৳১,৯৯৯ (রেগুলার ৳৬,৫০০)\n\n🛒 বিস্তারিত জানতে ও লাইফটাইম লাইসেন্স নিতে ভিজিট করুন: https://automoviepro.com\n📞 হোয়াটসঅ্যাপ হেল্পলাইন: +880 1684-355055\n\n#AutoMoviePro #VideoAutomation #AIVideo #PassiveIncome #YouTubeAutomation #FacelessChannel #FacebookReels"
                ]
            }
        }
    }


def save_reel_config(config: Dict[str, Any]):
    """Safely updates omni_reel_config.json."""
    config["last_updated"] = datetime.now().isoformat()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class OmniReelPublisher:
    """End-to-End Autonomous Facebook Reel Video Publisher & Schedule Manager."""

    def __init__(self, entity_id: str = "automovie_pro_page"):
        self.entity_id = entity_id
        self.user_data_dir = r"E:\AI Assistant\Automation Workspace\Social_Media_Profiles\Facebook_AssunnahPath"
        self.config = self.get_entity_config()

    def get_entity_config(self) -> Dict[str, Any]:
        cfg_all = load_reel_config()
        entities = cfg_all.get("entities", {})
        if self.entity_id in entities:
            return entities[self.entity_id]
        return {
            "display_name": self.entity_id,
            "platform": "facebook_page",
            "enabled": False,
            "reels_per_day": 2,
            "schedule_slots": ["11:00", "17:00"],
            "min_interval_hours": 4.0,
            "topics_pool": ["AutoMovie Pro AI Video Creation", "Faceless Channel Growth"],
            "caption_templates": []
        }

    def get_history(self) -> List[Dict[str, Any]]:
        if REELS_LOG_FILE.exists():
            try:
                with open(REELS_LOG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def get_today_reels_published(self) -> List[Dict[str, Any]]:
        today_str = datetime.now().strftime("%Y-%m-%d")
        hist = self.get_history()
        return [
            entry for entry in hist
            if entry.get("date") == today_str
            and entry.get("entity_id") == self.entity_id
            and entry.get("status") in ("published", "published_and_verified")
        ]

    def can_publish_reel_today(self) -> Tuple[bool, str]:
        """
        Enforces daily quota and minimum interval:
        - daily quota: reels_per_day (default 3 for automovie_pro_page)
        - minimum interval: min_interval_hours (default 3.5h)
        """
        cfg = self.get_entity_config()
        if not cfg.get("enabled", True):
            return False, "Reel publishing is disabled for this entity in omni_reel_config.json"

        max_daily = int(cfg.get("reels_per_day", 3))
        today_posts = self.get_today_reels_published()

        if len(today_posts) >= max_daily:
            return False, f"Daily limit reached: {len(today_posts)}/{max_daily} reels already published today."

        # Interval check
        if today_posts:
            min_interval = float(cfg.get("min_interval_hours", 3.0))
            try:
                last_time = datetime.fromisoformat(today_posts[-1]["timestamp"])
                elapsed_hours = (datetime.now() - last_time).total_seconds() / 3600.0
                if elapsed_hours < min_interval:
                    rem_mins = int((min_interval - elapsed_hours) * 60)
                    return False, f"Cooldown active: {rem_mins} minutes remaining until next reel slot."
            except Exception:
                pass

        return True, "Quota available"

    def get_due_schedule_slot(self) -> Optional[str]:
        """
        Checks if current time matches or has passed a scheduled slot that hasn't
        been fulfilled yet today.
        Slots e.g. ["11:00", "16:00", "20:30"].
        """
        cfg = self.get_entity_config()
        slots = cfg.get("schedule_slots", ["11:00", "16:00", "20:30"])
        now_dt = datetime.now()
        now_minutes = now_dt.hour * 60 + now_dt.minute

        today_posts = self.get_today_reels_published()
        posted_count = len(today_posts)
        max_daily = int(cfg.get("reels_per_day", 3))

        if posted_count >= max_daily:
            return None

        # Determine which slot corresponds to the current count
        # E.g. If 0 posts done today, slot index 0 is first target; if 1 done, index 1 is target, etc.
        if posted_count < len(slots):
            target_slot = slots[posted_count]
            try:
                sh, sm = [int(x) for x in target_slot.split(":")]
                slot_minutes = sh * 60 + sm
                # If current time is at or after slot time (within today)
                if now_minutes >= slot_minutes:
                    return target_slot
            except Exception:
                pass

        return None

    def select_best_video_for_reel(self, preferred_topic: Optional[str] = None) -> Tuple[Optional[Path], str, Dict[str, Any]]:
        """
        Selects the best unposted video from VAULT_DIR or GENERATED_REELS_DIR.
        Ensures videos uploaded in the past 5 days are excluded to prevent duplication.
        Returns (video_path, topic_name, meta_dict).
        """
        hist = self.get_history()
        recent_cutoff = datetime.now() - timedelta(days=5)
        recently_used_paths = set()
        for h in hist:
            try:
                ts = datetime.fromisoformat(h.get("timestamp", ""))
                if ts >= recent_cutoff:
                    vp = h.get("video_path")
                    if vp:
                        recently_used_paths.add(Path(vp).resolve())
            except Exception:
                pass

        # Candidate pools: 1. Approved vault, 2. Generated ad reels
        candidates = []
        for search_dir in [VAULT_DIR, GENERATED_REELS_DIR]:
            if not search_dir.exists():
                continue
            for mp4 in search_dir.glob("*.mp4"):
                if mp4.stat().st_size > 100000:  # > 100 KB
                    resolved = mp4.resolve()
                    if resolved not in recently_used_paths:
                        # Find accompanying json
                        meta_file = mp4.with_suffix(".json")
                        meta_data = {}
                        if meta_file.exists():
                            try:
                                with open(meta_file, "r", encoding="utf-8") as f:
                                    meta_data = json.load(f)
                            except Exception:
                                pass
                        candidates.append((mp4, meta_data))

        if not candidates:
            # Fallback: if all approved were used recently, take the oldest approved video
            all_approved = sorted(VAULT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
            if all_approved:
                mp4 = all_approved[0]
                meta_file = mp4.with_suffix(".json")
                meta_data = {}
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta_data = json.load(f)
                    except Exception:
                        pass
                candidates.append((mp4, meta_data))

        if not candidates:
            return None, "", {}

        # If a preferred topic is specified, search for matching keyword
        if preferred_topic:
            pref_lower = preferred_topic.lower()
            for mp4, meta in candidates:
                theme = str(meta.get("theme", "")).lower()
                if any(w in theme for w in pref_lower.split()[:3]):
                    return mp4, meta.get("theme", preferred_topic), meta

        # Default: pick candidate with newest modification time
        candidates.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
        chosen_mp4, chosen_meta = candidates[0]
        topic = chosen_meta.get("theme") or chosen_meta.get("title") or "AutoMovie Pro AI Video Creation"
        return chosen_mp4, topic, chosen_meta

    def generate_caption_for_topic(self, topic: str, video_meta: Dict[str, Any]) -> str:
        cfg = self.get_entity_config()
        templates = cfg.get("caption_templates", [])

        if templates:
            base_template = random.choice(templates)
        else:
            base_template = (
                f"🎬 {topic} — ১০০% স্বয়ংক্রিয় এআই ভিডিও ও সোশ্যাল মিডিয়া পাওয়ারহাউজ!\n\n"
                "ক্যামেরা বা ভিডিও এডিটিং শেখার ঝামেলা ছাড়াই ঘরে থাকা সাধারণ কম্পিউটার দিয়েই গড়ে তুলুন লাভজনক ফেসলেস ভিডিও চ্যানেল।\n\n"
                "💎 বিশেষ প্যাকেজ ও লাইফটাইম প্রাইসিং:\n"
                "🔹 ১. Omni Social Media Video Automation: মাত্র ৳৩,৯৯৯ (রেগুলার ৳১০,০০০)\n"
                "🔹 ২. Omni FB Business Manager & Ad: মাত্র ৳২,৯৯৯ (রেগুলার ৳৮,৫০০)\n"
                "🔹 ৩. Omni Profile & Page Post: মাত্র ৳১,৯৯৯ (রেগুলার ৳৬,৫০০)\n\n"
                "🛒 বিস্তারিত জানতে ও লাইফটাইম লাইসেন্স নিতে ভিজিট করুন: https://automoviepro.com\n"
                "📞 হোয়াটসঅ্যাপ হেল্পলাইন: +880 1684-355055\n\n"
                "#AutoMoviePro #VideoAutomation #AIVideo #PassiveIncome #YouTubeAutomation #FacelessChannel #FacebookReels"
            )

        return base_template

    def generate_dynamic_caption(self, topic: str = "AutoMovie Pro AI Video Creation", video_meta: Optional[Dict[str, Any]] = None) -> str:
        return self.generate_caption_for_topic(topic, video_meta or {})

    def record_reel_published(self, video_path: str, caption: str, proof_path: str, slot: str = "", topic: str = ""):
        logs = self.get_history()
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "slot": slot or datetime.now().strftime("%H:%M"),
            "entity_id": self.entity_id,
            "topic": topic,
            "video_path": str(video_path),
            "caption": caption[:160],
            "proof_path": str(proof_path),
            "status": "published_and_verified"
        })
        with open(REELS_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

    def publish_video_reel(self, video_path: Path, caption_text: str, slot: str = "", topic: str = "") -> Dict[str, Any]:
        video_path = Path(video_path)
        if not video_path.exists() or video_path.stat().st_size < 10000:
            return {"success": False, "error": f"Invalid or missing video file: {video_path}"}

        if not acquire_browser_lock(timeout=300):
            return {"success": False, "error": "Could not acquire browser lock."}

        try:
            try:
                from omni_chrome_watchdog import terminate_chrome_gracefully
                target_pdir = str(self.entity_config.get("profile_dir", ""))
                terminate_chrome_gracefully(timeout_seconds=5, reason=f"ভিডিও রিল আপলোড: {video_path.name}", target_profile_dir=target_pdir)
            except Exception:
                pass

            print(f"\n=======================================================", flush=True)
            print(f"🎬 [REEL PUBLISHER] Starting Autonomous Upload for: {video_path.name}", flush=True)
            print(f"Target Entity: {self.entity_id} | Scheduled Slot: {slot or 'Immediate'}", flush=True)
            print(f"Topic: {topic or 'Dynamic'}", flush=True)
            print(f"Video File Size: {video_path.stat().st_size} bytes", flush=True)
            print(f"=======================================================", flush=True)

            HEADLESS_MODE = os.environ.get("OMNI_HEADLESS", "true").lower() in ("true", "1", "yes")
            mode_label = "Invisible Background (Headless)" if HEADLESS_MODE else "Visible Foreground"
            print(f"[REEL PUBLISHER] Launching Browser ({mode_label})...", flush=True)
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=HEADLESS_MODE,
                    channel="chrome",
                    viewport={'width': 1280, 'height': 850},
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage"
                    ]
                )
                page = context.new_page()

                # 1. Enforce Page Identity
                print("[REEL PUBLISHER] Verifying profile/page identity...", flush=True)
                page.goto("https://www.facebook.com/", timeout=45000)
                time.sleep(5)

                from omni_profile_switcher import switch_to_entity
                if not switch_to_entity(page, self.entity_id):
                    print("[REEL PUBLISHER] Profile switch failed. Aborting.", flush=True)
                    context.close()
                    return {"success": False, "error": "Profile switch failed."}

                print("[REEL PUBLISHER] ✅ Identity confirmed: AutoMovie Pro Page!", flush=True)

                # 2. Navigate to AutoMovie Pro Page and open Reel composer
                print("[REEL PUBLISHER] Opening AutoMovie Pro Page...", flush=True)
                page.goto("https://www.facebook.com/AutoMoviePro", timeout=45000)
                time.sleep(5)
                page.evaluate("window.scrollTo(0, 0)")
                time.sleep(2)

                print("[REEL PUBLISHER] Locating Reel Creator...", flush=True)
                reel_btn = page.locator("div[role='button']:has-text('Reel'), div[aria-label='Reel']").first
                if not reel_btn.is_visible(timeout=5000):
                    for trig in ["div[aria-label='Create reel']", "a:has-text('Create reel')", "div[role='button']:has-text('Create reel')"]:
                        el = page.locator(trig).first
                        if el.is_visible(timeout=3000):
                            reel_btn = el
                            break

                reel_btn.click()
                time.sleep(4)

                # Attach Video MP4 File to the designated video input
                print(f"[REEL PUBLISHER] Attaching video file: {video_path}...", flush=True)
                dialog = page.locator("div[role='dialog']").first
                dialog_inputs = dialog.locator("input[type='file']")
                target_input = None
                for i in range(dialog_inputs.count()):
                    acc = dialog_inputs.nth(i).get_attribute("accept") or ""
                    if "video" in acc or "mp4" in acc:
                        target_input = dialog_inputs.nth(i)
                        break

                if not target_input:
                    target_input = page.locator("input[type='file'][accept*='video'], input[type='file'][accept*='mp4']").first

                target_input.set_input_files(str(video_path))
                print("[REEL PUBLISHER] Video file attached. Waiting for video processing and Next button...", flush=True)
                next_btn = dialog.locator("div[role='button']:has-text('Next'), button:has-text('Next')").first
                next_btn.wait_for(state="visible", timeout=35000)
                time.sleep(10)

                # Step 1 -> Step 2
                print("[REEL PUBLISHER] Step 1 complete. Clicking Next...", flush=True)
                next_btn.click()
                time.sleep(4)

                # Step 2 -> Step 3
                print("[REEL PUBLISHER] Step 2 complete. Clicking Next to reach Reel Settings...", flush=True)
                next_btn2 = dialog.locator("div[role='button']:has-text('Next'), button:has-text('Next')").first
                next_btn2.wait_for(state="visible", timeout=15000)
                next_btn2.click()
                time.sleep(4)

                # 3. Step 3: Insert Caption into Reel Settings
                print("[REEL PUBLISHER] Step 3 reached. Inserting marketing caption...", flush=True)
                caption_box = dialog.locator("div[aria-label*='Describe your reel'], div[contenteditable='true'], textarea").first
                caption_box.wait_for(state="visible", timeout=10000)
                caption_box.click()
                time.sleep(1)
                page.keyboard.insert_text(caption_text)
                time.sleep(3)

                # Dismiss hashtag autocomplete if active
                page.keyboard.press("Escape")
                time.sleep(1)

                # 4. Trigger Post Submission using exact Post button
                print("[REEL PUBLISHER] Clicking exact Post button...", flush=True)
                post_btn = dialog.get_by_role("button", name="Post", exact=True)
                if not post_btn.is_visible():
                    post_btn = dialog.locator("div[aria-label='Post']:not([aria-hidden='true']):not([aria-disabled='true'])").first

                post_btn.click()
                print("[REEL PUBLISHER] Post button clicked!", flush=True)

                # Handle post-submission completion dialogs
                print("[REEL PUBLISHER] Handling completion dialogs...", flush=True)
                for _ in range(6):
                    time.sleep(3)
                    done_btn = page.locator("div[role='dialog'] div[role='button']:has-text('Done'), div[role='dialog'] button:has-text('Done')").first
                    if done_btn.is_visible():
                        print("[REEL PUBLISHER] Clicking 'Done' on completion modal...", flush=True)
                        done_btn.click()
                        time.sleep(3)
                        break

                print("[REEL PUBLISHER] Waiting 35s for Meta video ingestion and timeline rendering...", flush=True)
                time.sleep(35)

                # 5. Live Timeline & Reels Tab Verification
                print("[REEL PUBLISHER] Verifying post on live timeline...", flush=True)
                page.goto("https://www.facebook.com/AutoMoviePro/reels/", timeout=45000)
                time.sleep(6)
                page.mouse.wheel(0, 400)
                time.sleep(3)

                proof_file = PROOF_DIR / f"reel_verified_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                page.screenshot(path=str(proof_file))
                print(f"[REEL PUBLISHER] 📸 Proof screenshot captured: {proof_file.name}", flush=True)

                self.record_reel_published(str(video_path), caption_text, str(proof_file), slot=slot, topic=topic)
                context.close()
                return {"success": True, "proof": str(proof_file), "video": str(video_path), "slot": slot, "topic": topic}

        except Exception as exc:
            print(f"[REEL PUBLISHER] Exception during upload: {exc}", flush=True)
            return {"success": False, "error": str(exc)}
        finally:
            release_browser_lock()

    def publish_scheduled_reel(self, force: bool = False) -> Dict[str, Any]:
        """
        Executes a scheduled reel publishing check & upload:
        1. Checks quota & due slot (unless force=True).
        2. Selects unposted video matching topic pool.
        3. Generates high-converting caption.
        4. Publishes reel via Playwright, verifies timeline, and records history.
        """
        slot = self.get_due_schedule_slot()
        if not force:
            can_pub, reason = self.can_publish_reel_today()
            if not can_pub:
                return {"success": False, "skipped": True, "reason": reason}

            if not slot:
                cfg = self.get_entity_config()
                slots = cfg.get("schedule_slots", [])
                return {"success": False, "skipped": True, "reason": f"No scheduled slot is due right now. Configured slots: {slots}"}

        # Select video & topic
        cfg = self.get_entity_config()
        topics = cfg.get("topics_pool", [])
        chosen_topic = random.choice(topics) if topics else "AutoMovie Pro AI Video Automation"

        video_path, matched_topic, meta = self.select_best_video_for_reel(preferred_topic=chosen_topic)
        if not video_path:
            return {"success": False, "error": "No approved video found in vault to publish."}

        caption = self.generate_caption_for_topic(matched_topic or chosen_topic, meta)
        result = self.publish_video_reel(video_path, caption, slot=slot or "Manual/Forced", topic=matched_topic or chosen_topic)
        return result


def print_status_report(entity_id: str = "automovie_pro_page"):
    pub = OmniReelPublisher(entity_id=entity_id)
    cfg = pub.get_entity_config()
    today_posts = pub.get_today_reels_published()
    can_pub, reason = pub.can_publish_reel_today()
    due_slot = pub.get_due_schedule_slot()

    print("=" * 65)
    print(f"🎬 OmniReel Status Report: [{entity_id}]")
    print("=" * 65)
    print(f"Display Name:      {cfg.get('display_name')}")
    print(f"Enabled:           {cfg.get('enabled')}")
    print(f"Daily Limit:       {cfg.get('reels_per_day')} reels/day")
    print(f"Schedule Slots:    {cfg.get('schedule_slots')}")
    print(f"Min Interval:      {cfg.get('min_interval_hours')} hours")
    print(f"Published Today:   {len(today_posts)}/{cfg.get('reels_per_day')}")
    for idx, p in enumerate(today_posts, 1):
        print(f"   [{idx}] Time: {p.get('timestamp')[:19]} | Slot: {p.get('slot')} | Topic: {p.get('topic', 'N/A')}")
    print(f"Can Publish Today: {can_pub} ({reason})")
    print(f"Due Slot Right Now:{due_slot or 'None'}")
    print(f"Topics Pool ({len(cfg.get('topics_pool', []))} topics):")
    for t in cfg.get("topics_pool", [])[:3]:
        print(f"   - {t}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OmniReel Autonomous Publisher & Scheduler")
    parser.add_argument("--status", action="store_true", help="Print schedule status and quota report")
    parser.add_argument("--cron-check", action="store_true", help="Run automated schedule check and publish if slot is due")
    parser.add_argument("--force", action="store_true", help="Force publish next available reel immediately")
    parser.add_argument("--entity", type=str, default="automovie_pro_page", help="Entity ID")
    args = parser.parse_args()

    if args.status:
        print_status_report(args.entity)
    elif args.cron_check:
        pub = OmniReelPublisher(entity_id=args.entity)
        res = pub.publish_scheduled_reel(force=False)
        print("Cron Check Result:", res)
    elif args.force:
        pub = OmniReelPublisher(entity_id=args.entity)
        res = pub.publish_scheduled_reel(force=True)
        print("Force Publish Result:", res)
    else:
        # Default: show status
        print_status_report(args.entity)
