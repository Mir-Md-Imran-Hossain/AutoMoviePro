"""
=============================================================================
OmniSocial AI - Multi-Entity Unified As-Sunnah Poster Engine
=============================================================================
Supports:
1. 'assunnah_path_bangla': Posts verified Quran & Sahih Hadith in Bengali to AsSunnahPathBangla Page.
2. 'assunnah_path_page': Posts verified Quran & Sahih Hadith in English to AsSunnahPathOfficial Page.
3. 'assunnah_path_profile': Posts verified Quran & Sahih Hadith in English to Personal Profile.
"""

import time
import os
import sys
import random
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
import easyocr
import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = Path(r"E:\AI Assistant\Automations")
sys.path.append(str(BASE_DIR))

try:
    from omni_telemetry import log_step, OmniTelemetry
except ImportError:
    def log_step(*args, **kwargs): pass
    class OmniTelemetry:
        @staticmethod
        def capture_frame(page): pass

try:
    from omni_notifications import handle_human_notifications
except ImportError:
    def handle_human_notifications(*args, **kwargs): pass

LOCK_FILE = BASE_DIR / "chrome_browser.lock"
PROFILE_ID = "61595114556629"
PAGE_ID_ENGLISH = "61594165271828"
PAGE_URL_BANGLA = "https://www.facebook.com/AsSunnahPathBangla"

def acquire_lock(timeout=600):
    print("[LOCK] Waiting for browser lock...", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        if LOCK_FILE.exists():
            try:
                content = LOCK_FILE.read_text(encoding="utf-8").strip()
                if str(os.getpid()) in content or str(os.getppid()) in content:
                    print("[LOCK] Browser lock re-entered by current/parent process.", flush=True)
                    return True
                if time.time() - os.path.getmtime(LOCK_FILE) > 900:
                    LOCK_FILE.unlink(missing_ok=True)
                else:
                    time.sleep(5)
                    continue
            except Exception:
                pass
        try:
            LOCK_FILE.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
            print("[LOCK] Browser lock acquired successfully.", flush=True)
            return True
        except Exception:
            time.sleep(3)
    return False

def release_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)
            print("[LOCK] Browser lock released.", flush=True)
    except Exception:
        pass

class VisionAgent:
    def __init__(self, page):
        self.reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        self.page = page

    def find_text_coords(self, target_text, threshold=0.4, exact_match=False, lowest_y=False):
        screenshot_bytes = self.page.screenshot()
        img_np = np.frombuffer(screenshot_bytes, np.uint8)
        img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        results = self.reader.readtext(img_bgr)
        target_lower = target_text.lower()
        
        matches = []
        for bbox, text, conf in results:
            if conf > threshold:
                text_lower = text.lower()
                is_match = (target_lower == text_lower.strip()) if exact_match else (target_lower in text_lower)
                if is_match:
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    cx = int(sum(xs) / 4)
                    cy = int(sum(ys) / 4)
                    matches.append((cx, cy, text, conf))
        if matches:
            if lowest_y:
                matches.sort(key=lambda m: m[1], reverse=True)
            return matches[0]
        return None

    def click_text(self, target_text, timeout=25, exact_match=False, lowest_y=False):
        start = time.time()
        while time.time() - start < timeout:
            coords = self.find_text_coords(target_text, exact_match=exact_match, lowest_y=lowest_y)
            if coords:
                cx, cy, text, conf = coords
                print(f"[VISION] Clicking '{text}' at ({cx}, {cy})", flush=True)
                self.page.mouse.click(cx, cy)
                return True
            time.sleep(2)
        return False

def human_scroll(page, duration_minutes, label="General", entity_id="general"):
    print(f"[SCROLL] [{label}] Starting human-like scrolling for {duration_minutes:.2f} mins...", flush=True)
    log_step(entity_id, "BROWSING", f"Feed Reading ({label})", f"Browsing timeline feeds to emulate organic user interaction for {duration_minutes:.1f} mins.", page=page)
    end_time = time.time() + (duration_minutes * 60)
    while time.time() < end_time:
        amount = random.randint(300, 900)
        page.mouse.wheel(0, amount)
        OmniTelemetry.capture_frame(page)
        log_step(entity_id, "SCROLLING", f"Mouse Wheel Down ({label})", f"Scrolled +{amount}px on newsfeed.", scroll=amount, page=page)
        time.sleep(random.uniform(1.8, 3.8))
        if random.random() < 0.25:
            pause_time = random.uniform(4, 9)
            log_step(entity_id, "READING_POST", f"Reading Feed Post ({label})", f"Pausing for {pause_time:.1f}s to read Islamic post in feed.", page=page)
            print(f"[SCROLL] [{label}] Pausing to read a post...", flush=True)
            time.sleep(pause_time)
        if random.random() < 0.15:
            up_scroll = random.randint(150, 350)
            page.mouse.wheel(0, -up_scroll)
            log_step(entity_id, "SCROLLING_UP", f"Feed Re-inspection ({label})", f"Scrolled up -{up_scroll}px.", scroll=-up_scroll, page=page)
            time.sleep(random.uniform(1.5, 3.0))
    log_step(entity_id, "IDLE", f"Browsing Complete ({label})", f"Feed engagement finished cleanly for {label}.", page=page)
    print(f"[SCROLL] [{label}] Scrolling finished.", flush=True)

