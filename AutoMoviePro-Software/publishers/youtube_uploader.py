from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from publishers.human_browser import (
    assert_no_captcha,
    human_click,
    human_paste_text,
    human_sleep,
    screenshot_find_and_click,
    upload_ritual,
    wait_human,
)
from publishers.session_vault import paths_for_channel
from publishers.stealth_session import stealth_browser
from publishers.upload_meta import normalize_job_meta

logger = logging.getLogger(__name__)


def upload_youtube(path: Path, job: Dict[str, Any], channel: Dict[str, Any]) -> str:
    lang = str(job.get("lang_code") or channel.get("_lang_code") or "en")
    paths = paths_for_channel("youtube", channel, lang_code=lang)
    store = paths["storage_state"]
    profile = paths["user_data_dir"]
    if not (Path(store).exists() or (Path(profile) / "Default").exists()):
        raise RuntimeError("YouTube session missing — চ্যানেলে YouTube Connect ব্যবহার করুন (একবার লগইন)")
    return _playwright_studio_upload(path, job, store, profile)


def _first_visible(page, selectors: List[str]):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            continue
    return None


def _fill_title(page, title: str) -> bool:
    for sel in (
        "#title-textarea #textbox",
        "ytcp-social-suggestions-textbox#title-textarea #textbox",
        "#textbox",
        'div[id="textbox"]',
        'input[name="title"]',
    ):
        loc = page.locator(sel)
        if not loc.count():
            continue
        try:
                    human_paste_text(page, loc.first, title[:100], prefer_type=True)
                    return True
        except Exception:
            continue
    return False


def _fill_description(page, description: str) -> bool:
    if not description:
        return True
    for sel in (
        "#description-textarea #textbox",
        "ytcp-social-suggestions-textbox#description-textarea #textbox",
        "#description-textarea",
    ):
        loc = page.locator(sel)
        if not loc.count():
            continue
        try:
            human_paste_text(page, loc.first, description[:4800])
            return True
        except Exception:
            continue
    return False


def _click_show_more(page) -> None:
    for label in ("Show more", "আরও দেখুন", "Más", "Afficher plus", "Mehr anzeigen"):
        try:
            btn = page.get_by_role("button", name=label)
            if btn.count() and human_click(page, btn.first):
                human_sleep(0.6, 1.2)
                return
        except Exception:
            pass
    loc = page.locator("#toggle-button, ytcp-button#toggle-button")
    if loc.count():
        try:
            human_click(page, loc.first)
            human_sleep(0.6, 1.2)
        except Exception:
            pass


def _fill_tags(page, tags: List[str]) -> bool:
    if not tags:
        return True
    _click_show_more(page)
    chip_text = ",".join(tags[:15])
    for sel in (
        "#tags-container input",
        "ytcp-form-input-container#tags-container input",
        "#text-input",
        'input[aria-label*="Tags" i]',
        'input[placeholder*="tag" i]',
    ):
        loc = page.locator(sel)
        if not loc.count():
            continue
        try:
            human_paste_text(page, loc.first, chip_text)
            human_sleep(0.4, 0.9)
            page.keyboard.press("Enter")
            return True
        except Exception:
            continue
    return False


def _upload_thumbnail(page, thumb_path: Optional[str]) -> bool:
    if not thumb_path:
        return False
    p = Path(thumb_path)
    if not p.is_file():
        return False
    # Prefer dedicated thumbnail file inputs
    for sel in (
        'ytcp-video-thumbnail-overview input[type="file"]',
        "#file-loader",
        'input[type="file"][accept*="image"]',
    ):
        loc = page.locator(sel)
        if not loc.count():
            continue
        try:
            loc.first.set_input_files(str(p))
            human_sleep(1.2, 2.4)
            return True
        except Exception:
            continue
    # Fallback: click "Upload file" / "Upload thumbnail" then set last file input
    for label in ("Upload file", "Upload thumbnail", "Custom thumbnail", "কাস্টম থাম্বনেইল"):
        try:
            btn = page.get_by_text(label, exact=False)
            if btn.count():
                human_click(page, btn.first)
                human_sleep(0.8, 1.5)
                break
        except Exception:
            pass
    files = page.locator('input[type="file"]')
    try:
        n = files.count()
        if n:
            files.nth(n - 1).set_input_files(str(p))
            human_sleep(1.2, 2.4)
            return True
    except Exception:
        return False
    return False


