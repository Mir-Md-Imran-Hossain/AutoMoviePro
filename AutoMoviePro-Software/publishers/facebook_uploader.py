from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from publishers.human_browser import (
    assert_no_captcha,
    human_click,
    human_paste_text,
    human_sleep,
    screenshot_find_and_click,
    upload_ritual,
)
from publishers.session_vault import paths_for_channel
from publishers.stealth_session import stealth_browser
from publishers.upload_meta import normalize_job_meta

logger = logging.getLogger(__name__)


def upload_facebook(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> str:
    lang = str(job.get("lang_code") or channel.get("_lang_code") or "en")
    paths = paths_for_channel("facebook", channel, lang_code=lang)
    store = paths["storage_state"]
    profile = paths["user_data_dir"]
    if not (Path(store).exists() or (Path(profile) / "Default").exists()):
        raise RuntimeError("Facebook session missing — চ্যানেলে Facebook Connect ব্যবহার করুন (একবার লগইন)")
    return _playwright_page_upload(
        path, job, store, profile, channel.get("facebook_name") or ""
    )


def _switch_to_page(page, page_name: str) -> None:
    """If a Page name is set, try the account switcher so we post as the Page."""
    name = (page_name or "").strip()
    if not name:
        return
    try:
        for sel in (
            '[aria-label="Your profile"]',
            '[aria-label="Account"]',
            '[aria-label*="Your profile" i]',
            '[aria-label="Controls and settings for your account and Page"]',
        ):
            loc = page.locator(sel)
            if loc.count() and human_click(page, loc.first):
                human_sleep(0.8, 1.6)
                break
        el = page.get_by_text(name, exact=False)
        if el.count():
            human_click(page, el.first)
            human_sleep(2.0, 3.5)
            return
        see = page.get_by_text("See all profiles", exact=False)
        if not see.count():
            see = page.get_by_text("সব প্রোফাইল দেখুন", exact=False)
        if see.count() and human_click(page, see.first):
            human_sleep(1.0, 2.0)
            el = page.get_by_text(name, exact=False)
            if el.count():
                human_click(page, el.first)
                human_sleep(2.0, 3.5)
    except Exception as exc:
        logger.debug("facebook page switch skipped: %s", exc)


def _open_composer(page) -> None:
    labels = (
        "Photo/video",
        "Photo/Video",
        "ফটো/ভিডিओ",
        "What's on your mind",
        "আপনার মনে কী চলছে",
        "Create post",
        "পোস্ট তৈরি",
        "Reel",
    )
    for label in labels:
        try:
            el = page.get_by_text(label, exact=False)
            if el.count() and human_click(page, el.first):
                human_sleep(1.0, 2.0)
                return
        except Exception:
            continue
    # aria / role fallbacks (2025–2026 FB)
    for sel in (
        '[aria-label*="Photo" i]',
        '[aria-label*="Create" i]',
        'div[role="button"][tabindex="0"]',
    ):
        loc = page.locator(sel)
        try:
            if loc.count():
                human_click(page, loc.first)
                human_sleep(1.0, 2.0)
                return
        except Exception:
            continue


def _playwright_page_upload(
    path: Path,
    job: Dict[str, Any],
    storage: str,
    user_data_dir: str,
    page_name: str,
) -> str:
    meta = normalize_job_meta(job)
    caption = str(meta.get("facebook_caption") or "")
    with stealth_browser(
        storage_state=storage,
        user_data_dir=user_data_dir,
        headless=False,
    ) as (_pw, _b, page, engine):
        logger.info("Facebook upload via %s", engine)
        upload_ritual(page, "facebook")
        start = "https://www.facebook.com/"
        page.goto(start, wait_until="domcontentloaded", timeout=90000)
        human_sleep(2.0, 4.0)
        assert_no_captcha(page, platform="facebook", url=page.url)
        _switch_to_page(page, page_name)
        screenshot_find_and_click(page, hint="fb_home")
        _open_composer(page)

        human_sleep(1.0, 2.0)
        file_inputs = page.locator('input[type="file"]')
        if file_inputs.count():
            # Prefer video-capable input when multiple exist
            chosen = file_inputs.first
            try:
                for i in range(file_inputs.count()):
                    acc = (file_inputs.nth(i).get_attribute("accept") or "").lower()
                    if "video" in acc or "mp4" in acc or acc == "":
                        chosen = file_inputs.nth(i)
                        break
            except Exception:
                pass
            chosen.set_input_files(str(path))
            human_sleep(3.0, 5.5)

        if caption:
            box = page.locator(
                "div[contenteditable='true'][role='textbox'], "
                "div[contenteditable='true'], "
                "[role='textbox']"
            )
            if box.count():
                # Prefer the largest / last composer box (not search)
                target = box.last if box.count() > 1 else box.first
                human_paste_text(page, target, caption[:2000])

        assert_no_captcha(page, platform="facebook", url=page.url)
        for label in ("Post", "পোস্ট", "Publish", "Share", "শেয়ার", "Next"):
            btn = page.get_by_role("button", name=label)
            if btn.count():
                if human_click(page, btn.first):
                    break
        human_sleep(3.0, 5.0)
        return page.url or f"https://facebook.com/ (uploaded {path.name} to {page_name})"
