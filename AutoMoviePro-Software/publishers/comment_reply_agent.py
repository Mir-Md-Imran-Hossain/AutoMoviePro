"""
Own-video comment reply agent.

Replies to comments on videos we uploaded (posts table), not the promo engage farm.
Browser path for YouTube watch-page comments; Facebook best-effort composer reply.
"""
from __future__ import annotations

import logging
import random
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app import db as store
from publishers.upload_meta import youtube_video_id

logger = logging.getLogger(__name__)

AUTO_REPLY_ENABLED_KEY = "auto_reply_enabled"
LAST_AUTO_REPLY_SCAN_KEY = "last_auto_reply_scan_at"


def is_auto_reply_enabled() -> bool:
    """Returns True if the auto-reply loop is enabled by user."""
    return store.get_meta(AUTO_REPLY_ENABLED_KEY, "1") in ("1", "true", "True", "yes")


def set_auto_reply_enabled(enabled: bool) -> None:
    """Toggles auto-reply system ON or OFF."""
    store.set_meta(AUTO_REPLY_ENABLED_KEY, "1" if enabled else "0")


def get_auto_reply_status() -> Dict[str, Any]:
    """Returns current toggle state, last scan timestamp, total count, and recent reply history."""
    try:
        recent = store.list_recent_post_messages(limit=25)
    except Exception:
        recent = []
    return {
        "enabled": is_auto_reply_enabled(),
        "last_scan": store.get_meta(LAST_AUTO_REPLY_SCAN_KEY, "Never"),
        "total_replies_sent": len(recent),
        "recent_replies": recent,
    }


def detect_comment_language(text: str, default: str = "en") -> str:
    """Detects primary language of comment using character scripts."""
    if not text:
        return default
    # Bengali unicode range [\u0980-\u09FF]
    if any("\u0980" <= ch <= "\u09FF" for ch in text):
        return "bn"
    # Arabic / Urdu [\u0600-\u06FF]
    if any("\u0600" <= ch <= "\u06FF" for ch in text):
        return "ar"
    # Hindi / Devanagari [\u0900-\u097F]
    if any("\u0900" <= ch <= "\u097F" for ch in text):
        return "hi"
    return default


def simulate_typing_delay(reply_text: str, min_delay: float = 1.0, max_delay: float = 4.0) -> float:
    """Calculates human-like typing delay based on character count and pauses."""
    length = len(reply_text or "")
    char_delay = length * random.uniform(0.035, 0.065)
    delay = max(min_delay, min(max_delay, char_delay))
    try:
        from publishers.human_browser import human_sleep
        human_sleep(delay * 0.4, delay)
    except Exception:
        import time
        time.sleep(min(0.2, delay * 0.05))
    return delay


def draft_comment_reply(
    comment_text: str = "",
    video_context: str = "",
    video_title: str = "",
    channel_name: str = "AutoMovie Pro",
    lang_code: str = "en",
    niche: str = "",
    author_name: str = "",
    **kwargs: Any,
) -> str:
    """Human creator reply with natural tone and context-awareness — strictly avoids robotic AI formulas."""
    comment = (comment_text or kwargs.get("comment") or "").strip()
    title = (video_title or kwargs.get("title") or "").strip() or "this video"
    v_ctx = video_context or kwargs.get("context") or ""
    # Auto-detect exact language from comment text or fallback to lang_code
    lang = detect_comment_language(comment, default=(lang_code or "en").lower()[:2])
    if not comment:
        return ""

    context_snip = f"\nVideo Context / Script Summary: {v_ctx[:300]}" if v_ctx else ""

    prompt = (
        f"You are the creator of '{channel_name}', producing high-quality videos in the {niche or 'educational'} niche.\n"
        f"Video title: {title}{context_snip}\n"
        f"Viewer comment: {comment}\n"
        f"Language to reply in: {lang}\n"
        "Reply as a warm, enthusiastic human creator in 1-2 concise sentences.\n"
        "STRICT RULES:\n"
        "- Reply in the EXACT SAME language as the viewer's comment.\n"
        "- Ground your response directly in the video title and context.\n"
        "- NEVER say 'As an AI' or 'Thank you for commenting'.\n"
        "- NEVER use robotic cliches.\n"
        "- Respond naturally to their specific comment or question.\n"
        "Reply text only:"
    )
    try:
        from pipeline.llm_router import chat_text

        out = chat_text(prompt, purpose="agent")
        text = str((out or {}).get("text") or "").strip()
        text = re.sub(r"^['\"]|['\"]$", "", text)
        # Guard against AI tells in generated text
        if "as an ai" not in text.lower() and len(text) >= 8:
            return text[:400]
    except Exception as exc:
        logger.debug("comment LLM fallback: %s", exc)

    # Local natural human creator fallbacks by language
    if lang == "bn":
        if any(x in comment.lower() for x in ("price", "মূল্য", "কত", "cost", "কোথায়", "পাব")):
            return "বিস্তারিত জানতে ডেসক্রিপশন বক্স চেক করতে পারেন, সাথে থাকার জন্য অনেক ধন্যবাদ!"
        if video_context:
            return f"অনেক ধন্যবাদ! {title}-এর মূল বিষয়বস্তু নিয়ে আপনার দারুণ মতামতের জন্য কৃতজ্ঞ। সাথে থাকুন!"
        return "অনেক ধন্যবাদ আপনার সুন্দর মতামতের জন্য! পরবর্তী ভিডিওগুলোতে আরও দারুণ বিষয় নিয়ে আসছি।"
    elif lang == "ar":
        return f"شكراً جزيلاً لمشاركتك رأيك القيّم حول {title}! نسعد دائماً بوجودك معنا."
    elif lang == "hi":
        return f"आपके विचार साझा करने के लिए बहुत-बहुत धन्यवाद! {title} से जुड़े रहने के लिए आभार।"

    # Default English fallback
    if any(x in comment.lower() for x in ("price", "cost", "buy", "where", "how to")):
        return f"Appreciate you tuning in! Be sure to check the description for full background details on {title}."
    return f"Really glad this resonated with you! More deep dives like {title} coming up tomorrow."


