"""Automated navigation & social-engine style workflow tasks (A/B/C)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pipeline.e2e_ui.alert_handler import AlertHandler
from pipeline.e2e_ui.human_input import HumanInteractionManager

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    ok: bool
    task: str
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


# Selector packs — platforms evolve; override via task params.
YOUTUBE_SELECTORS = {
    "search_input": "input#search, input[name='search_query']",
    "search_button": "button#search-icon-legacy, button[aria-label*='Search' i]",
    "channel_link": "ytd-channel-renderer a#main-link, ytd-video-renderer a#video-title",
    "subscribe": "ytd-subscribe-button-renderer button, button[aria-label*='Subscribe' i]",
    "like": "like-button-view-model button, button[aria-label*='like this' i]",
    "comment_box": "#simplebox-placeholder, ytd-commentbox #contenteditable-root, div#contenteditable-root",
    "comment_submit": "#submit-button button, ytd-commentbox #submit-button",
    "notifications": "button[aria-label*='Notifications' i], yt-icon-button#button[aria-label*='Notifications' i]",
}

FACEBOOK_SELECTORS = {
    "search_input": "input[placeholder*='Search' i], input[aria-label*='Search' i]",
    "search_button": "div[aria-label='Search'] [role='button'], button[type='submit']",
    "page_link": "a[href*='facebook.com/']:not([href*='photo'])",
    "follow": "div[aria-label*='Follow' i], div[aria-label*='Like' i][role='button']",
    "like": "div[aria-label='Like'][role='button'], div[aria-label*='Like' i][role='button']",
    "comment_box": "div[aria-label*='Write a comment' i], div[contenteditable='true'][role='textbox']",
    "comment_submit": "div[aria-label='Comment'][role='button']",
    "notifications": "div[aria-label*='Notifications' i], a[aria-label*='Notifications' i]",
}


def _selectors_for(platform: str) -> Dict[str, str]:
    p = (platform or "").lower()
    if "face" in p or p == "fb":
        return dict(FACEBOOK_SELECTORS)
    return dict(YOUTUBE_SELECTORS)


class WorkflowTaskRunner:
    """
    Isolated functional automation tasks.

    Task A — Content Discovery (search → open → dwell)
    Task B — Engagement (subscribe/follow, like, comment)
    Task C — Inbox / Notifications
    """

    def __init__(
        self,
        page: Any,
        *,
        platform: str = "youtube",
        human: Optional[HumanInteractionManager] = None,
        alerts: Optional[AlertHandler] = None,
        selectors: Optional[Dict[str, str]] = None,
    ) -> None:
        self.page = page
        self.platform = platform
        self.human = human or HumanInteractionManager(page)
        self.alerts = alerts or AlertHandler(page, platform=platform)
        self.sel = _selectors_for(platform)
        if selectors:
            self.sel.update(selectors)

    def _gate(self) -> None:
        self.alerts.check_or_raise()

    # ============================================================== Task A
    def task_content_discovery(
        self,
        *,
        query: str,
        start_url: str = "",
        open_first_result: bool = True,
        watch_seconds: float = 25.0,
        result_index: int = 0,
    ) -> WorkflowResult:
        """Search for channels/pages, open media, simulate watch/view time."""
        task = "content_discovery"
        try:
            self._gate()
            if start_url:
                logger.info("Task A navigate %s", start_url)
                self.page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
                self.human.pause(1.0, 2.2)
                self._gate()

            search = self.sel["search_input"]
            self.human.wait_for(search, timeout_ms=30000)
            self.human.click(search)
            self.human.type_text(search, query, clear=True)
            self.human.pause(0.3, 0.8)
            # Prefer Enter (more human than hunting the icon every time)
            self.page.keyboard.press("Enter")
            self.human.pause(1.5, 3.0)
            self._gate()

            self.human.scroll(delta_y=600)
            opened = ""
            if open_first_result:
                link = self.page.locator(self.sel["channel_link"]).nth(max(0, result_index))
                link.wait_for(state="visible", timeout=30000)
                opened = link.get_attribute("href") or ""
                self.human.click(link)
                self.human.pause(1.2, 2.5)
                self._gate()
                self.human.watch_dwell(watch_seconds)

            return WorkflowResult(
                ok=True,
                task=task,
                detail=f"searched={query!r} opened={opened}",
                data={"query": query, "opened": opened, "watch_seconds": watch_seconds},
            )
        except Exception as exc:
            logger.exception("Task A failed")
            return WorkflowResult(ok=False, task=task, detail=str(exc)[:400])

    # ============================================================== Task B
    def task_engagement(
        self,
        *,
        subscribe: bool = False,
        like: bool = False,
        comment: str = "",
        page_url: str = "",
    ) -> WorkflowResult:
        """Follow/subscribe, like, leave a comment."""
        task = "engagement"
        actions: List[str] = []
        try:
            self._gate()
            if page_url:
                self.page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
                self.human.pause(1.0, 2.0)
                self._gate()

            if subscribe:
                try:
                    self.human.scroll(delta_y=200)
                    self.human.click(self.sel["subscribe"], timeout_ms=12000)
                    actions.append("subscribe")
                    self.human.pause(0.8, 1.6)
                except Exception as exc:
                    logger.warning("subscribe skip: %s", exc)
                    actions.append(f"subscribe_failed:{exc}")

            if like:
                try:
                    self.human.click(self.sel["like"], timeout_ms=12000)
                    actions.append("like")
                    self.human.pause(0.5, 1.2)
                except Exception as exc:
                    logger.warning("like skip: %s", exc)
                    actions.append(f"like_failed:{exc}")

            if (comment or "").strip():
                try:
                    box = self.sel["comment_box"]
                    self.human.scroll(toward=box)
                    self.human.click(box, timeout_ms=15000)
                    # contenteditable often needs type into focused element
                    self.human.pause(0.3, 0.7)
                    for ch in comment:
                        self.page.keyboard.type(ch, delay=0)
                        time.sleep(__import__("random").uniform(0.05, 0.16))
                    self.human.pause(0.4, 1.0)
                    try:
                        self.human.click(self.sel["comment_submit"], timeout_ms=8000)
                    except Exception:
                        self.page.keyboard.press("Control+Enter")
                    actions.append("comment")
                    self.human.pause(0.8, 1.5)
                except Exception as exc:
                    logger.warning("comment skip: %s", exc)
                    actions.append(f"comment_failed:{exc}")

            self._gate()
            ok = any(a in ("subscribe", "like", "comment") for a in actions)
            return WorkflowResult(
                ok=ok or not (subscribe or like or comment),
                task=task,
                detail=",".join(actions) or "noop",
                data={"actions": actions},
            )
        except Exception as exc:
            logger.exception("Task B failed")
            return WorkflowResult(ok=False, task=task, detail=str(exc)[:400])

    # ============================================================== Task C
    def task_inbox_notifications(
        self,
        *,
        open_panel: bool = True,
        mark_read_seconds: float = 4.0,
        reply_text: str = "",
        reply_box_selector: str = "",
    ) -> WorkflowResult:
        """Open notifications, skim updates, optional reply."""
        task = "inbox_notifications"
        try:
            self._gate()
            if open_panel:
                self.human.click(self.sel["notifications"], timeout_ms=15000)
                self.human.pause(1.0, 2.0)
                self._gate()

            # Skim / scroll notification list
            self.human.scroll(delta_y=500)
            self.human.watch_dwell(mark_read_seconds)

            replied = False
            if (reply_text or "").strip():
                box = reply_box_selector or self.sel.get("comment_box", "")
                if box:
                    try:
                        self.human.click(box, timeout_ms=10000)
                        self.human.type_text(box, reply_text, clear=False)
                        self.page.keyboard.press("Enter")
                        replied = True
                    except Exception as exc:
                        logger.warning("reply skip: %s", exc)

            self._gate()
            return WorkflowResult(
                ok=True,
                task=task,
                detail=f"panel_opened={open_panel} replied={replied}",
                data={"replied": replied},
            )
        except Exception as exc:
            logger.exception("Task C failed")
            return WorkflowResult(ok=False, task=task, detail=str(exc)[:400])

    def run_suite(self, *, query: str = "", start_url: str = "", **engage_kwargs: Any) -> List[WorkflowResult]:
        """Convenience: A → B → C with shared session."""
        results: List[WorkflowResult] = []
        if query or start_url:
            results.append(
                self.task_content_discovery(
                    query=query or "news",
                    start_url=start_url,
                    watch_seconds=float(engage_kwargs.pop("watch_seconds", 20)),
                )
            )
        results.append(self.task_engagement(**engage_kwargs))
        results.append(self.task_inbox_notifications())
        return results