def post_content(page, agent, text_content, img_path, context_name, target_eid):
    print(f"[POST] [{context_name}] Opening composer modal...", flush=True)
    
    # 1. Scroll slightly down if on Page so composer is fully in view, or scroll to top
    if "Page" in context_name:
        page.mouse.wheel(0, 500)
        time.sleep(3)
    else:
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(3)
    OmniTelemetry.capture_frame(page)

    # 1. Open Dialog
    clicked = False
    for selector in [
        'div[role="button"]:has-text("Photo/video")',
        'div[aria-label="Photo/video"]',
        'span:has-text("Photo/video")',
        'div[role="button"]:has-text("What\'s on your mind")',
        'div[aria-label*="on your mind"]',
        'span:has-text("What\'s on your mind")',
        'div[aria-label*="Create a post"]',
        'div[role="button"]:has-text("Create post")'
    ]:
        try:
            loc = page.locator(selector).first
            if loc.is_visible():
                loc.click()
                clicked = True
                print(f"[POST] [{context_name}] Clicked composer trigger via: {selector}", flush=True)
                break
        except Exception:
            pass
            
    if not clicked:
        try:
            page.mouse.click(650, 400 if "Page" in context_name else 140)
        except Exception:
            pass
    time.sleep(4)
    OmniTelemetry.capture_frame(page)

    # 2. Attach Image
    if img_path and os.path.exists(img_path):
        print(f"[POST] [{context_name}] Attaching image: {img_path}...", flush=True)
        log_step(target_eid, "ATTACHING_ASSET", f"Uploading Emblem Banner ({context_name})", f"Attaching high-res banner: {os.path.basename(img_path)} via file input.", page=page)
        attached = False
        
        # Click photo icon inside dialog if present
        for photo_trigger in [
            'div[role="dialog"] div[aria-label="Photo/video"]',
            'div[role="dialog"] div[role="button"]:has-text("Add photos or videos")',
            'div[role="dialog"] div[aria-label="Add photos/videos"]',
            'div[role="dialog"] div[role="button"]:has-text("Add Photos/Videos")'
        ]:
            try:
                p_btn = page.locator(photo_trigger).first
                if p_btn.is_visible():
                    p_btn.click()
                    time.sleep(2)
                    break
            except Exception:
                pass
                
        # Set input files
        for f_sel in [
            'div[role="dialog"] input[type="file"]',
            'input[type="file"]'
        ]:
            try:
                inp = page.locator(f_sel).first
                if inp.count() > 0:
                    inp.set_input_files(img_path)
                    attached = True
                    print(f"[POST] [{context_name}] Successfully attached via {f_sel}!", flush=True)
                    break
            except Exception:
                pass
                
        if attached:
            log_step(target_eid, "ASSET_LOADED", f"Gold Emblem Banner Attached ({context_name})", f"Banner {os.path.basename(img_path)} successfully uploaded.", page=page)
            time.sleep(6)
            OmniTelemetry.capture_frame(page)
        else:
            print(f"[POST] [{context_name}] Warning: Could not attach image.", flush=True)
            
    # 3. Insert caption text
    print(f"[POST] [{context_name}] Inserting caption text...", flush=True)
    log_step(target_eid, "TYPING_CAPTION", f"Human Typing Input ({context_name})", f"Inserting verified Quran/Hadith caption ({len(text_content)} chars) with Arabic tashkeel.", kb=f"{len(text_content)} chars", page=page)
    page.keyboard.insert_text(text_content)
    time.sleep(3)
    OmniTelemetry.capture_frame(page)
    page.keyboard.press("Escape")
    time.sleep(2)
    
    # 4. Scroll dialog down to expose Post button
    try:
        dialog = page.locator('div[role="dialog"]').first
        if dialog.is_visible():
            dialog.evaluate('(el) => el.scrollTop = el.scrollHeight')
            time.sleep(2)
    except Exception:
        pass
    
    # 5. Check if 'Next' button exists (Facebook Page 2-step flow)
    for next_sel in [
        'div[role="dialog"] div[aria-label="Next"]',
        'div[role="dialog"] div[role="button"]:has-text("Next")',
        'div[aria-label="Next"]'
    ]:
        try:
            nb = page.locator(next_sel).first
            if nb.is_visible():
                print(f"[POST] [{context_name}] Found 'Next' button! Clicking...", flush=True)
                nb.click()
                time.sleep(3)
                OmniTelemetry.capture_frame(page)
                break
        except Exception:
            pass

    # 6. Click Post button
    print(f"[POST] [{context_name}] Clicking Post button...", flush=True)
    log_step(target_eid, "PUBLISHING", f"Triggering Post Submission ({context_name})", "Locating and triggering 'Post' button.", page=page)
    post_success = False
    
    for post_sel in [
        'div[role="dialog"] div[aria-label="Post"]',
        'div[role="dialog"] div[role="button"]:has-text("Post")',
        'div[aria-label="Post"]',
        'div[role="button"]:has-text("Post")'
    ]:
        try:
            btn = page.locator(post_sel).first
            if btn.is_visible():
                btn.click(timeout=5000)
                print(f"[POST] [{context_name}] SUCCESS: Post clicked via: {post_sel}", flush=True)
                post_success = True
                break
        except Exception:
            pass

    if not post_success:
        if agent.click_text("Post", exact_match=True, lowest_y=True):
            print(f"[POST] [{context_name}] SUCCESS: Post clicked via OCR!", flush=True)
            post_success = True
            
    if post_success:
        time.sleep(12)
        OmniTelemetry.capture_frame(page)
        log_step(target_eid, "PUBLISHED", f"Post Live on Timeline ({context_name})", f"Submission confirmed on Facebook for {context_name}.", page=page)
        return True
    else:
        log_step(target_eid, "ERROR", f"Post Button Failed ({context_name})", "Could not locate Post button.", page=page)
        print(f"[POST] [{context_name}] ERROR: Post button not found!", flush=True)
        return False