def _already_replied(post_id: int, comment_key: str) -> bool:
    if store.engage_done("comment_reply", f"post:{post_id}", comment_key):
        return True
    return False


def _mark_replied(post_id: int, comment_key: str) -> None:
    store.mark_engage("comment_reply", f"post:{post_id}", comment_key)


def _collect_youtube_comments(page, limit: int = 8) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    try:
        page.evaluate("window.scrollBy(0, 1200)")
    except Exception:
        pass
    try:
        from publishers.human_browser import human_sleep as hs
        hs(1.5, 2.5)
    except Exception:
        pass
    threads = page.locator("ytd-comment-thread-renderer")
    try:
        n = min(threads.count(), limit)
    except Exception:
        n = 0
    for i in range(n):
        t = threads.nth(i)
        try:
            author = ""
            text = ""
            a = t.locator("#author-text, a#author-text")
            if a.count():
                author = (a.first.inner_text() or "").strip()
            c = t.locator("#content-text, yt-formatted-string#content-text")
            if c.count():
                text = (c.first.inner_text() or "").strip()
            if text:
                out.append({"author": author or "viewer", "text": text[:500]})
        except Exception:
            continue
    return out


def _reply_on_youtube_thread(page, thread_index: int, reply: str) -> bool:
    from publishers.human_browser import human_click, human_paste_text, human_sleep

    threads = page.locator("ytd-comment-thread-renderer")
    if thread_index >= threads.count():
        return False
    t = threads.nth(thread_index)
    try:
        reply_btn = t.get_by_text("Reply", exact=False)
        if reply_btn.count():
            human_click(page, reply_btn.first)
            human_sleep(0.6, 1.2)
        box = t.locator("#contenteditable-root, div[contenteditable='true']")
        if not box.count():
            box = page.locator("#contenteditable-root, div[contenteditable='true']")
        if not box.count():
            return False
        human_paste_text(page, box.first, reply[:400])
        human_sleep(0.4, 0.8)
        for label in ("Reply", "উত্তর", "Comment"):
            btn = t.get_by_role("button", name=label)
            if btn.count() and human_click(page, btn.first):
                return True
        submit = page.locator("#submit-button, ytd-button-renderer#submit-button")
        if submit.count() and human_click(page, submit.first):
            return True
    except Exception as exc:
        logger.debug("yt reply failed: %s", exc)
        return False
    return False


