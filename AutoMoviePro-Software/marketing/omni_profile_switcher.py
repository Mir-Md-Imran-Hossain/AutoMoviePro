"""
=============================================================================
OmniSocial AI - Universal Deterministic Profile & Page Switcher
=============================================================================
Guarantees 100% entity isolation and prevents accidental cross-posting across:
1. automovie_pro_page
2. assunnah_path_bangla
3. assunnah_path_page (English Page)
4. assunnah_path_profile (Personal Profile)
=============================================================================
"""

import time
import os
import sys
from typing import Tuple

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PROFILE_ID = "61595114556629"
PAGE_ID_ENGLISH = "61594165271828"
PAGE_URL_BANGLA = "https://www.facebook.com/AsSunnahPathBangla"
PAGE_URL_AUTOMOVIE = "https://www.facebook.com/AutoMoviePro"

def check_active_entity(page) -> str:
    """
    Inspects the currently active actor on Facebook.
    Returns: 'automovie_pro_page' | 'assunnah_path_bangla' | 'assunnah_path_page' | 'assunnah_path_profile' | 'unknown'
    """
    try:
        page.goto("https://www.facebook.com/me/", timeout=30000)
        time.sleep(5)
    except Exception:
        pass

    url = page.url.lower()
    title = page.title()
    body_snippet = ""
    try:
        body_snippet = page.locator("body").inner_text()[:1500]
    except Exception:
        pass

    # 1. AutoMovie Pro Page
    if "automovie" in url or "automovie" in title.lower():
        return "automovie_pro_page"

    # 2. As-Sunnah Path Bangla Page
    if "assunnahpathbangla" in url or "bangla" in title.lower() or "as sunnah path bangla" in body_snippet.lower():
        if "bangla" in url or "bangla" in title.lower():
            return "assunnah_path_bangla"

    # 3. As-Sunnah Path English Page
    if PAGE_ID_ENGLISH in url or "assunnahpathofficial" in url:
        return "assunnah_path_page"

    # 4. Check whether we are on a Page vs Personal Profile
    is_manage_page = "manage page" in body_snippet.lower() or "professional dashboard" in body_snippet.lower()
    
    if is_manage_page:
        # We are on a page. If it says Bangla in the header, it's Bangla page. Otherwise English page.
        try:
            h1 = page.locator("h1").first.inner_text().lower()
            if "bangla" in h1:
                return "assunnah_path_bangla"
            elif "automovie" in h1:
                return "automovie_pro_page"
            else:
                return "assunnah_path_page"
        except Exception:
            return "assunnah_path_page"
    else:
        # We are on the Personal Profile
        if PROFILE_ID in url or "assunnahpathprofile" in url or "as sunnah path" in title.lower() or "what's on your mind" in body_snippet.lower():
            return "assunnah_path_profile"

    return "unknown"


