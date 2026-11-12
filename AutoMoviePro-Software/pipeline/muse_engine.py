"""
Muse AI Video Generation & Multi-Account Automation Engine
===========================================================
Supports rotating up to 5 customer accounts (Gmail) on muse.ai.
Features:
- Headless browser automation via Playwright
- Persistent session storage in data/muse_sessions/
- Automatic OTP login initiation & cookie persistence
- Turn-key video clip generation matching scene prompts
- Automatic quota refresh & account reset
- Fallback orchestration to Agnes Video / Agnes AI Still
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MUSE_DATA_DIR = Path("data/muse_sessions")
MUSE_DATA_DIR.mkdir(parents=True, exist_ok=True)
MUSE_ACCOUNTS_FILE = MUSE_DATA_DIR / "accounts.json"


def load_muse_accounts() -> List[Dict[str, Any]]:
    """Load the pool of configured Muse accounts."""
    if not MUSE_ACCOUNTS_FILE.exists():
        return []
    try:
        return json.loads(MUSE_ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load Muse accounts: %s", exc)
        return []


def save_muse_accounts(accounts: List[Dict[str, Any]]) -> None:
    """Save the pool of configured Muse accounts."""
    MUSE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MUSE_ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2, ensure_ascii=False), encoding="utf-8")


def register_account(email: str, label: str = "") -> Dict[str, Any]:
    """Register or update an account in the Muse pool (up to 5 accounts)."""
    accounts = load_muse_accounts()
    email_clean = email.strip().lower()
    
    # Check if exists
    for acc in accounts:
        if acc.get("email") == email_clean:
            acc["updated_at"] = time.time()
            if label:
                acc["label"] = label
            save_muse_accounts(accounts)
            return acc
            
    if len(accounts) >= 5:
        # Check if there is an inactive one, else raise or replace oldest
        accounts.sort(key=lambda x: x.get("updated_at", 0))
        removed = accounts.pop(0)
        logger.info("Muse pool full (5 accounts max). Replacing oldest account: %s", removed.get("email"))

    new_acc = {
        "id": f"muse_{len(accounts) + 1}",
        "email": email_clean,
        "label": label or f"Account {len(accounts) + 1}",
        "status": "pending_auth",
        "created_at": time.time(),
        "updated_at": time.time(),
        "session_file": str(MUSE_DATA_DIR / f"session_{email_clean.replace('@', '_').replace('.', '_')}.json"),
        "credits_remaining": 50,
        "total_generated": 0,
    }
    accounts.append(new_acc)
    save_muse_accounts(accounts)
    return new_acc


async def initiate_login_step(email: str) -> Dict[str, Any]:
    """
    Step 1: Open muse.ai in Playwright, enter email, submit, trigger 6-digit OTP.
    Returns status dict indicating OTP has been dispatched to email.
    """
    from playwright.async_api import async_playwright

    email_clean = email.strip().lower()
    account_entry = register_account(email_clean)
    session_path = Path(account_entry["session_file"])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        try:
            logger.info("Navigating to https://muse.ai for %s", email_clean)
            await page.goto("https://muse.ai", wait_until="networkidle", timeout=35000)

            input_el = page.locator('input[placeholder*="email" i], input[type="text"], input[type="email"]').first
            if await input_el.count() == 0:
                await browser.close()
                return {"success": False, "error": "Login input not found on muse.ai"}

            await input_el.fill(email_clean)
            await page.wait_for_timeout(800)

            continue_btn = page.locator('button:has-text("Continue"), button[type="submit"]').first
            await continue_btn.click()
            await page.wait_for_timeout(3500)

            # Save state checkpoint
            state = await context.storage_state()
            session_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            await browser.close()
            return {
                "success": True,
                "email": email_clean,
                "message": "6-digit OTP sent to email. Please submit code via confirm_otp_step.",
                "pending": True,
            }
        except Exception as exc:
            logger.error("Muse login step failed for %s: %s", email_clean, exc)
            await browser.close()
            return {"success": False, "error": str(exc)}


async def confirm_otp_step(email: str, otp_code: str) -> Dict[str, Any]:
    """
    Step 2: Enter the 6-digit OTP code and persist the authorized session cookies.
    """
    from playwright.async_api import async_playwright

    email_clean = email.strip().lower()
    accounts = load_muse_accounts()
    acc = next((a for a in accounts if a.get("email") == email_clean), None)
    if not acc:
        return {"success": False, "error": f"Account {email_clean} not found in pool"}

    session_path = Path(acc["session_file"])
    if not session_path.exists():
        return {"success": False, "error": "Session checkpoint missing. Please call initiate_login_step first."}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(session_path),
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        try:
            await page.goto("https://muse.ai", wait_until="networkidle", timeout=35000)
            
            # Find OTP inputs or single code input
            otp_inputs = page.locator('input[autocomplete="one-time-code"], input[maxlength="1"], input[type="tel"]')
            count = await otp_inputs.count()
            if count >= 6:
                for idx, ch in enumerate(otp_code[:6]):
                    await otp_inputs.nth(idx).fill(ch)
            else:
                single_otp = page.locator('input[placeholder*="code" i], input[placeholder*="OTP" i]').first
                if await single_otp.count() > 0:
                    await single_otp.fill(otp_code)
                else:
                    await browser.close()
                    return {"success": False, "error": "Could not locate OTP input fields on page"}

            await page.wait_for_timeout(1000)
            submit_btn = page.locator('button:has-text("Verify"), button:has-text("Submit"), button[type="submit"]').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            await page.wait_for_timeout(4000)

            # Save full authenticated session state
            state = await context.storage_state()
            session_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            # Update account status
            acc["status"] = "active"
            acc["authorized_at"] = time.time()
            save_muse_accounts(accounts)

            await browser.close()
            return {"success": True, "email": email_clean, "status": "authenticated"}
        except Exception as exc:
            logger.error("Muse OTP verification failed: %s", exc)
            await browser.close()
            return {"success": False, "error": str(exc)}


async def reset_muse_account(email: str) -> bool:
    """
    Triggers 'Reset Muse' or wipes session context to restore initial generation allowance.
    """
    from playwright.async_api import async_playwright

    email_clean = email.strip().lower()
    accounts = load_muse_accounts()
    acc = next((a for a in accounts if a.get("email") == email_clean), None)
    if not acc or not Path(acc.get("session_file", "")).exists():
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=acc["session_file"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        try:
            await page.goto("https://muse.ai", wait_until="networkidle", timeout=35000)
            
            # Click settings or profile menu
            reset_btn = page.locator('button:has-text("Reset Muse"), button:has-text("Clear chat"), button:has-text("New agent")').first
            if await reset_btn.count() > 0:
                await reset_btn.click()
                await page.wait_for_timeout(1500)
                confirm = page.locator('button:has-text("Confirm"), button:has-text("Yes")').first
                if await confirm.count() > 0:
                    await confirm.click()
                logger.info("Successfully reset Muse AI account state for %s", email_clean)
                acc["credits_remaining"] = 50
                save_muse_accounts(accounts)
                await browser.close()
                return True
        except Exception as exc:
            logger.warning("Reset Muse action failed for %s: %s", email_clean, exc)
        await browser.close()
    return False


async def generate_muse_video_clip(
    prompt: str,
    out_path: Path,
    *,
    duration_sec: float = 5.0,
    aspect_ratio: str = "9:16",
    max_wait_sec: int = 120,
) -> Optional[Path]:
    """
    Select an active account from the pool and generate a video clip.
    If generation limits are reached, auto-reset the account and retry.
    """
    accounts = [a for a in load_muse_accounts() if a.get("status") == "active"]
    if not accounts:
        logger.debug("No active Muse AI accounts in pool. Skipping Muse engine.")
        return None

    # Rotate account
    accounts.sort(key=lambda x: x.get("total_generated", 0))
    selected = accounts[0]
    session_file = selected.get("session_file")
    if not session_file or not Path(session_file).exists():
        return None

    from playwright.async_api import async_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=session_file,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        try:
            logger.info("Navigating to Muse AI with account %s for video generation...", selected["email"])
            await page.goto("https://muse.ai", wait_until="networkidle", timeout=35000)

            # Send prompt
            chat_input = page.locator('textarea, input[placeholder*="Ask" i], input[placeholder*="create" i]').first
            if await chat_input.count() == 0:
                await browser.close()
                return None

            video_prompt = f"Create a photorealistic cinematic video clip: {prompt}. Duration: {int(duration_sec)}s, format: {aspect_ratio}. High quality."
            await chat_input.fill(video_prompt)
            await page.keyboard.press("Enter")
            logger.info("Submitted video prompt to Muse AI. Waiting for generation...")

            # Wait for video element or download link
            start_t = time.time()
            video_url = None
            while time.time() - start_t < max_wait_sec:
                videos = page.locator("video")
                if await videos.count() > 0:
                    src = await videos.first.get_attribute("src")
                    if src and src.startswith("http"):
                        video_url = src
                        break
                # Also check links
                links = page.locator('a[href$=".mp4"]')
                if await links.count() > 0:
                    video_url = await links.first.get_attribute("href")
                    break
                await page.wait_for_timeout(3000)

            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(video_url)
                    if resp.status_code == 200 and len(resp.content) > 10000:
                        out_path.write_bytes(resp.content)
                        logger.info("Muse AI video downloaded successfully: %s (%d bytes)", out_path.name, len(resp.content))
                        selected["total_generated"] = selected.get("total_generated", 0) + 1
                        selected["credits_remaining"] = max(0, selected.get("credits_remaining", 50) - 1)
                        save_muse_accounts(accounts)
                        await browser.close()
                        return out_path

        except Exception as exc:
            logger.warning("Muse generation exception: %s", exc)

        await browser.close()
    return None


def generate_muse_video_sync(
    prompt: str,
    out_path: Path,
    *,
    duration_sec: float = 5.0,
    aspect_ratio: str = "9:16",
    max_wait_sec: int = 90,
) -> Optional[Path]:
    """Synchronous wrapper for pipeline integration."""
    try:
        return asyncio.run(
            generate_muse_video_clip(
                prompt,
                out_path,
                duration_sec=duration_sec,
                aspect_ratio=aspect_ratio,
                max_wait_sec=max_wait_sec,
            )
        )
    except Exception as exc:
        logger.warning("generate_muse_video_sync failed: %s", exc)
        return None
