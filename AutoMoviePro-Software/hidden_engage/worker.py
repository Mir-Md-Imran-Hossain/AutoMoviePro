"""
Daily human-like engagement on promo channels / pages.

Uses Patchright/stealth Chrome + human_browser behaviors:
  warmup browsing, aimless scroll, watch, occasional like/share/comment,
  paste-style comments, CAPTCHA hard-stop for admin unlock.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any, Dict, List

from app import db as store
from app.api_client import LicenseClient
from publishers.human_browser import (
    CaptchaBlockedError,
    DEFAULT_COMMENTS,
    aimless_scroll,
    assert_no_captcha,
    captcha_is_locked,
    human_click,
    human_paste_text,
    human_sleep,
    maybe_comment,
    maybe_like,
    maybe_share,
    reading_pause,
    screenshot_find_and_click,
    warmup_browse,
)
from publishers.stealth_session import stealth_browser

logger = logging.getLogger(__name__)


def run_daily_engagement() -> Dict[str, Any]:
    if captcha_is_locked():
        return {
            "ok": False,
            "error": "captcha_locked",
            "hint": "Admin must unlock CAPTCHA before engagement continues",
            "captcha": True,
        }

    session = store.get_session()
    if not session:
        return {"ok": False, "error": "not_logged_in"}

    client = LicenseClient(session["api_base_url"], session["token"])
    try:
        links = client.promo_links()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    channels = [c for c in store.list_channels() if c.get("enabled")]
    summary: List[Dict[str, Any]] = []

    # Also engage own language destinations as "home" targets
    own_targets = _own_destination_targets(channels)
    all_links = list(links or []) + own_targets

    for link in all_links:
        if captcha_is_locked():
            summary.append({"action": "stopped", "reason": "captcha_locked"})
            break
        platform = (link.get("platform") or "").lower()
        url = link.get("url") or ""
        if not url or platform not in ("youtube", "facebook"):
            continue
        try:
            # Follow/subscribe once
            if not store.engage_done(platform, url, "follow"):
                ok = _engage_visit(
                    platform,
                    url,
                    channels,
                    mode="follow",
                    watch_seconds=random.randint(25, 70),
                )
                if ok:
                    store.mark_engage(platform, url, "follow")
                summary.append({"url": url, "action": "follow", "ok": ok})

            play_action = f"play_{datetime.now().date().isoformat()}"
            if store.engage_done(platform, url, play_action):
                summary.append({"url": url, "action": "play", "ok": True, "skipped": True})
                continue

            watch_seconds = random.choice([75, 120, 180, 0])
            if watch_seconds == 0:
                watch_seconds = random.randint(210, 480)
            ok_play = _engage_visit(
                platform,
                url,
                channels,
                mode="watch",
                watch_seconds=watch_seconds,
                allow_comment=True,
                allow_share=True,
            )
            if ok_play:
                store.mark_engage(platform, url, play_action)
            summary.append({"url": url, "action": "play", "seconds": watch_seconds, "ok": ok_play})
        except CaptchaBlockedError as exc:
            summary.append({"url": url, "action": "captcha_block", "ok": False, "error": str(exc)})
            return {
                "ok": False,
                "error": "captcha_locked",
                "summary": summary,
                "hint": "CAPTCHA detected — waiting for admin unlock",
                "captcha": True,
            }
        except Exception as exc:
            logger.exception("engage item failed")
            summary.append({"url": url, "action": "error", "ok": False, "error": str(exc)[:200]})

    store.set_meta("last_engage_day", datetime.now().date().isoformat())
    return {"ok": True, "summary": summary, "count": len(summary)}


def _own_destination_targets(channels: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for ch in channels:
        yt = (ch.get("youtube_name") or "").strip()
        fb = (ch.get("facebook_name") or "").strip()
        if yt:
            # search-style URL — human will land then browse
            out.append({
                "platform": "youtube",
                "url": f"https://www.youtube.com/results?search_query={yt.replace(' ', '+')}",
                "own": "1",
            })
        if fb:
            out.append({
                "platform": "facebook",
                "url": f"https://www.facebook.com/search/top?q={fb.replace(' ', '%20')}",
                "own": "1",
            })
        try:
            from pipeline.lang_destinations import parse_lang_destinations

            dest = parse_lang_destinations(ch.get("lang_destinations_json"))
            for slot in dest.values():
                y2 = (slot.get("youtube_name") or "").strip()
                f2 = (slot.get("facebook_name") or "").strip()
                if y2 and y2 != yt:
                    out.append({
                        "platform": "youtube",
                        "url": f"https://www.youtube.com/results?search_query={y2.replace(' ', '+')}",
                    })
                if f2 and f2 != fb:
                    out.append({
                        "platform": "facebook",
                        "url": f"https://www.facebook.com/search/top?q={f2.replace(' ', '%20')}",
                    })
        except Exception:
            pass
    # de-dupe by url
    seen = set()
    uniq = []
    for item in out:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        uniq.append(item)
    return uniq[:8]


def _pick_storage(platform: str, channels: List[Dict[str, Any]]) -> str:
    key = "youtube_session" if platform == "youtube" else "facebook_session"
    for ch in channels:
        if ch.get(key):
            return str(ch[key])
        try:
            from pipeline.lang_destinations import parse_lang_destinations

            dest = parse_lang_destinations(ch.get("lang_destinations_json"))
            for slot in dest.values():
                if slot.get(key):
                    return str(slot[key])
        except Exception:
            pass
    return ""


def _engage_visit(
    platform: str,
    url: str,
    channels: List[Dict[str, Any]],
    *,
    mode: str,
    watch_seconds: int = 60,
    allow_comment: bool = False,
    allow_share: bool = False,
) -> bool:
    storage = _pick_storage(platform, channels)
    if not storage:
        logger.warning("no session for %s", platform)
        return False

    with stealth_browser(storage_state=storage, headless=False) as (_pw, _browser, page, engine):
        logger.info("engage via %s mode=%s url=%s", engine, mode, url[:80])
        # Warmup like a human opening the app first
        if random.random() < 0.7:
            warmup_browse(page, platform)

        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        human_sleep(1.5, 3.5)
        assert_no_captcha(page, platform=platform, url=url)
        screenshot_find_and_click(page, hint=f"land_{platform}")

        aimless_scroll(page, bursts=random.randint(2, 6))
        reading_pause()

        if mode == "follow":
            _do_follow(page, platform)

        # Open a video / post if on a listing
        if platform == "youtube":
            thumbs = page.locator(
                "ytd-video-renderer a#video-title, ytd-rich-item-renderer a#thumbnail, a#video-title-link"
            )
            if thumbs.count() and random.random() < 0.85:
                idx = random.randint(0, min(5, thumbs.count() - 1))
                human_click(page, thumbs.nth(idx))
                human_sleep(2.0, 4.0)
                assert_no_captcha(page, platform=platform, url=page.url)

        # Watch / dwell
        dwell = max(15, int(watch_seconds * random.uniform(0.75, 1.15)))
        chunks = max(2, dwell // random.randint(12, 25))
        per = dwell / chunks
        for _ in range(chunks):
            if random.random() < 0.4:
                aimless_scroll(page, bursts=1)
            if random.random() < 0.2:
                # nudge mouse like watching
                try:
                    page.mouse.move(random.randint(200, 900), random.randint(200, 600))
                except Exception:
                    pass
            human_sleep(per * 0.7, per * 1.3)

        maybe_like(page, platform)
        if allow_share:
            maybe_share(page, platform)
        if allow_comment:
            maybe_comment(page, platform, DEFAULT_COMMENTS)

        # Extra stray browse sometimes
        if random.random() < 0.35:
            aimless_scroll(page, bursts=random.randint(1, 3))
            reading_pause()

        return True


def _do_follow(page, platform: str) -> None:
    if platform == "youtube":
        for name in ["Subscribe", "সাবস্ক্রাইব"]:
            btn = page.get_by_role("button", name=name)
            if btn.count():
                human_click(page, btn)
                human_sleep(0.8, 2.0)
                return
        # channel link then subscribe
        ch = page.locator("ytd-channel-name a, #channel-name a").first
        if ch.count():
            human_click(page, ch)
            human_sleep(1.5, 3.0)
            btn = page.get_by_role("button", name="Subscribe")
            if btn.count():
                human_click(page, btn)
    else:
        for name in ["Follow", "ফলো", "Like", "লাইক"]:
            btn = page.get_by_role("button", name=name)
            if btn.count():
                human_click(page, btn)
                human_sleep(0.8, 2.0)
                return
