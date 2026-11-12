"""
=============================================================================
AutoMovie Pro - Autonomous Facebook Page Video & Reel Publisher Engine
=============================================================================
Features:
1. Seamless Facebook Page switching and identity assertion.
2. Uploads horizontal long-form videos & vertical 9:16 reels.
3. Custom thumbnail detection and attachment (Video options / custom image).
4. High-converting SEO Title, Description, Helpline, Website & Hashtags injection.
5. Captures high-resolution visual proof screenshot into data/reels_proofs/.
6. Extracts live published video permalink (https://facebook.com/watch/?v=... or /reel/...).
7. Direct integration with AutoMovie Pro local database and website jobs-sync.
=============================================================================
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.config import DATA_DIR
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

PROOF_DIR = DATA_DIR / "reels_proofs"
PROOF_DIR.mkdir(parents=True, exist_ok=True)


def resolve_custom_thumbnail(path: Path, job: Dict[str, Any]) -> Optional[Path]:
    """Finds available high-converting custom thumbnail image for the video."""
    candidates = []
    # 1. Explicit thumbnail_path in job dict
    explicit = job.get("thumbnail_path")
    if explicit:
        candidates.append(Path(explicit))

    # 2. Sibling image files in video folder
    parent = path.parent
    candidates.extend([
        parent / "thumbnail.png",
        parent / "thumbnail_variant_a.png",
        parent / "thumbnail_variant_b.png",
        parent / "thumbnail.jpg",
        parent / "cover.png",
        parent / "cover.jpg",
        path.with_suffix(".png"),
        path.with_suffix(".jpg"),
    ])

    for cand in candidates:
        try:
            if cand.exists() and cand.is_file() and cand.stat().st_size > 1000:
                return cand
        except Exception:
            continue
    return None


def format_facebook_seo_caption(job: Dict[str, Any], meta: Dict[str, Any], channel_name: str = "") -> str:
    """Constructs a high-engagement, viral, and SEO-optimized Facebook post caption."""
    title = str(job.get("title") or meta.get("title") or "").strip()
    raw_desc = str(job.get("description") or meta.get("facebook_caption") or meta.get("description") or "").strip()
    raw_tags = str(job.get("tags") or meta.get("tags") or "").strip()

    # Format tags into hashtags
    hashtags_list = []
    if raw_tags:
        for t in re.split(r"[,;\s]+", raw_tags):
            clean_tag = re.sub(r"[^\w\u0980-\u09FF]", "", t.strip())
            if clean_tag and not clean_tag.isdigit():
                hashtags_list.append(f"#{clean_tag}")

    default_tags = ["#AutoMoviePro", "#AIVideo", "#PassiveIncome", "#FacebookReels", "#VideoAutomation"]
    for dt in default_tags:
        if dt not in hashtags_list and len(hashtags_list) < 12:
            hashtags_list.append(dt)

    hashtags_str = " ".join(hashtags_list[:12])

    body_parts = []
    if title:
        body_parts.append(f"🎬 {title}\n")
    if raw_desc and raw_desc != title:
        body_parts.append(f"{raw_desc}\n")

    # Official Conversion & Contact Links
    body_parts.append(
        "🌐 ১-ক্লিকে ওয়েবসাইট ভিজিট করুন: https://automoviepro.com\n"
        "💬 হোয়াটসঅ্যাপে সরাসরি ইনবক্স করুন: https://wa.me/8801968111593\n"
        "📞 হেল্পলাইন / WhatsApp: +8801968111593\n"
    )

    if hashtags_str:
        body_parts.append(hashtags_str)

    return "\n".join(body_parts).strip()


def _switch_to_page(page, page_name: str) -> None:
    """Switches Facebook account identity to the designated Page."""
    name = (page_name or "").strip()
    if not name:
        return
    logger.info("Verifying/Switching to Facebook Page: '%s'...", name)
    try:
        # Check if already on the page or viewing as page
        heading = page.locator("h1, h2").first
        if heading.count() and name.lower() in (heading.inner_text() or "").lower():
            logger.info("Already operating as Page '%s'", name)
            return

        for sel in (
            '[aria-label="Your profile"]',
            '[aria-label="Account"]',
            '[aria-label*="Your profile" i]',
            '[aria-label*="Controls and settings" i]',
            '[aria-label="প্রোফাইল"]',
            '[aria-label="অ্যাকাউন্ট"]',
        ):
            loc = page.locator(sel)
            if loc.count() and human_click(page, loc.first):
                human_sleep(1.0, 2.0)
                break

        el = page.get_by_text(name, exact=False)
        if el.count():
            human_click(page, el.first)
            human_sleep(2.5, 4.0)
            return

        see = page.get_by_text("See all profiles", exact=False)
        if not see.count():
            see = page.get_by_text("সব প্রোফাইল দেখুন", exact=False)
        if see.count() and human_click(page, see.first):
            human_sleep(1.2, 2.2)
            el = page.get_by_text(name, exact=False)
            if el.count():
                human_click(page, el.first)
                human_sleep(2.5, 4.0)
    except Exception as exc:
        logger.debug("Facebook page switch error (ignoring if already on page): %s", exc)


def _open_composer(page) -> None:
    """Locates and opens the feed/reel post composer dialog."""
    labels = (
        "Photo/video",
        "Photo/Video",
        "ফটো/ভিডিও",
        "What's on your mind",
        "আপনার মনে কী চলছে",
        "Create post",
        "পোস্ট তৈরি",
        "Reel",
        "রিল",
    )
    for label in labels:
        try:
            el = page.get_by_text(label, exact=False)
            if el.count() and human_click(page, el.first):
                human_sleep(1.2, 2.2)
                return
        except Exception:
            continue

    # Fallback to aria/role selectors
    for sel in (
        '[aria-label*="Photo" i]',
        '[aria-label*="Create" i]',
        '[aria-label*="Reel" i]',
        'div[role="button"][tabindex="0"]:has-text("Photo")',
        'div[role="button"][tabindex="0"]:has-text("Reel")',
    ):
        loc = page.locator(sel)
        try:
            if loc.count() and human_click(page, loc.first):
                human_sleep(1.2, 2.2)
                return
        except Exception:
            continue


def _try_attach_thumbnail(page, thumbnail_path: Path) -> bool:
    """Attempts to upload the custom thumbnail image to Facebook video composer."""
    if not thumbnail_path or not thumbnail_path.exists():
        return False
    logger.info("Attempting custom thumbnail upload: %s", thumbnail_path.name)
    try:
        # Check for 'Video options' / 'Video Options' / 'ভিডিও বিকল্পসমূহ'
        for opt_label in ("Video options", "Video Options", "ভিডিও বিকল্পসমূহ", "Options", "বিকল্পসমূহ"):
            opt_btn = page.locator(f"div[role='button']:has-text('{opt_label}'), span:has-text('{opt_label}')")
            if opt_btn.count():
                human_click(page, opt_btn.first)
                human_sleep(1.5, 2.5)
                break

        # Check for 'Change thumbnail' / 'Upload image' / 'Custom thumbnail'
        for thumb_label in ("Change thumbnail", "থাম্বনেল পরিবর্তন", "Upload image", "ছবি আপলোড", "Custom", "কাস্টম"):
            t_btn = page.locator(f"div[role='button']:has-text('{thumb_label}'), span:has-text('{thumb_label}')")
            if t_btn.count():
                human_click(page, t_btn.first)
                human_sleep(1.0, 1.8)
                break

        # Locate image file input
        img_inputs = page.locator("input[type='file'][accept*='image']")
        if img_inputs.count():
            img_inputs.first.set_input_files(str(thumbnail_path))
            human_sleep(2.0, 3.5)
            logger.info("✅ Custom thumbnail attached successfully!")
            # Save options if a 'Save' / 'সংরক্ষণ' button is visible
            for s_label in ("Save", "সংরক্ষণ", "Done", "হয়ে গেছে"):
                s_btn = page.locator(f"div[role='dialog'] div[role='button']:has-text('{s_label}')")
                if s_btn.count():
                    human_click(page, s_btn.first)
                    human_sleep(1.0, 2.0)
                    break
            return True
    except Exception as exc:
        logger.debug("Custom thumbnail attachment skipped/failed: %s", exc)
    return False


def _extract_published_permalink(page, page_name: str, is_reel: bool = False) -> str:
    """
    Extracts the newly published video permalink from Facebook.
    Navigates to the Page's video or reel tab to get the authoritative permalink.
    """
    clean_name = re.sub(r"[^\w]", "", page_name or "")
    tab = "reels" if is_reel else "videos"
    fallback_url = f"https://www.facebook.com/{clean_name}/{tab}/" if clean_name else "https://www.facebook.com/"

    try:
        if clean_name:
            target_url = f"https://www.facebook.com/{clean_name}/{tab}/"
            logger.info("Navigating to Page %s to resolve permalink: %s", tab, target_url)
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            human_sleep(4.0, 6.0)
            page.evaluate("window.scrollBy(0, 350)")
            human_sleep(2.0, 3.5)

            # Look for recent video / reel links
            patterns = [
                "a[href*='/reel/']",
                "a[href*='/videos/']",
                "a[href*='/watch/?v=']",
                "a[href*='facebook.com/watch']",
            ]
            for sel in patterns:
                links = page.locator(sel)
                count = links.count()
                for i in range(min(count, 5)):
                    href = links.nth(i).get_attribute("href") or ""
                    if href:
                        if href.startswith("/"):
                            href = "https://www.facebook.com" + href
                        # Clean tracking params
                        clean_link = href.split("?")[0] if "/reel/" in href or "/videos/" in href else href
                        if any(k in clean_link for k in ("/reel/", "/videos/", "watch")):
                            logger.info("✅ Extracted live Facebook permalink: %s", clean_link)
                            return clean_link
    except Exception as exc:
        logger.debug("Permalink extraction exception: %s", exc)

    return fallback_url


def _playwright_page_upload(
    path: Path,
    job: Dict[str, Any],
    storage: str,
    user_data_dir: str,
    page_name: str,
) -> Dict[str, Any]:
    meta = normalize_job_meta(job)
    caption = format_facebook_seo_caption(job, meta, channel_name=page_name)
    thumbnail_path = resolve_custom_thumbnail(path, job)
    is_reel = str(job.get("video_type") or "").lower() == "short" or "reel" in str(path).lower()

    proof_file = PROOF_DIR / f"fb_upload_proof_{job.get('id', 'job')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    with stealth_browser(
        storage_state=storage,
        user_data_dir=user_data_dir,
        headless=False,
    ) as (_pw, _b, page, engine):
        logger.info("Facebook upload starting via %s for file: %s (is_reel=%s)", engine, path.name, is_reel)
        upload_ritual(page, "facebook")

        # 1. Direct navigation
        start = "https://www.facebook.com/"
        page.goto(start, wait_until="domcontentloaded", timeout=90000)
        human_sleep(2.5, 4.5)
        assert_no_captcha(page, platform="facebook", url=page.url)

        # 2. Switch to designated Page identity
        _switch_to_page(page, page_name)

        # 3. Open Composer or Navigate to Reel Creator
        if is_reel:
            logger.info("Checking direct Reel creator: https://www.facebook.com/reels/create ...")
            try:
                page.goto("https://www.facebook.com/reels/create", wait_until="domcontentloaded", timeout=45000)
                human_sleep(3.0, 5.0)
            except Exception:
                _open_composer(page)
        else:
            screenshot_find_and_click(page, hint="fb_home")
            _open_composer(page)

        human_sleep(1.5, 3.0)

        # 4. Attach Video File
        file_inputs = page.locator('input[type="file"]')
        if file_inputs.count():
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
            logger.info("Video file attached: %s. Waiting for metadata extraction...", path.name)
            human_sleep(4.0, 7.0)

        # 5. Attach Custom Thumbnail (if found)
        if thumbnail_path:
            _try_attach_thumbnail(page, thumbnail_path)

        # 6. Insert SEO Caption & Tags
        if caption:
            box = page.locator(
                "div[aria-label*='Describe your reel' i], "
                "div[aria-label*='Create a public post' i], "
                "div[contenteditable='true'][role='textbox'], "
                "div[contenteditable='true'], "
                "[role='textbox'], "
                "textarea"
            )
            if box.count():
                target = box.last if box.count() > 1 else box.first
                human_paste_text(page, target, caption[:2500])
                human_sleep(1.0, 2.0)

        assert_no_captcha(page, platform="facebook", url=page.url)

        # 7. Step through Next / Publish / Post buttons
        for _ in range(3):
            next_btn = page.locator(
                "div[role='dialog'] div[role='button']:has-text('Next'), "
                "div[role='dialog'] button:has-text('Next'), "
                "div[role='button']:has-text('পরবর্তী')"
            ).first
            if next_btn.count() and next_btn.is_visible():
                human_click(page, next_btn)
                human_sleep(2.0, 3.5)

        # Final Post / Publish Button
        for label in ("Post", "পোস্ট", "Publish", "প্রকাশ করুন", "Share", "শেয়ার"):
            btn = page.get_by_role("button", name=label)
            if btn.count() and btn.first.is_visible():
                if human_click(page, btn.first):
                    logger.info("Clicked '%s' button!", label)
                    break

        logger.info("Post submitted. Waiting 25s for Meta media ingestion...")
        human_sleep(20.0, 28.0)

        # 8. Capture Proof Screenshot
        try:
            page.screenshot(path=str(proof_file))
            logger.info("📸 Visual proof screenshot captured: %s", proof_file.name)
        except Exception as exc:
            logger.debug("Screenshot capture error: %s", exc)

        # 9. Extract Live Video Permalink
        permalink = _extract_published_permalink(page, page_name, is_reel=is_reel)

        return {
            "ok": True,
            "url": permalink,
            "proof_path": str(proof_file) if proof_file.exists() else "",
            "thumbnail_path": str(thumbnail_path) if thumbnail_path else "",
            "title": str(job.get("title") or ""),
        }


def upload_facebook(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> str:
    """Primary upload entry point called by upload_service."""
    lang = str(job.get("lang_code") or channel.get("_lang_code") or "en")
    paths = paths_for_channel("facebook", channel, lang_code=lang)
    store = paths["storage_state"]
    profile = paths["user_data_dir"]
    if not (Path(store).exists() or (Path(profile) / "Default").exists()):
        raise RuntimeError("Facebook session missing — চ্যানেলে Facebook Connect ব্যবহার করুন (একবার লগইন)")

    page_name = str(channel.get("facebook_name") or "").strip()
    res = _playwright_page_upload(path, job, store, profile, page_name)
    url = res.get("url") or f"https://facebook.com/{page_name.replace(' ', '')}"
    return url