def switch_to_entity(page, target_entity: str) -> bool:
    """
    Deterministically switches to the specified target entity and asserts active identity.
    """
    print(f"\n[SWITCHER] Requesting switch to target: {target_entity}", flush=True)

    # 1. Pre-check: Are we already active?
    current = check_active_entity(page)
    print(f"[SWITCHER] Current active entity identified as: {current}", flush=True)
    if current == target_entity:
        print(f"[SWITCHER] ALREADY on target entity '{target_entity}'. No switch required [OK]", flush=True)
        return True

    # 2. Strategy A: Direct Navigation & 'Switch' banner button
    if target_entity == "automovie_pro_page":
        dest_url = PAGE_URL_AUTOMOVIE
    elif target_entity == "assunnah_path_bangla":
        dest_url = PAGE_URL_BANGLA
    elif target_entity == "assunnah_path_page":
        dest_url = f"https://www.facebook.com/profile.php?id={PAGE_ID_ENGLISH}"
    else:
        dest_url = f"https://www.facebook.com/profile.php?id={PROFILE_ID}"

    print(f"[SWITCHER] Navigating to target destination: {dest_url}", flush=True)
    try:
        page.goto(dest_url, timeout=35000)
        time.sleep(5)
    except Exception as e:
        print(f"[SWITCHER] Navigation warning: {e}", flush=True)

    # Check for direct switch button on page
    switch_clicked = False
    for sel in [
        'div[role="button"]:has-text("Switch Now")',
        'div[role="button"]:has-text("Switch")',
        'div[aria-label="Switch Now"]',
        'div[aria-label="Switch"]'
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible():
                print(f"[SWITCHER] Found direct switch trigger: {sel}. Clicking...", flush=True)
                btn.click()
                time.sleep(3)
                dlg_btn = page.locator('div[role="dialog"] div[role="button"]:has-text("Switch")').first
                if dlg_btn.is_visible():
                    dlg_btn.click()
                time.sleep(15)
                switch_clicked = True
                break
        except Exception:
            pass

    # 3. Strategy B: Global Account Switcher Menu
    if not switch_clicked or check_active_entity(page) != target_entity:
        print("[SWITCHER] Using top-level profile switcher menu...", flush=True)
        try:
            page.goto("https://www.facebook.com/", timeout=30000)
            time.sleep(5)

            # Click top-right avatar
            profile_btn = page.locator('div[aria-label="Your profile"]').first
            profile_btn.click()
            time.sleep(3)

            # Click 'See all profiles'
            for sa_sel in ['span:has-text("See all profiles")', 'div[role="button"]:has-text("See all profiles")', 'div:has-text("See all profiles")']:
                try:
                    sa = page.locator(sa_sel).first
                    if sa.is_visible():
                        sa.click()
                        time.sleep(3)
                        break
                except Exception:
                    pass

            dlg = page.locator('div[role="dialog"]').first
            if dlg.is_visible():
                buttons = dlg.locator('div[role="button"]').all()
                for b in buttons:
                    txt = b.inner_text().strip()
                    if target_entity == "automovie_pro_page" and "AutoMovie Pro" in txt:
                        print("[SWITCHER] Clicking AutoMovie Pro in switcher dialog...", flush=True)
                        b.click()
                        time.sleep(15)
                        switch_clicked = True
                        break
                    elif target_entity == "assunnah_path_bangla" and "Bangla" in txt:
                        print("[SWITCHER] Clicking As Sunnah Path Bangla in switcher dialog...", flush=True)
                        b.click()
                        time.sleep(15)
                        switch_clicked = True
                        break
                    elif target_entity == "assunnah_path_page" and "notifications" in txt.lower():
                        # English page has notifications
                        print("[SWITCHER] Clicking As Sunnah Path Page in switcher dialog...", flush=True)
                        b.click()
                        time.sleep(15)
                        switch_clicked = True
                        break
                    elif target_entity == "assunnah_path_profile" and "As Sunnah Path" in txt and "notifications" not in txt.lower() and "bangla" not in txt.lower():
                        print("[SWITCHER] Clicking As Sunnah Path Personal Profile in switcher dialog...", flush=True)
                        b.click()
                        time.sleep(15)
                        switch_clicked = True
                        break
        except Exception as e_dlg:
            print(f"[SWITCHER] Account switcher dialog error: {e_dlg}", flush=True)

    # 4. FINAL ASSERTION & VERIFICATION
    final_active = check_active_entity(page)
    print(f"[SWITCHER] Final active actor verified as: {final_active}", flush=True)
    if final_active == target_entity:
        print(f"[SWITCHER] SUCCESS: Successfully active as '{target_entity}'! [OK]\n", flush=True)
        return True
    else:
        print(f"\n[FATAL SWITCHER ERROR] Target was '{target_entity}', but active identity is '{final_active}'!", flush=True)
        print("[FATAL SWITCHER ERROR] ABORTING EXECUTION TO PREVENT CROSS-POSTING ANOMALY!\n", flush=True)
        try:
            page.screenshot(path=rf"E:\AI Assistant\Automations\abort_switch_mismatch_{target_entity}.png")
        except Exception:
            pass
        return False