def _set_not_for_kids(page) -> None:
    for name in (
        "No, it's not made for kids",
        "No, this video is not made for kids",
        "না, এটি শিশুদের জন্য নয়",
    ):
        try:
            radio = page.get_by_role("radio", name=name)
            if radio.count():
                human_click(page, radio.first)
                return
        except Exception:
            pass
    loc = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_FOR_KIDS"]')
    if loc.count():
        try:
            human_click(page, loc.first)
        except Exception:
            pass


def _advance_studio_wizard(page) -> Dict[str, Any]:
    """
    Drive YouTube Studio checks → Next → Next → Visibility(Public) → Publish.
    Must not stop after title/description — user reported manual finish was needed.
    """
    report: Dict[str, Any] = {"steps": [], "published": False, "public_set": False}
    from publishers.human_browser import detect_captcha
    from publishers.captcha_solver import try_easy_solve

    def _soft_captcha() -> None:
        try:
            if detect_captcha(page):
                try_easy_solve(page)
        except Exception:
            pass

    for step in range(14):
        _soft_captcha()
        next_btn = page.locator("#next-button, ytcp-button#next-button")
        done_btn = page.locator("#done-button, ytcp-button#done-button")
        _ = (next_btn, done_btn)  # probed each loop for visibility below

        # Visibility: Public
        for pub in ("Public", "পাবলিক", "Öffentlich", "Público"):
            try:
                radio = page.get_by_role("radio", name=pub)
                if radio.count() and radio.first.is_visible():
                    if human_click(page, radio.first):
                        report["public_set"] = True
                        report["steps"].append(f"public:{pub}")
                        human_sleep(0.5, 1.0)
                        break
            except Exception:
                continue
        try:
            pub_radio = page.locator(
                'tp-yt-paper-radio-button[name="PUBLIC"], '
                '#privacy-radios tp-yt-paper-radio-button[name="PUBLIC"]'
            )
            if pub_radio.count() and pub_radio.first.is_visible():
                human_click(page, pub_radio.first)
                report["public_set"] = True
                report["steps"].append("public:PUBLIC")
                human_sleep(0.5, 1.0)
        except Exception:
            pass

        # Prefer Publish / Done when visible+enabled
        clicked = False
        for sel in ("#done-button", "ytcp-button#done-button"):
            btn = page.locator(sel)
            try:
                if btn.count() and btn.first.is_visible() and btn.first.is_enabled():
                    if human_click(page, btn.first):
                        report["steps"].append("done")
                        clicked = True
                        human_sleep(2.0, 3.5)
                        break
            except Exception:
                continue
        if not clicked:
            for label in ("Publish", "প্রকাশ", "Save", "Done"):
                try:
                    btn = page.get_by_role("button", name=label)
                    if btn.count() and btn.first.is_visible():
                        if human_click(page, btn.first):
                            report["steps"].append(f"label:{label}")
                            clicked = True
                            human_sleep(2.0, 3.5)
                            break
                except Exception:
                    continue

        if not clicked:
            for sel in ("#next-button", "ytcp-button#next-button"):
                btn = page.locator(sel)
                try:
                    if btn.count() and btn.first.is_visible() and btn.first.is_enabled():
                        if human_click(page, btn.first):
                            report["steps"].append("next")
                            clicked = True
                            human_sleep(1.4, 2.8)
                            break
                except Exception:
                    continue
        if not clicked:
            for label in ("Next", "পরবর্তী", "Continue"):
                try:
                    btn = page.get_by_role("button", name=label)
                    if btn.count() and btn.first.is_visible():
                        if human_click(page, btn.first):
                            report["steps"].append(f"label:{label}")
                            clicked = True
                            human_sleep(1.4, 2.8)
                            break
                except Exception:
                    continue

        # Success markers
        try:
            if page.locator("text=Video published").count() or page.locator(
                "text=published"
            ).count():
                report["published"] = True
                report["steps"].append("published_banner")
                break
        except Exception:
            pass
        try:
            share = page.locator("#share-url, #share-url-input, input#share-url")
            if share.count() and share.first.is_visible():
                report["published"] = True
                report["steps"].append("share_dialog")
                break
        except Exception:
            pass

        if not clicked and step >= 3:
            # One more Public+Done attempt then stop
            break

    # Final Publish attempt if still on visibility
    if not report.get("published"):
        _soft_captcha()
        for label in ("Publish", "প্রকাশ", "Done"):
            try:
                btn = page.get_by_role("button", name=label)
                if btn.count() and human_click(page, btn.first):
                    report["steps"].append(f"final:{label}")
                    human_sleep(2.5, 4.0)
                    break
            except Exception:
                continue
        try:
            if page.locator("#share-url, #share-url-input").count():
                report["published"] = True
        except Exception:
            pass

    logger.info("YouTube studio wizard steps: %s published=%s", report.get("steps"), report.get("published"))
    return report


