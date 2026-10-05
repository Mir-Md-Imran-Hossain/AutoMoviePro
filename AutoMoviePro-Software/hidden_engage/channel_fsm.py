"""
Intelligent channel/page engagement FSM for admin promo + peer videos.

Designed to look human and avoid automation fingerprints:
  - budget hard-stop (no infinite loops)
  - max retries per UI action
  - skip if already subscribed / already engaged (local + DOM)
  - sparse comments/shares (not every visit)
  - variable watch times; sometimes near-full watch
  - soft-fail on missing selectors (never hammer)
  - captcha abort
"""
from __future__ import annotations

import logging
import random
import time
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from app import db as store
from hidden_engage import activity_log
from hidden_engage.comments import prepare_comment
from publishers.human_browser import (
    CaptchaBlockedError,
    aimless_scroll,
    assert_no_captcha,
    captcha_is_locked,
    do_comment,
    do_like,
    do_share,
    edit_own_comment,
    human_click,
    human_sleep,
    reading_pause,
)

logger = logging.getLogger(__name__)

# Hard caps per browser session — prevents spammy bot patterns
MAX_SUBSCRIBE_PER_SESSION = 2
MAX_DAILY_SUBSCRIBES = 3
MAX_COMMENTS_PER_SESSION = 2
MAX_SHARES_PER_SESSION = 1
MAX_LIKES_PER_SESSION = 4
MAX_VIDEOS_PER_HUB = 3
MAX_ACTION_RETRIES = 2


def daily_subscribes_count(today: Optional[str] = None) -> int:
    d = today or date.today().isoformat()
    val = store.get_meta(f"daily_sub_count_{d}")
    try:
        return int(val) if val else 0
    except (ValueError, TypeError):
        return 0


def increment_daily_subscribes(today: Optional[str] = None) -> int:
    d = today or date.today().isoformat()
    c = daily_subscribes_count(d) + 1
    store.set_meta(f"daily_sub_count_{d}", str(c))
    return c


class SessionCaps:
    def __init__(self) -> None:
        self.subscribes = 0
        self.comments = 0
        self.shares = 0
        self.likes = 0
        self.errors = 0


def _safe(fn: Callable[[], bool], *, retries: int = MAX_ACTION_RETRIES) -> bool:
    """Run UI action with soft retries; never raise into a loop."""
    for attempt in range(max(1, retries)):
        try:
            if fn():
                return True
        except CaptchaBlockedError:
            raise
        except Exception as exc:
            logger.debug("action soft-fail attempt %s: %s", attempt + 1, exc)
        human_sleep(0.4 + attempt * 0.3, 1.0 + attempt * 0.5)
    return False


def _deadline_ok(deadline: float, need: float = 8.0) -> bool:
    return time.time() + need < deadline and not captcha_is_locked()


def subscription_status(page, platform: str) -> str:
    """
    Returns: subscribed | not_subscribed | unknown
    Uses DOM labels — never click Subscribe if already subscribed.
    """
    try:
        if platform == "youtube":
            # Already subscribed / joined
            for sel in (
                "button[aria-label*='Subscribed' i]",
                "button[aria-label*='Unsubscribe' i]",
                "yt-button-shape button[aria-label*='Subscribed' i]",
            ):
                loc = page.locator(sel)
                if loc.count():
                    return "subscribed"
            # Visible Subscribe button
            for name in ["Subscribe", "সাবস্ক্রাইব"]:
                btn = page.get_by_role("button", name=name)
                if btn.count():
                    label = ""
                    try:
                        label = (btn.first.get_attribute("aria-label") or btn.first.inner_text() or "").lower()
                    except Exception:
                        label = name.lower()
                    if "subscribed" in label or "unsubscribe" in label:
                        return "subscribed"
                    if "subscribe" in label or name.lower() in label or True:
                        # role name matched Subscribe
                        return "not_subscribed"
            return "unknown"
        # Facebook page follow
        for sel in (
            "[aria-label='Following']",
            "[aria-label='ফলো করছেন']",
            "div[aria-label*='Following' i]",
        ):
            if page.locator(sel).count():
                return "subscribed"
        for name in ["Follow", "ফলো", "Like", "লাইক"]:
            btn = page.get_by_role("button", name=name)
            if btn.count():
                return "not_subscribed"
        return "unknown"
    except Exception as exc:
        logger.debug("subscription_status: %s", exc)
        return "unknown"