def reply_youtube_post(post: Dict[str, Any], channel: Dict[str, Any], *, max_replies: int = 3) -> Dict[str, Any]:
    url = str(post.get("remote_url") or "")
    lang = str(post.get("lang_code") or "en")

    if url.startswith("dry-run://"):
        comment_sample = "Incredible breakdown, learned a lot from this!"
        key = f"dry_yt_user|{comment_sample}"
        if not _already_replied(int(post["id"]), key):
            reply = draft_comment_reply(
                video_title=str(post.get("title") or ""),
                comment_text=comment_sample,
                channel_name=str(channel.get("youtube_name") or "AutoMovie Pro"),
                lang_code=lang,
                niche=str(channel.get("niche") or ""),
            )
            store.add_post_message(
                int(post["id"]),
                platform="youtube",
                author="dry_yt_user",
                message=comment_sample,
                reply=reply,
                lang_code=lang,
            )
            _mark_replied(int(post["id"]), key)
            return {"ok": True, "replied": 1, "dry_run": True}
        return {"ok": True, "replied": 0, "dry_run": True}

    vid = youtube_video_id(url)
    if not vid:
        return {"ok": False, "error": "no_video_id", "replied": 0}

    paths = None
    try:
        from publishers.session_vault import paths_for_channel
        paths = paths_for_channel("youtube", channel, lang_code=lang)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "replied": 0}
    store_path = paths["storage_state"]
    profile = paths["user_data_dir"]
    from pathlib import Path

    if not (Path(store_path).exists() or (Path(profile) / "Default").exists()):
        return {"ok": False, "error": "youtube_session_missing", "replied": 0}

    replied = 0
    from publishers.stealth_session import stealth_browser
    from publishers.human_browser import assert_no_captcha, human_sleep

    watch = f"https://www.youtube.com/watch?v={vid}"
    with stealth_browser(storage_state=store_path, user_data_dir=profile, headless=False) as (
        _pw,
        _b,
        page,
        engine,
    ):
        logger.info("Comment reply via %s for %s", engine, vid)
        page.goto(watch, wait_until="domcontentloaded", timeout=90000)
        human_sleep(2.0, 3.5)
        assert_no_captcha(page, platform="youtube", url=page.url)
        comments = _collect_youtube_comments(page, limit=10)
        for idx, c in enumerate(comments):
            if replied >= max_replies:
                break
            key = re.sub(r"\s+", " ", f"{c.get('author')}|{c.get('text')}")[:180]
            if _already_replied(int(post["id"]), key):
                continue
            reply = draft_comment_reply(
                video_title=str(post.get("title") or ""),
                comment_text=str(c.get("text") or ""),
                channel_name=str(channel.get("youtube_name") or "AutoMovie Pro"),
                lang_code=lang,
                niche=str(channel.get("niche") or ""),
            )
            if not reply:
                continue
            if _reply_on_youtube_thread(page, idx, reply):
                store.add_post_message(
                    int(post["id"]),
                    platform="youtube",
                    author=str(c.get("author") or ""),
                    message=str(c.get("text") or ""),
                    reply=reply,
                    lang_code=lang,
                )
                _mark_replied(int(post["id"]), key)
                replied += 1
                human_sleep(1.5, 3.0)
    return {"ok": True, "replied": replied, "video_id": vid, "scanned": len(comments)}


def _collect_tiktok_comments(page, limit: int = 8) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    try:
        page.evaluate("window.scrollBy(0, 800)")
    except Exception:
        pass
    try:
        from publishers.human_browser import human_sleep as hs
        hs(1.5, 2.5)
    except Exception:
        pass
    items = page.locator("[data-e2e='comment-item'], div[class*='CommentItem'], div[class*='DivCommentItemContainer']")
    try:
        n = min(items.count(), limit)
    except Exception:
        n = 0
    for i in range(n):
        item = items.nth(i)
        try:
            author = ""
            text = ""
            a = item.locator("[data-e2e='comment-user-username'], span[class*='SpanUserNameText'], a[class*='UserLink']")
            if a.count():
                author = (a.first.inner_text() or "").strip()
            c = item.locator("[data-e2e='comment-level-1'], p[class*='PCommentText'], span[class*='SpanCommentText']")
            if c.count():
                text = (c.first.inner_text() or "").strip()
            if text:
                out.append({"author": author or "tiktok_user", "text": text[:500]})
        except Exception:
            continue
    return out


def _reply_on_tiktok_thread(page, item_index: int, reply: str) -> bool:
    from publishers.human_browser import human_click, human_paste_text, human_sleep

    items = page.locator("[data-e2e='comment-item'], div[class*='CommentItem'], div[class*='DivCommentItemContainer']")
    if item_index >= items.count():
        return False
    item = items.nth(item_index)
    try:
        reply_btn = item.locator("[data-e2e='comment-reply-1'], span:has-text('Reply'), span:has-text('উত্তর')")
        if reply_btn.count():
            human_click(page, reply_btn.first)
            human_sleep(0.6, 1.2)
        box = page.locator("div[contenteditable='true'], [data-e2e='comment-input'], textarea[placeholder*='comment']")
        if not box.count():
            box = item.locator("div[contenteditable='true'], textarea")
        if not box.count():
            return False
        human_paste_text(page, box.first, reply[:300])
        human_sleep(0.4, 0.8)
        submit = page.locator("[data-e2e='comment-post'], div:has-text('Post'), button:has-text('Post'), button:has-text('পোস্ট')")
        if submit.count() and human_click(page, submit.first):
            return True
    except Exception as exc:
        logger.debug("tiktok reply failed: %s", exc)
        return False
    return False


