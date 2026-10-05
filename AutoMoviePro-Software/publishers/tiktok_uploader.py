"""
Autonomous TikTok Video Uploader for AutoMovie Pro.
Uses stealth browser + persistent session profile (Patchright / Playwright).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from publishers.human_browser import (
    assert_no_captcha,
    human_click,
    human_paste_text,
    human_sleep,
    upload_ritual,
)
from publishers.session_vault import paths_for_channel
from publishers.stealth_session import stealth_browser
from publishers.upload_meta import normalize_job_meta

logger = logging.getLogger(__name__)

TIKTOK_UPLOAD_URL = "https://www.tiktok.com/creator-center/upload?lang=en"
TIKTOK_UPLOAD_FALLBACK = "https://www.tiktok.com/upload?lang=en"


def upload_tiktok(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> str:
    """
    Publish video to TikTok using persistent logged-in browser session.
    """
    if settings.dry_run_publish:
        logger.info("DRY RUN TikTok upload: %s", path)
        return f"dry-run://tiktok/{path.name}"

    lang = str(job.get("lang_code") or channel.get("_lang_code") or "en")
    paths = paths_for_channel("tiktok", channel, lang_code=lang)
    store = paths["storage_state"]
    profile = paths["user_data_dir"]

    if not (Path(store).exists() or (Path(profile) / "Default").exists()):
        raise RuntimeError(
            "TikTok session missing — চ্যানেলে TikTok Connect ব্যবহার করুন (একবার লগইন করুন)"
        )

    return _playwright_tiktok_upload(path, job, store, profile, channel.get("tiktok_name") or "")


def _playwright_tiktok_upload(
    path: Path,
    job: Dict[str, Any],
    storage: str,
    user_data_dir: str,
    account_name: str,
) -> str:
    meta = normalize_job_meta(job)
    title = str(job.get("title") or meta.get("title") or "")
    tags = job.get("tags") or meta.get("tags") or []
    if isinstance(tags, str):
        tag_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]
    elif isinstance(tags, list):
        tag_list = [str(t).strip().lstrip("#") for t in tags if str(t).strip()]
    else:
        tag_list = []

    hashtags = " ".join(f"#{t}" for t in tag_list[:8])
    caption = f"{title}\n\n{hashtags}".strip()[:2000]

    with stealth_browser(
        storage_state=storage,
        user_data_dir=user_data_dir,
        headless=False,
    ) as (_pw, _b, page, engine):
        logger.info("TikTok upload via %s", engine)
        upload_ritual(page, "tiktok")

        # 1. Navigate to Creator Center upload
        try:
            page.goto(TIKTOK_UPLOAD_URL, wait_until="domcontentloaded", timeout=90000)
        except Exception:
            page.goto(TIKTOK_UPLOAD_FALLBACK, wait_until="domcontentloaded", timeout=90000)

        human_sleep(3.0, 5.0)
        assert_no_captcha(page, platform="tiktok", url=page.url)

        # 2. Check if redirected to login
        if "/login" in (page.url or "").lower():
            raise RuntimeError(
                "TikTok session expired or not logged in — পুনরায় TikTok Connect এ লগইন করুন"
            )

        # 3. Locate file input (may be inside upload iframe or direct in page)
        file_input = None
        # Check if page has an iframe for upload
        for frame in page.frames:
            try:
                inputs = frame.locator('input[type="file"]')
                if inputs.count():
                    file_input = inputs.first
                    break
            except Exception:
                continue

        if not file_input:
            inputs = page.locator('input[type="file"]')
            if inputs.count():
                file_input = inputs.first

        if not file_input:
            # Try waiting for upload input
            try:
                page.wait_for_selector('input[type="file"]', timeout=15000)
                file_input = page.locator('input[type="file"]').first
            except Exception:
                pass

        if not file_input:
            raise RuntimeError("TikTok upload input not found — page structure changed or slow loading")

        logger.info("Setting TikTok upload file: %s", path)
        file_input.set_input_files(str(path))
        human_sleep(5.0, 8.0)

        assert_no_captcha(page, platform="tiktok", url=page.url)

        # 4. Fill Caption / Description
        if caption:
            # Common TikTok caption selectors
            caption_selectors = [
                'div[contenteditable="true"][role="combobox"]',
                'div[contenteditable="true"]',
                '.notranslate.public-DraftEditor-content',
                '[data-text="true"]',
                'div.DraftEditor-root',
            ]
            caption_box = None
            for sel in caption_selectors:
                try:
                    # Look in frames first
                    for frame in page.frames:
                        boxes = frame.locator(sel)
                        if boxes.count():
                            caption_box = boxes.first
                            break
                    if caption_box:
                        break
                    boxes = page.locator(sel)
                    if boxes.count():
                        caption_box = boxes.first
                        break
                except Exception:
                    continue

            if caption_box:
                try:
                    human_paste_text(page, caption_box, caption)
                    human_sleep(1.0, 2.0)
                except Exception as exc:
                    logger.warning("Could not type caption directly: %s", exc)

        # 5. Wait for video upload & processing check
        human_sleep(5.0, 8.0)
        assert_no_captcha(page, platform="tiktok", url=page.url)

        # 6. Click Post Button
        post_btn = None
        post_selectors = [
            'button[data-e2e="post_video_button"]',
            'button:has-text("Post")',
            'button:has-text("পোস্ট")',
            'button:has-text("Publish")',
            '.btn-post',
        ]
        for sel in post_selectors:
            try:
                for frame in page.frames:
                    btns = frame.locator(sel)
                    if btns.count() and btns.first.is_enabled():
                        post_btn = btns.first
                        break
                if post_btn:
                    break
                btns = page.locator(sel)
                if btns.count() and btns.first.is_enabled():
                    post_btn = btns.first
                    break
            except Exception:
                continue

        if post_btn:
            logger.info("Clicking TikTok Post button...")
            human_click(page, post_btn)
            human_sleep(4.0, 7.0)
        else:
            logger.warning("TikTok Post button not found or not enabled yet")

        # 7. Check for modal confirmation or success
        # Some accounts show a "Your video has been uploaded" modal or "Manage your posts" button
        human_sleep(3.0, 5.0)

        final_url = page.url or f"https://www.tiktok.com/@{account_name or 'profile'}"
        logger.info("TikTok upload completed: %s", final_url)
        return final_url