def simulate_notification_interaction(page, platform: str) -> str:
    """Simulate human interaction with notifications: click/check or ignore."""
    action = "ignore" if random.random() < 0.5 else "click"
    if action == "ignore":
        human_sleep(0.8, 1.8)
        return "notification_ignored"

    try:
        if platform == "youtube":
            for sel in (
                "button[aria-label*='Notifications' i]",
                "yt-icon-button#notification-button",
                "button.ytd-notification-topbar-button-renderer",
            ):
                bell = page.locator(sel)
                if bell.count():
                    human_click(page, bell.first)
                    human_sleep(1.2, 2.5)
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    human_sleep(0.4, 1.0)
                    return "notification_checked"
        elif platform == "facebook":
            for sel in (
                "div[aria-label*='Notifications' i]",
                "div[aria-label*='বিজ্ঞপ্তি' i]",
                "a[href*='/notifications/']",
            ):
                bell = page.locator(sel)
                if bell.count():
                    human_click(page, bell.first)
                    human_sleep(1.2, 2.5)
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    human_sleep(0.4, 1.0)
                    return "notification_checked"
    except Exception as exc:
        logger.debug("simulate_notification_interaction: %s", exc)
    return "notification_ignored"


def ensure_subscribed(page, platform: str, hub_url: str, caps: SessionCaps) -> str:
    """Subscribe/follow once if needed. Returns status after attempt."""
    status = subscription_status(page, platform)
    if status == "subscribed" or store.engage_done(platform, hub_url, "follow"):
        if status == "subscribed" and not store.engage_done(platform, hub_url, "follow"):
            store.mark_engage(platform, hub_url, "follow")
        return "subscribed"
    if daily_subscribes_count() >= MAX_DAILY_SUBSCRIBES:
        logger.info("Daily subscribe cap of %d reached; skipping subscribe", MAX_DAILY_SUBSCRIBES)
        return "daily_cap_reached"
    if caps.subscribes >= MAX_SUBSCRIBE_PER_SESSION:
        return status
    if status != "not_subscribed" and status != "unknown":
        return status

    # Hesitation like a human deciding to follow
    reading_pause()
    human_sleep(0.8, 2.2)

    def _click_sub() -> bool:
        if platform == "youtube":
            for name in ["Subscribe", "সাবস্ক্রাইব"]:
                btn = page.get_by_role("button", name=name)
                if btn.count():
                    # Guard: skip if label says Subscribed
                    try:
                        lab = (btn.first.get_attribute("aria-label") or "").lower()
                        if "subscribed" in lab or "unsubscribe" in lab:
                            return True
                    except Exception:
                        pass
                    return human_click(page, btn.first)
            return False
        for name in ["Follow", "ফলো", "Like Page"]:
            btn = page.get_by_role("button", name=name)
            if btn.count():
                return human_click(page, btn.first)
        return False

    ok = _safe(_click_sub)
    human_sleep(1.0, 2.5)
    # Dismiss possible notification popup
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    after = subscription_status(page, platform)
    if ok or after == "subscribed":
        store.mark_engage(platform, hub_url, "follow")
        caps.subscribes += 1
        increment_daily_subscribes()
        activity_log.log_action(platform=platform, action="subscribe", url=hub_url, detail="admin_promo hub")
        return "subscribed"
    activity_log.log_action(platform=platform, action="subscribe_skip", url=hub_url, ok=False, detail=after)
    return after