def fill_youtube_studio_details(page, job: Dict[str, Any]) -> Dict[str, Any]:
    """Fill title/description/tags/thumbnail/kids — exported for tests."""
    meta = normalize_job_meta(job)
    report = {
        "title": False,
        "description": False,
        "tags": False,
        "thumbnail": False,
    }
    report["title"] = _fill_title(page, meta["title"])
    report["description"] = _fill_description(page, meta["description"])
    report["tags"] = _fill_tags(page, list(meta.get("tags") or []))
    report["thumbnail"] = _upload_thumbnail(page, meta.get("thumbnail"))
    _set_not_for_kids(page)
    return {"meta": meta, "filled": report}


def _playwright_studio_upload(path: Path, job: Dict[str, Any], storage: str, user_data_dir: str) -> str:
    with stealth_browser(
        storage_state=storage,
        user_data_dir=user_data_dir,
        headless=False,
    ) as (_pw, _b, page, engine):
        logger.info("YouTube upload via %s", engine)
        upload_ritual(page, "youtube")
        page.goto("https://www.youtube.com/upload", wait_until="domcontentloaded", timeout=90000)
        human_sleep(1.5, 3.0)
        assert_no_captcha(page, platform="youtube", url=page.url)
        wait_human(page, 'input[type="file"]', timeout_ms=20000)
        page.set_input_files('input[type="file"]', str(path))
        human_sleep(3.5, 7.0)
        screenshot_find_and_click(page, hint="yt_upload")
        # Let Studio details panel settle like a human watching progress
        wait_human(page, "#textbox, #title-textarea", timeout_ms=45000)
        human_sleep(1.0, 2.5)

        filled = fill_youtube_studio_details(page, job)
        logger.info("YouTube meta fill: %s", filled.get("filled"))

        human_sleep(1.0, 2.0)
        wiz = _advance_studio_wizard(page)
        human_sleep(2.0, 4.0)
        url = page.url or f"https://studio.youtube.com/ (uploaded {path.name})"
        if not wiz.get("published"):
            # Still return URL but mark incomplete so callers can see it in logs
            logger.error("YouTube wizard did not confirm Publish — steps=%s", wiz.get("steps"))
            screenshot_find_and_click(page, hint="yt_publish_incomplete")
            raise RuntimeError(
                "youtube_publish_incomplete:title_desc_ok_but_wizard_not_finished:"
                + ",".join(wiz.get("steps") or [])
            )
        try:
            share = page.locator("#share-url, #share-url-input, input#share-url")
            if share.count():
                val = share.first.input_value()
                if val and val.startswith("http"):
                    url = val
        except Exception:
            pass
        return url
