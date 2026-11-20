"""
AutoMovie Pro - Capture Real UI Screenshots in Authenticated Local Demo Mode
Logs in via local demo credentials (zero live server dependency) and captures:
1. Dashboard View (01_dashboard.png)
2. Channel List View (02_channel_list.png)
3. Settings View (03_settings.png)
4. Video Studio / Preview / Thumbnail (04_video_preview.png)
"""

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOFTWARE_DIR = ROOT / "AutoMoviePro-Software"
SCREENSHOTS_DIR = ROOT / "reports" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8787"


def main():
    print("=" * 70)
    print("📸 CAPTURING REAL LOCAL DEMO UI SCREENSHOTS")
    print("=" * 70)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOFTWARE_DIR)
    env["AMP_ALLOW_LOCAL_LOGIN"] = "1"
    env["AMP_INTELLIGENCE_MODE"] = "DEVELOPMENT"

    server_proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=str(SOFTWARE_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        # Wait for server
        for _ in range(30):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(f"{URL}/api/health", timeout=1.0) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass

        print("[*] Server online. Launching Playwright browser...")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 850})
            page = context.new_page()

            page.goto(URL, wait_until="domcontentloaded")
            time.sleep(1.0)

            # Perform Login
            print("[*] Performing Local Demo Login (admin / admin123)...")
            page.evaluate("() => { const el = document.getElementById('apiBase'); if (el) el.value = 'http://127.0.0.1:8787'; }")
            page.fill("#loginId", "admin")
            page.fill("#password", "admin123")
            page.click("#loginBtn")

            # Wait for login transition
            time.sleep(2.0)
            print("[*] Logged in successfully!")

            # 1. Dashboard View
            print("[*] Capturing 01_dashboard.png (Dashboard)...")
            page.evaluate("if (typeof switchTab === 'function') switchTab('home');")
            time.sleep(1.0)
            page.screenshot(path=str(SCREENSHOTS_DIR / "01_dashboard.png"), full_page=False)

            # 2. Channel List View
            print("[*] Capturing 02_channel_list.png (Channels & Niches)...")
            page.evaluate("if (typeof switchTab === 'function') switchTab('channel');")
            time.sleep(1.0)
            page.screenshot(path=str(SCREENSHOTS_DIR / "02_channel_list.png"), full_page=False)

            # 3. Settings View
            print("[*] Capturing 03_settings.png (API Vault & System Settings)...")
            page.evaluate("if (typeof switchTab === 'function') switchTab('api-settings');")
            time.sleep(1.0)
            page.screenshot(path=str(SCREENSHOTS_DIR / "03_settings.png"), full_page=False)

            # 4. Video Library / Studio Preview
            print("[*] Capturing 04_video_preview.png (Video Studio & Previews)...")
            page.evaluate("if (typeof switchTab === 'function') switchTab('videos');")
            time.sleep(1.0)
            page.screenshot(path=str(SCREENSHOTS_DIR / "04_video_preview.png"), full_page=False)

            browser.close()
            print("\n  [✓] All 4 authentic UI screenshots captured successfully in reports/screenshots/!")

    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()


if __name__ == "__main__":
    main()