def open_latest_video(page, platform: str) -> Optional[str]:
    """Open the newest video/post from a channel/page. Returns video URL or None."""
    try:
        if platform == "youtube":
            # Prefer Videos tab if present
            for tab in ["Videos", "ভিডিও", "Shorts"]:
                t = page.get_by_role("tab", name=tab)
                if t.count() and random.random() < 0.7:
                    human_click(page, t.first)
                    human_sleep(1.2, 2.8)
                    break
            thumbs = page.locator(
                "ytd-rich-item-renderer a#video-title-link, "
                "ytd-grid-video-renderer a#video-title, "
                "ytd-rich-grid-media a#video-title-link, "
                "a#video-title-link, a#thumbnail[href*='watch']"
            )
            if not thumbs.count():
                return None
            # Latest ≈ first few
            idx = 0 if random.random() < 0.75 else random.randint(0, min(2, thumbs.count() - 1))
            human_click(page, thumbs.nth(idx))
            human_sleep(2.0, 4.0)
            return page.url
        # Facebook page — click first video/reel tile
        tiles = page.locator(
            "a[href*='/videos/'], a[href*='/reel/'], a[href*='/watch/']"
        )
        if not tiles.count():
            # Fall back: scroll then retry once
            aimless_scroll(page, bursts=2)
            tiles = page.locator("a[href*='/videos/'], a[href*='/reel/']")
        if not tiles.count():
            return None
        human_click(page, tiles.first)
        human_sleep(2.0, 4.2)
        return page.url
    except Exception as exc:
        logger.debug("open_latest_video: %s", exc)
        return None


def open_random_video(page, platform: str) -> Optional[str]:
    try:
        if platform == "youtube":
            thumbs = page.locator(
                "ytd-rich-item-renderer a#video-title-link, "
                "ytd-grid-video-renderer a#video-title, "
                "a#video-title-link"
            )
            n = thumbs.count()
            if n < 1:
                return None
            idx = random.randint(0, min(n - 1, 11))
            human_click(page, thumbs.nth(idx))
            human_sleep(1.8, 3.8)
            return page.url
        tiles = page.locator("a[href*='/videos/'], a[href*='/reel/']")
        n = tiles.count()
        if n < 1:
            return None
        idx = random.randint(0, min(n - 1, 8))
        human_click(page, tiles.nth(idx))
        human_sleep(1.8, 3.8)
        return page.url
    except Exception as exc:
        logger.debug("open_random_video: %s", exc)
        return None


def watch_human(page, platform: str, *, seconds: float, deadline: float) -> None:
    """Chunked watch with mouse/scroll — stops early on budget/captcha."""
    end = min(time.time() + max(8.0, seconds), deadline - 5)
    while time.time() < end:
        if captcha_is_locked():
            break
        if random.random() < 0.35:
            aimless_scroll(page, bursts=1)
        if platform == "facebook" and random.random() < 0.3:
            try:
                page.keyboard.press("ArrowDown")
            except Exception:
                pass
        try:
            page.mouse.move(random.randint(160, 1000), random.randint(140, 680))
        except Exception:
            pass
        # Occasional "pause thinking"
        if random.random() < 0.12:
            human_sleep(2.5, 6.0)
        else:
            human_sleep(3.5, 9.5)


def go_back_safe(page) -> None:
    try:
        page.go_back(wait_until="domcontentloaded", timeout=25000)
        human_sleep(1.0, 2.2)
    except Exception:
        try:
            page.keyboard.press("Alt+ArrowLeft")
            human_sleep(1.0, 2.0)
        except Exception:
            pass