def reply_tiktok_post(post: Dict[str, Any], channel: Dict[str, Any], *, max_replies: int = 3) -> Dict[str, Any]:
    url = str(post.get("remote_url") or "")
    if not url:
        return {"ok": False, "error": "no_video_url", "replied": 0}
    lang = str(post.get("lang_code") or "en")

    if url.startswith("dry-run://"):
        comment_sample = "Great short! Very informative."
        key = f"dry_user|{comment_sample}"
        if not _already_replied(int(post["id"]), key):
            reply = draft_comment_reply(
                video_title=str(post.get("title") or ""),
                comment_text=comment_sample,
                channel_name=str(channel.get("tiktok_name") or "AutoMovie Pro"),
                lang_code=lang,
                niche=str(channel.get("niche") or ""),
            )
            store.add_post_message(
                int(post["id"]),
                platform="tiktok",
                author="dry_user",
                message=comment_sample,
                reply=reply,
                lang_code=lang,
            )
            _mark_replied(int(post["id"]), key)
            return {"ok": True, "replied": 1, "dry_run": True}
        return {"ok": True, "replied": 0, "dry_run": True}

    paths = None
    try:
        from publishers.session_vault import paths_for_channel
        paths = paths_for_channel("tiktok", channel, lang_code=lang)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "replied": 0}

    store_path = paths["storage_state"]
    profile = paths["user_data_dir"]
    from pathlib import Path
    if not (Path(store_path).exists() or (Path(profile) / "Default").exists()):
        return {"ok": False, "error": "tiktok_session_missing", "replied": 0}

    replied = 0
    from publishers.stealth_session import stealth_browser
    from publishers.human_browser import assert_no_captcha, human_sleep

    with stealth_browser(storage_state=store_path, user_data_dir=profile, headless=False) as (
        _pw, _b, page, engine,
    ):
        logger.info("TikTok comment reply via %s for %s", engine, url)
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        human_sleep(2.0, 3.5)
        assert_no_captcha(page, platform="tiktok", url=page.url)
        comments = _collect_tiktok_comments(page, limit=10)
        for idx, c in enumerate(comments):
            if replied >= max_replies:
                break
            key = re.sub(r"\s+", " ", f"{c.get('author')}|{c.get('text')}")[:180]
            if _already_replied(int(post["id"]), key):
                continue
            reply = draft_comment_reply(
                video_title=str(post.get("title") or ""),
                comment_text=str(c.get("text") or ""),
                channel_name=str(channel.get("tiktok_name") or "AutoMovie Pro"),
                lang_code=lang,
                niche=str(channel.get("niche") or ""),
            )
            if not reply:
                continue
            if _reply_on_tiktok_thread(page, idx, reply):
                store.add_post_message(
                    int(post["id"]),
                    platform="tiktok",
                    author=str(c.get("author") or ""),
                    message=str(c.get("text") or ""),
                    reply=reply,
                    lang_code=lang,
                )
                _mark_replied(int(post["id"]), key)
                replied += 1
                human_sleep(1.5, 3.0)
    return {"ok": True, "replied": replied, "url": url, "scanned": len(comments)}


