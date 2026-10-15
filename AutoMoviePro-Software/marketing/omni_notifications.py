import time
import random
try:
    from omni_telemetry import log_step
except ImportError:
    def log_step(*args, **kwargs): pass

def handle_human_notifications(page, entity_id="general"):
    """
    Simulates human notification interaction upon entering the account:
    1. Checks the top-bar notification bell.
    2. Opens notifications dropdown or visits /notifications/.
    3. Reads and inspects the latest notifications.
    4. If there's an actionable notification (e.g. comment/mention/react/alert), opens it organically.
    5. Returns back to feed ready for normal operations.
    """
    print(f"[NOTIFICATIONS] [{entity_id}] Checking account notifications like a real human...", flush=True)
    log_step(entity_id, "NOTIFICATIONS_CHECK", "Checking Notifications Bell", "Inspecting notification badge and latest alerts upon entering account.")
    
    try:
        # Check if bell icon exists
        bell_selectors = [
            'div[aria-label="Notifications"]',
            'div[role="button"][aria-label*="Notifications"]',
            'a[aria-label*="Notifications"]'
        ]
        
        bell = None
        for sel in bell_selectors:
            loc = page.locator(sel).first
            if loc.is_visible():
                bell = loc
                break
                
        if bell:
            # Random slight hover delay
            bell.hover()
            time.sleep(random.uniform(0.8, 1.8))
            bell.click()
            print(f"[NOTIFICATIONS] [{entity_id}] Clicked notification bell.", flush=True)
            time.sleep(random.uniform(2.5, 4.0))
            
            # Read notifications from dropdown
            items = page.locator('div[role="dialog"] a[role="link"], div[aria-label="Notifications"] a[role="link"]').all()
            notif_count = len(items)
            print(f"[NOTIFICATIONS] [{entity_id}] Found {notif_count} notification items in popup.", flush=True)
            
            if notif_count > 0:
                # Human inspects top 2-3 notifications
                sample_count = min(3, notif_count)
                for i in range(sample_count):
                    try:
                        txt = items[i].inner_text().strip().replace('\n', ' -- ')
                        print(f"  [Notif #{i+1}] {txt[:90]}", flush=True)
                        log_step(entity_id, "READING_NOTIF", f"Reading Alert #{i+1}", f"Examined notification: {txt[:70]}")
                    except Exception:
                        pass
                    time.sleep(random.uniform(1.2, 2.5))
                    
                # 30% chance to organically click into the top notification if it looks relevant
                if random.random() < 0.35 and notif_count > 0:
                    try:
                        print(f"[NOTIFICATIONS] [{entity_id}] Organically clicking top notification to inspect post...", flush=True)
                        log_step(entity_id, "CLICKING_NOTIF", "Inspecting Notification Item", "Navigating to referenced post/activity.")
                        items[0].click()
                        time.sleep(random.uniform(4.0, 7.0))
                        # Scroll slightly to read
                        page.mouse.wheel(0, random.randint(200, 500))
                        time.sleep(random.uniform(2.0, 4.0))
                    except Exception as ce:
                        print(f"[NOTIFICATIONS] Notice clicking notif item: {ce}", flush=True)
            else:
                # Press escape to dismiss empty dropdown
                page.keyboard.press("Escape")
                time.sleep(1)
        else:
            # Fallback: human directly navigates to /notifications/ if bell not immediately in viewport
            print(f"[NOTIFICATIONS] [{entity_id}] Navigating to /notifications/ tab...", flush=True)
            page.goto("https://www.facebook.com/notifications/", timeout=20000)
            time.sleep(random.uniform(3.0, 5.0))
            log_step(entity_id, "READING_NOTIF", "Reading Notifications Hub", "Reviewed all recent alerts.")
            
    except Exception as e:
        print(f"[NOTIFICATIONS] [{entity_id}] Notice during notification check: {e}", flush=True)
        
    # Crucial Fix: Always navigate back to Home Feed so we never stay on notification pages or other profiles
    try:
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=25000)
        time.sleep(3)
    except Exception:
        pass

    print(f"[NOTIFICATIONS] [{entity_id}] Notification handling complete. Moving to feed.", flush=True)
    log_step(entity_id, "NOTIFICATIONS_DONE", "Notifications Handled", "Completed organic review of alerts.", page=page)