def maybe_engage_video(
    page,
    platform: str,
    video_url: str,
    *,
    title: str,
    caps: SessionCaps,
    deadline: float,
    allow_comment: bool,
    allow_share: bool,
    force_like: bool = False,
    force_comment: bool = False,
) -> List[str]:
    """Like / comment / share with local de-dupe + session caps."""
    done: List[str] = []
    if not _deadline_ok(deadline, 15):
        return done

    # Like (guaranteed if force_like is set, else random human probability)
    should_like = force_like or (random.random() < 0.55)
    if (
        caps.likes < MAX_LIKES_PER_SESSION
        and not store.engage_done(platform, video_url, "like")
        and should_like
    ):
        if _safe(lambda: do_like(page, platform, force_prob=1.0 if force_like else 0.95)):
            store.mark_engage(platform, video_url, "like")
            caps.likes += 1
            done.append("like")
            activity_log.log_action(platform=platform, action="like", url=video_url, title=title)
            human_sleep(0.6, 1.8)

    # Comment (guaranteed positive if force_comment is set, else sparse)
    should_comment = force_comment or (allow_comment and random.random() < 0.42)
    if (
        (allow_comment or force_comment)
        and caps.comments < MAX_COMMENTS_PER_SESSION
        and not store.engage_done(platform, video_url, "comment")
        and should_comment
        and _deadline_ok(deadline, 30)
    ):
        prepared = prepare_comment({"title": title, "description": ""})
        if _safe(lambda: do_comment(page, platform, prepared["text"], force_prob=1.0 if force_comment else 0.95)):
            store.mark_engage(platform, video_url, "comment")
            caps.comments += 1
            done.append("comment")
            activity_log.log_action(
                platform=platform,
                action="comment",
                url=video_url,
                title=title,
                detail=prepared["text"][:160],
                meta={"will_edit": prepared.get("will_edit")},
            )
            if prepared.get("will_edit") and _deadline_ok(deadline, 25):
                human_sleep(6.0, 16.0)  # human notices typo later
                if _safe(
                    lambda: edit_own_comment(page, platform, prepared["text"], prepared["corrected"]),
                    retries=1,
                ):
                    done.append("comment_edit")
                    activity_log.log_action(
                        platform=platform,
                        action="comment_edit",
                        url=video_url,
                        detail=f"→ {prepared['corrected'][:80]}",
                    )

    # Share (very sparse — mostly copy-link + dismiss)
    if (
        allow_share
        and caps.shares < MAX_SHARES_PER_SESSION
        and not store.engage_done(platform, video_url, "share")
        and random.random() < 0.22
        and _deadline_ok(deadline, 20)
    ):
        if _safe(lambda: do_share(page, platform, force_prob=0.95)):
            store.mark_engage(platform, video_url, "share")
            caps.shares += 1
            done.append("share")
            activity_log.log_action(platform=platform, action="share", url=video_url, title=title)

    return done


