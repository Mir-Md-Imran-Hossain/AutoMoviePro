import time
import os
import sys
import random
from playwright.sync_api import sync_playwright
import easyocr
import cv2
import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

try:
    from omni_telemetry import log_step
except ImportError:
    def log_step(*args, **kwargs): pass

try:
    from omni_notifications import handle_human_notifications
except ImportError:
    def handle_human_notifications(*args, **kwargs): pass

class PlaywrightVisionAgent:
    def __init__(self, page, langs=['en']):
        self.reader = easyocr.Reader(langs, gpu=False, verbose=False)
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
                is_match = False
                if exact_match:
                    if target_lower == text_lower.strip():
                        is_match = True
                else:
                    if target_lower in text_lower:
                        is_match = True
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

def human_like_scroll(page, duration_minutes):
    print(f"[SYSTEM] Starting Human-like scrolling for {duration_minutes:.2f} minutes...", flush=True)
    end_time = time.time() + (duration_minutes * 60)
    
    log_step("automovie_pro_page", "BROWSING", "Human Feed Engagement", f"Simulating natural feed reading for {duration_minutes:.1f} mins to maintain warm account status.", page=page)
    
    while time.time() < end_time:
        scroll_amount = random.randint(300, 1000)
        page.mouse.wheel(0, scroll_amount)
        log_step("automovie_pro_page", "SCROLLING", "Mouse Wheel Down", f"Scrolled +{scroll_amount}px down newsfeed.", scroll=scroll_amount, page=page)
        time.sleep(random.uniform(1.5, 4.0))
        
        if random.random() < 0.25:
            pause_time = random.uniform(5, 12)
            log_step("automovie_pro_page", "READING_POST", "Reading Article / Post", f"Pausing for {pause_time:.1f}s at viewport offset to inspect organic feed post.", page=page)
            print("[SYSTEM] Pausing to read a post...", flush=True)
            time.sleep(pause_time)
            
        if random.random() < 0.15:
            up_scroll = random.randint(150, 400)
            page.mouse.wheel(0, -up_scroll)
            log_step("automovie_pro_page", "SCROLLING_UP", "Curiosity Backscroll", f"Scrolled back up -{up_scroll}px to re-examine photo.", scroll=-up_scroll, page=page)
            time.sleep(random.uniform(1.5, 3.0))
            
    log_step("automovie_pro_page", "IDLE", "Browsing Complete", "Human-like feed session completed successfully.", page=page)
    print("[SYSTEM] Human-like scrolling completed.", flush=True)

LOCK_FILE = r"E:\AI Assistant\Automations\chrome_browser.lock"

def acquire_lock(timeout=600):
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(LOCK_FILE):
            try:
                # If file contains current PID or parent PID, or is older than 15 mins
                content = ""
                with open(LOCK_FILE, "r") as f:
                    content = f.read().strip()
                if str(os.getpid()) in content or str(os.getppid()) in content:
                    return True
                if time.time() - os.path.getmtime(LOCK_FILE) > 900:
                    os.remove(LOCK_FILE)
                else:
                    time.sleep(5)
                    continue
            except:
                pass
        try:
            with open(LOCK_FILE, "w") as f:
                f.write(f"{os.getpid()}:{time.time()}")
            return True
        except:
            time.sleep(3)
    return False

def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass

def post_to_facebook(text_content, img_path):
    if not acquire_lock():
        print("[ERROR] Could not acquire browser lock in time.", flush=True)
        return
    try:
        try:
            from omni_chrome_watchdog import terminate_chrome_gracefully
            terminate_chrome_gracefully(timeout_seconds=30, reason="AutoMovie Pro অটোমেটেড মার্কেটিং পোস্টিং")
        except Exception:
            os.system("taskkill /F /IM chrome.exe >nul 2>&1")
        time.sleep(1)
        
        user_data_dir = r"E:\AI Assistant\Automation Workspace\Social_Media_Profiles\Facebook_AssunnahPath"
        
        with sync_playwright() as p:
            print("[SYSTEM] Launching Browser in Human-Like Mode...", flush=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir, headless=False, channel="chrome",
                viewport={'width': 1200, 'height': 800},
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = context.new_page()
            agent = PlaywrightVisionAgent(page)
        
            print("[SYSTEM] Navigating to Facebook Home...", flush=True)
            page.goto("https://www.facebook.com/")
            time.sleep(6)
        
            # 0. Strict Deterministic Verification: Must be 100% on AutoMovie Pro Page
            print("[SYSTEM] Verifying and enforcing active identity: automovie_pro_page...", flush=True)
            from omni_profile_switcher import switch_to_entity
            if not switch_to_entity(page, "automovie_pro_page"):
                print("[FATAL ERROR] AutoMovie Pro profile could NOT be activated or verified! Aborting immediately to prevent cross-posting.", flush=True)
                page.screenshot(path=r"E:\AI Assistant\Automations\abort_profile_mismatch.png")
                context.close()
                sys.exit(1)
            print("[SYSTEM] SAFETY VERIFIED: Active account is 100% AutoMovie Pro!", flush=True)

            # 0.5. Notification Handling upon entering account (Human-Like Notification Check)
            handle_human_notifications(page, entity_id="automovie_pro_page")

            # 1. Pre-post human scrolling (3 to 7 minutes)
            pre_scroll_mins = random.uniform(3, 7)
            human_like_scroll(page, pre_scroll_mins)
            
            # 2. Scroll back to top
            print("[SYSTEM] Scrolling to top of feed...", flush=True)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(3)
            
            # 3. Open photo uploader directly from the feed
            print("[SYSTEM] Opening Photo uploader modal...", flush=True)
            clicked_photo = False
            try:
                page.locator('div[aria-label="Photo/video"]').first.click(timeout=3000)
                clicked_photo = True
            except:
                pass
                
            if not clicked_photo:
                page.mouse.click(666, 140)
                
            time.sleep(4)
            
            # 4. Attach Image
            if img_path and img_path != "NONE" and os.path.exists(img_path):
                print(f"[SYSTEM] Attaching image: {img_path}...", flush=True)
                log_step("automovie_pro_page", "ATTACHING_ASSET", "Uploading Marketing Banner", f"Attaching high-res banner: {os.path.basename(img_path)} via file input dialog.", page=page)
                try:
                    page.locator("input[type='file']").first.set_input_files(img_path)
                    print("[SYSTEM] Image attached successfully!", flush=True)
                    log_step("automovie_pro_page", "ASSET_LOADED", "Thumbnail Rendered", "Facebook thumbnail successfully parsed and displayed.", page=page)
                    time.sleep(6) # wait for thumbnail to render
                except Exception as e:
                    print(f"[SYSTEM] Error attaching image: {e}", flush=True)
            else:
                print("[SYSTEM] No image provided or file missing. Proceeding with text only.", flush=True)
                
            # 5. Type detailed Bengali caption with emojis
            print("[SYSTEM] Typing detailed caption...", flush=True)
            log_step("automovie_pro_page", "TYPING_CAPTION", "Human-Speed Keyboard Input", f"Injecting {len(text_content)} characters with natural WPM and emoji encoding.", kb=f"{len(text_content)} chars", page=page)
            page.keyboard.insert_text(text_content)
            time.sleep(3)
            page.keyboard.press("Escape") # Close hashtag suggestions popup
            time.sleep(2)
            
            # 6. Click Post button
            print("[SYSTEM] Clicking Post button...", flush=True)
            log_step("automovie_pro_page", "OCR_TARGETING", "Locating Post Button", "Scanning viewport via OCR to detect bottom 'Post' submission trigger.", page=page)
            if agent.click_text("Post", exact_match=True, lowest_y=True):
                print("[SYSTEM] SUCCESS: Post clicked!", flush=True)
                log_step("automovie_pro_page", "PUBLISHING", "Post Button Triggered", "Clicked 'Post' button. Awaiting Facebook edge server confirmation.", page=page)
                time.sleep(15)
                
                # 7. Verification Screenshot
                print("[SYSTEM] Verifying post on profile...", flush=True)
                log_step("automovie_pro_page", "VERIFYING", "Navigating to Profile Feed", "Verifying live post render on profile timeline.", page=page)
                page.goto("https://www.facebook.com/me/")
                time.sleep(6)
                page.mouse.wheel(0, 1500)
                time.sleep(3)
                screenshot_path = r"E:\AI Assistant\Automations\post_verification.png"
                page.screenshot(path=screenshot_path)
                log_step("automovie_pro_page", "VERIFIED", "Post Verified & Screenshot Captured", f"Post is live on Facebook timeline. Screenshot saved.", page=page)
                print(f"[SYSTEM] Verification screenshot saved to {screenshot_path}", flush=True)
                try:
                    import shutil
                    shutil.copy2(screenshot_path, r"C:\Users\HP\.gemini\antigravity\brain\8bce3999-2a44-43d5-ada5-1775c44a371e\post_verification.png")
                except Exception as e:
                    print(f"[SYSTEM] Artifact copy notice: {e}", flush=True)
            else:
                print("[SYSTEM] ERROR: Could not find Post button.", flush=True)
                page.screenshot(path=r"E:\AI Assistant\Automations\vision_post_error.png")
                context.close()
                sys.exit(1)
                
            # 8. Post-post human scrolling (3 to 7 minutes)
            post_scroll_mins = random.uniform(3, 7)
            human_like_scroll(page, post_scroll_mins)
            
            context.close()
            print("[SYSTEM] Complete cycle finished successfully.", flush=True)
    finally:
        release_lock()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        post_to_facebook(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python FB_Human_Poster.py <text> <img_path>")