def reply_facebook_post(post: Dict[str, Any], channel: Dict[str, Any], *, max_replies: int = 3) -> Dict[str, Any]:
    url = str(post.get("remote_url") or "")
    if not url:
        return {"ok": False, "error": "no_video_url", "replied": 0}
    lang = str(post.get("lang_code") or "en")

    if url.startswith("dry-run://"):
        comment_sample = "Loved this documentary. Very eye-opening!"
        key = f"dry_fb_user|{comment_sample}"
        if not _already_replied(int(post["id"]), key):
            reply = draft_comment_reply(
                video_title=str(post.get("title") or ""),
                comment_text=comment_sample,
                channel_name=str(channel.get("facebook_name") or "AutoMovie Pro"),
                lang_code=lang,
                niche=str(channel.get("niche") or ""),
            )
            store.add_post_message(
                int(post["id"]),
                platform="facebook",
                author="dry_fb_user",
                message=comment_sample,
                reply=reply,
                lang_code=lang,
            )
            _mark_replied(int(post["id"]), key)
            return {"ok": True, "replied": 1, "dry_run": True}
        return {"ok": True, "replied": 0, "dry_run": True}

    paths = None
    try:
        from publishers.session_vault import paths_for_channel
        paths = paths_for_channel("facebook", channel, lang_code=lang)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "replied": 0}

    store_path = paths["storage_state"]
    profile = paths["user_data_dir"]
    from pathlib import Path
    if not (Path(store_path).exists() or (Path(profile) / "Default").exists()):
        return {"ok": False, "error": "facebook_session_missing", "replied": 0}

    replied = 0
    from publishers.stealth_session import stealth_browser
    from publishers.human_browser import assert_no_captcha, human_sleep, human_paste_text

    with stealth_browser(storage_state=store_path, user_data_dir=profile, headless=False) as (
        _pw, _b, page, engine,
    ):
        logger.info("Facebook comment reply via %s for %s", engine, url)
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        human_sleep(2.0, 3.5)
        assert_no_captcha(page, platform="facebook", url=page.url)
        comments = []
        articles = page.locator("div[role='article']")
        n = min(articles.count(), 8)
        for i in range(n):
            art = articles.nth(i)
            try:
                txt = (art.inner_text() or "").strip()
                if txt and len(txt) > 3:
                    comments.append({"author": "fb_user", "text": txt[:300]})
            except Exception:
                continue
        for idx, c in enumerate(comments):
            if replied >= max_replies:
                break
            key = re.sub(r"\s+", " ", f"{c.get('author')}|{c.get('text')}")[:180]
            if _already_replied(int(post["id"]), key):
                continue
            reply = draft_comment_reply(
                video_title=str(post.get("title") or ""),
                comment_text=str(c.get("text") or ""),
                channel_name=str(channel.get("facebook_name") or "AutoMovie Pro"),
                lang_code=lang,
                niche=str(channel.get("niche") or ""),
            )
            if not reply:
                continue
            box = page.locator("div[role='textbox'], div[contenteditable='true']")
            if box.count():
                human_paste_text(page, box.first, reply[:300])
                page.keyboard.press("Enter")
                store.add_post_message(
                    int(post["id"]),
                    platform="facebook",
                    author=str(c.get("author") or ""),
                    message=str(c.get("text") or ""),
                    reply=reply,
                    lang_code=lang,
                )
                _mark_replied(int(post["id"]), key)
                replied += 1
                human_sleep(1.5, 3.0)
    return {"ok": True, "replied": replied, "url": url}


def run_comment_reply_pass(*, max_posts: int = 5, max_replies_each: int = 2) -> Dict[str, Any]:
    """Scheduler entry: reply to comments and messages on recent uploads across YouTube, Facebook, and TikTok."""
    from publishers.human_browser import captcha_is_locked

    if not is_auto_reply_enabled():
        return {"ok": True, "skipped": True, "reason": "auto_reply_disabled", "handled": 0}

    store.set_meta(LAST_AUTO_REPLY_SCAN_KEY, datetime.now().isoformat())

    if captcha_is_locked():
        return {"ok": False, "error": "captcha_locked", "posts": 0}
    channels = {int(c["id"]): c for c in store.list_channels() if c.get("id") is not None}
    posts = store.list_posts(80)
    results = []
    handled = 0
    for post in posts:
        if handled >= max_posts:
            break
        platform = str(post.get("platform") or "").lower()
        url = str(post.get("remote_url") or "").lower()
        ch = channels.get(int(post.get("channel_id") or 0))
        if not ch:
            continue

        try:
            res = None
            if "youtube" in platform or "youtube.com" in url or "youtu.be" in url:
                res = reply_youtube_post(post, ch, max_replies=max_replies_each)
            elif "tiktok" in platform or "tiktok.com" in url:
                res = reply_tiktok_post(post, ch, max_replies=max_replies_each)
            elif "facebook" in platform or "facebook.com" in url:
                res = reply_facebook_post(post, ch, max_replies=max_replies_each)

            if res is not None:
                results.append({"post_id": post.get("id"), "platform": platform, **res})
                if res.get("ok"):
                    handled += 1
        except Exception as exc:
            logger.exception("comment reply post %s failed", post.get("id"))
            results.append({"post_id": post.get("id"), "ok": False, "error": str(exc)})
    return {"ok": True, "handled": handled, "results": results}