def engage_promo_hub(
    page,
    hub: Dict[str, Any],
    *,
    caps: SessionCaps,
    deadline: float,
) -> Dict[str, Any]:
    """
    Full FSM for one admin promo channel/page:
      subscribe if needed → latest video watch+engage →
      or random 1–2 videos if already complete → back.
    """
    platform = (hub.get("platform") or "").lower()
    hub_url = hub.get("url") or ""
    title = hub.get("title") or ""
    actions: List[str] = []

    if not hub_url or not _deadline_ok(deadline, 30):
        return {"ok": False, "skipped": True, "reason": "budget"}

    page.goto(hub_url, wait_until="domcontentloaded", timeout=90000)
    human_sleep(1.6, 3.8)
    assert_no_captcha(page, platform=platform, url=hub_url)
    reading_pause()
    aimless_scroll(page, bursts=random.randint(1, 3))

    # If URL is already a video, treat as video engage only
    if hub.get("kind") == "video":
        watch_human(page, platform, seconds=random.uniform(35, 110), deadline=deadline)
        acts = maybe_engage_video(
            page,
            platform,
            page.url,
            title=title,
            caps=caps,
            deadline=deadline,
            allow_comment=True,
            allow_share=True,
        )
        actions.extend(acts)
        activity_log.log_action(
            platform=platform,
            action="watch_promo_video",
            url=page.url,
            title=title,
            detail=",".join(acts) or "watch",
        )
        return {"ok": True, "actions": actions, "mode": "direct_video"}

    channel_type = str(hub.get("channel_type") or ("A" if hub.get("is_favorite") else "A")).upper()

    if channel_type == "B":
        # Type B: Secondary / random channel
        # 1. Simulate notification ignore or click
        notif_state = simulate_notification_interaction(page, platform)
        actions.append(f"notif:{notif_state}")
        activity_log.log_action(
            platform=platform,
            action="notification_sim",
            url=hub_url,
            title=title,
            detail=notif_state,
        )

        # 2. Occasional casual video watch
        if random.random() < 0.65 and _deadline_ok(deadline, 25):
            vurl = open_random_video(page, platform) or open_latest_video(page, platform)
            if vurl:
                assert_no_captcha(page, platform=platform, url=vurl)
                watch_sec = random.uniform(15, 45)
                watch_human(page, platform, seconds=watch_sec, deadline=deadline)
                acts = maybe_engage_video(
                    page,
                    platform,
                    vurl,
                    title=title,
                    caps=caps,
                    deadline=deadline,
                    allow_comment=random.random() < 0.2,
                    allow_share=False,
                    force_like=False,
                    force_comment=False,
                )
                actions.extend(acts)
                activity_log.log_action(
                    platform=platform,
                    action="watch_type_b",
                    url=vurl,
                    title=title,
                    detail=f"watch≈{int(watch_sec)}s;{','.join(acts) or 'none'}",
                )
                go_back_safe(page)
        else:
            aimless_scroll(page, bursts=random.randint(1, 3))
            activity_log.log_action(
                platform=platform,
                action="browse_type_b",
                url=hub_url,
                title=title,
                detail="casual_scroll",
            )
        return {"ok": True, "actions": actions, "channel_type": "B"}

    # Type A: Favorite channel — subscribe if needed + daily 1 watch, like, positive comment
    sub = ensure_subscribed(page, platform, hub_url, caps)
    actions.append(f"sub:{sub}")

    today = date.today().isoformat()
    latest_key = f"latest_play_{today}"
    fully_done = (
        store.engage_done(platform, hub_url, "follow")
        and store.engage_done(platform, hub_url, "latest_comment")
        and store.engage_done(platform, hub_url, "latest_share")
        and store.engage_done(platform, hub_url, latest_key)
    )

    videos_opened = 0

    if not fully_done and _deadline_ok(deadline, 40):
        # Path A: latest video focus (guarantee view, like, positive comment)
        vurl = open_latest_video(page, platform)
        if vurl:
            videos_opened += 1
            assert_no_captcha(page, platform=platform, url=vurl)
            watch_sec = random.choice(
                [
                    random.uniform(45, 75),
                    random.uniform(75, 110),
                    random.uniform(110, 180),
                ]
            )
            watch_human(page, platform, seconds=watch_sec, deadline=deadline)
            acts = maybe_engage_video(
                page,
                platform,
                vurl,
                title=title or "latest",
                caps=caps,
                deadline=deadline,
                allow_comment=True,
                allow_share=not store.engage_done(platform, hub_url, "latest_share"),
                force_like=True,
                force_comment=True,
            )
            actions.extend(acts)
            if "comment" in acts:
                store.mark_engage(platform, hub_url, "latest_comment")
            if "share" in acts:
                store.mark_engage(platform, hub_url, "latest_share")
            store.mark_engage(platform, hub_url, latest_key)
            activity_log.log_action(
                platform=platform,
                action="watch_latest",
                url=vurl,
                title=title,
                detail=f"watch≈{int(watch_sec)}s;{','.join(acts) or 'none'}",
            )
            go_back_safe(page)
        else:
            activity_log.log_action(
                platform=platform,
                action="latest_not_found",
                url=hub_url,
                title=title,
                ok=False,
            )
    else:
        # Path B: already engaged — random 1–2 videos, human browse
        n_rand = random.randint(1, 2)
        for _ in range(n_rand):
            if videos_opened >= MAX_VIDEOS_PER_HUB or not _deadline_ok(deadline, 35):
                break
            # Ensure on hub
            if hub_url.rstrip("/") not in (page.url or "").rstrip("/"):
                try:
                    page.goto(hub_url, wait_until="domcontentloaded", timeout=60000)
                    human_sleep(1.2, 2.8)
                except Exception:
                    break
            aimless_scroll(page, bursts=random.randint(1, 2))
            vurl = open_random_video(page, platform)
            if not vurl:
                break
            videos_opened += 1
            assert_no_captcha(page, platform=platform, url=vurl)
            # Random duration; sometimes "watch almost all"
            if random.random() < 0.25:
                watch_sec = random.uniform(120, 240)
            else:
                watch_sec = random.uniform(20, 75)
            watch_human(page, platform, seconds=watch_sec, deadline=deadline)
            acts = maybe_engage_video(
                page,
                platform,
                vurl,
                title=title,
                caps=caps,
                deadline=deadline,
                allow_comment=random.random() < 0.35,
                allow_share=False,  # don't spam share on random
            )
            actions.extend(acts)
            activity_log.log_action(
                platform=platform,
                action="watch_random",
                url=vurl,
                title=title,
                detail=f"watch≈{int(watch_sec)}s;{','.join(acts) or 'none'}",
            )
            go_back_safe(page)
            human_sleep(1.0, 3.0)

    return {
        "ok": True,
        "actions": actions,
        "videos": videos_opened,
        "mode": "random" if fully_done else "latest",
        "url": hub_url,
    }