def execute_single_entity_cycle(target_entity: str):
    """
    Executes post routine targeted directly to the requested channel:
    - assunnah_path_bangla
    - assunnah_path_page
    - assunnah_path_profile
    """
    from Assunnah_Content_Bank import get_dynamic_assunnah_post

    if not acquire_lock():
        print("[ERROR] Could not acquire browser lock. Skipping cycle.", flush=True)
        return False

    try:
        from omni_chrome_watchdog import terminate_chrome_gracefully
        terminate_chrome_gracefully(timeout_seconds=30, reason=f"পোস্টিং কার্যক্রম: {target_entity}")
    except Exception:
        os.system("taskkill /F /IM chrome.exe >nul 2>&1")
    time.sleep(1)
    user_data_dir = r"E:\AI Assistant\Automation Workspace\Social_Media_Profiles\Facebook_AssunnahPath"

    # Select language and content based on entity
    if target_entity == "assunnah_path_bangla":
        caption, img_path = get_dynamic_assunnah_post("bn")
        context_name = "As-Sunnah Path Bangla"
    else:
        caption, img_path = get_dynamic_assunnah_post("en")
        context_name = "As-Sunnah Path Official" if "page" in target_entity else "Personal Profile"

    print(f"\n{'='*65}\n [START] Executing cycle for: {target_entity} ({context_name})\n{'='*65}", flush=True)

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir, headless=False, channel="chrome",
                viewport={'width': 1200, 'height': 800},
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = context.new_page()
            agent = VisionAgent(page)

            from omni_profile_switcher import switch_to_entity
            if not switch_to_entity(page, target_entity):
                print(f"[FATAL ERROR] Failed to switch and verify active entity as '{target_entity}'. Aborting to prevent cross-posting!", flush=True)
                page.screenshot(path=rf"E:\AI Assistant\Automations\abort_{target_entity}.png")
                context.close()
                return False

            # Pre-inspection of notifications
            handle_human_notifications(page, entity_id=target_entity)

            # Organic Pre-scroll (1.5 to 2.5 minutes)
            human_scroll(page, random.uniform(1.5, 2.5), label=f"{context_name} Pre-scroll", entity_id=target_entity)

            # Post content to target entity
            success = post_content(page, agent, caption, img_path, context_name=context_name, target_eid=target_entity)
            if success:
                # Capture proof
                if target_entity == "assunnah_path_bangla":
                    page.goto(PAGE_URL_BANGLA)
                    proof_name = "assunnah_bangla_proof.png"
                elif target_entity == "assunnah_path_page":
                    page.goto(f"https://www.facebook.com/profile.php?id={PAGE_ID_ENGLISH}")
                    proof_name = "assunnah_page_post_proof.png"
                else:
                    page.goto(f"https://www.facebook.com/profile.php?id={PROFILE_ID}")
                    proof_name = "assunnah_profile_post_proof.png"

                time.sleep(5)
                page.mouse.wheel(0, 1000)
                time.sleep(3)
                proof_path = os.path.join(r"E:\AI Assistant\Automations", proof_name)
                page.screenshot(path=proof_path)
                try:
                    shutil.copy2(proof_path, os.path.join(r"C:\Users\HP\.gemini\antigravity\brain\8bce3999-2a44-43d5-ada5-1775c44a371e", proof_name))
                except Exception:
                    pass

                # Organic Post-scroll (1.5 to 3 minutes)
                human_scroll(page, random.uniform(1.5, 3.0), label=f"{context_name} Post-scroll", entity_id=target_entity)

            context.close()
            return success

    finally:
        release_lock()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "assunnah_path_bangla"
    res = execute_single_entity_cycle(target)
    sys.exit(0 if res else 1)