def scroll_reels(page, *, seconds: float, deadline: float) -> Dict[str, Any]:
    """Human-like Facebook Reels scroll — watch, occasional like, rarely comment."""
    if not _deadline_ok(deadline, 20):
        return {"ok": False, "skipped": True}
    try:
        page.goto("https://www.facebook.com/reel/", wait_until="domcontentloaded", timeout=60000)
        human_sleep(2.0, 4.0)
        assert_no_captcha(page, platform="facebook", url=page.url)
    except CaptchaBlockedError:
        raise
    except Exception as exc:
        activity_log.log_action(platform="facebook", action="reels_open_fail", detail=str(exc)[:160], ok=False)
        return {"ok": False, "error": str(exc)[:120]}

    end = min(time.time() + max(20.0, seconds), deadline - 5)
    liked = 0
    scrolled = 0
    while time.time() < end and not captcha_is_locked():
        # Watch current reel
        human_sleep(4.0, 14.0)
        if random.random() < 0.18 and liked < 2:
            if _safe(lambda: do_like(page, "facebook", force_prob=0.9), retries=1):
                liked += 1
                activity_log.log_action(platform="facebook", action="reels_like", url=page.url)
        # Next reel
        try:
            page.keyboard.press("ArrowDown")
            scrolled += 1
        except Exception:
            aimless_scroll(page, bursts=1)
        human_sleep(0.8, 2.5)
        if random.random() < 0.08:
            # human distraction pause
            human_sleep(3.0, 8.0)

    activity_log.log_action(
        platform="facebook",
        action="reels_scroll",
        detail=f"scrolled={scrolled} liked={liked} sec≈{int(seconds)}",
    )
    return {"ok": True, "scrolled": scrolled, "liked": liked}


def engage_peer_video(
    page,
    item: Dict[str, Any],
    *,
    caps: SessionCaps,
    deadline: float,
) -> Dict[str, Any]:
    """Direct peer customer video — lighter engage than promo hubs."""
    platform = (item.get("platform") or "").lower()
    url = item.get("url") or ""
    title = item.get("title") or ""
    if not url or not _deadline_ok(deadline, 25):
        return {"ok": False, "skipped": True}
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    human_sleep(1.5, 3.5)
    assert_no_captcha(page, platform=platform, url=url)
    reading_pause()
    watch_human(page, platform, seconds=random.uniform(30, 95), deadline=deadline)
    # Soft subscribe only sometimes on peer channel
    if random.random() < 0.25 and caps.subscribes < MAX_SUBSCRIBE_PER_SESSION:
        ensure_subscribed(page, platform, url, caps)
    acts = maybe_engage_video(
        page,
        platform,
        page.url,
        title=title,
        caps=caps,
        deadline=deadline,
        allow_comment=True,
        allow_share=random.random() < 0.3,
    )
    activity_log.log_action(
        platform=platform,
        action="watch_peer",
        url=page.url,
        title=title,
        detail=",".join(acts) or "watch",
        meta={"source": item.get("source")},
    )
    return {"ok": True, "actions": acts, "url": page.url}
