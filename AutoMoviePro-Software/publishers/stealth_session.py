"""
Stealth browser launcher — best-effort anti-detection stack.

Priority:
  1) Patchright (free Playwright fork with CDP/fingerprint patches) + real Chrome
  2) Playwright + playwright-stealth
  3) Camoufox (Firefox fingerprint hardening) if AMP_USE_CAMOUFOX=1
  4) Plain Playwright Chromium

No stack is permanently "undetectable" — platforms update detectors.
We combine fingerprint patches + headed Chrome + human behavior layers.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

logger = logging.getLogger(__name__)


def _try_patchright():
    try:
        from patchright.sync_api import sync_playwright

        return sync_playwright
    except Exception as exc:
        logger.info("patchright unavailable: %s", exc)
        return None


def _try_playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright


def _apply_stealth(page) -> None:
    try:
        from playwright_stealth import stealth_sync

        stealth_sync(page)
    except Exception:
        try:
            from playwright_stealth import Stealth

            Stealth().apply_stealth_sync(page)
        except Exception as exc:
            logger.debug("playwright-stealth skip: %s", exc)


@contextmanager
def stealth_browser(
    *,
    storage_state: str = "",
    headless: bool = False,
    user_data_dir: str = "",
) -> Iterator[Tuple[Any, Any, Any, str]]:
    """
    Yields (playwright, browser_or_context, page, engine_name).
    Caller must not close playwright manually — context manager handles it.
    """
    prefer_headless = headless and os.environ.get("AMP_FORCE_HEADED", "").strip() != "1"
    # Engagement should prefer headed for realism unless AMP_HEADLESS=1
    if os.environ.get("AMP_HEADLESS", "").strip() == "1":
        prefer_headless = True
    else:
        prefer_headless = False if not headless else prefer_headless

    engine = "playwright"
    sync_pw = _try_patchright()
    if sync_pw:
        engine = "patchright"
    else:
        sync_pw = _try_playwright()

    if os.environ.get("AMP_USE_CAMOUFOX", "").strip() == "1":
        try:
            from camoufox.sync_api import Camoufox

            with Camoufox(headless=prefer_headless) as browser:
                context = browser.new_context(
                    storage_state=storage_state if storage_state and Path(storage_state).exists() else None
                )
                page = context.new_page()
                yield None, browser, page, "camoufox"
                return
        except Exception as exc:
            logger.warning("camoufox failed, falling back: %s", exc)

    with sync_pw() as p:
        browser = None
        context = None
        launch_err = None
        for attempt in (
            {"channel": "chrome", "headless": prefer_headless},
            {"channel": "msedge", "headless": prefer_headless},
            {"headless": prefer_headless},
        ):
            try:
                if user_data_dir:
                    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
                    context = p.chromium.launch_persistent_context(
                        user_data_dir,
                        channel=attempt.get("channel"),
                        headless=attempt.get("headless", False),
                        no_viewport=True,
                        args=["--disable-blink-features=AutomationControlled"],
                        ignore_default_args=["--enable-automation"] if engine == "patchright" else None,
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    if storage_state and Path(storage_state).exists() and not user_data_dir:
                        pass
                    if engine != "patchright":
                        _apply_stealth(page)
                    yield p, context, page, engine
                    try:
                        context.close()
                    except Exception:
                        pass
                    return
                browser = p.chromium.launch(**{k: v for k, v in attempt.items() if v is not None})
                ctx_kwargs: Dict[str, Any] = {
                    "viewport": {"width": 1366, "height": 768},
                    "locale": "en-US",
                    "timezone_id": "Asia/Dhaka",
                }
                if storage_state and Path(storage_state).exists():
                    ctx_kwargs["storage_state"] = storage_state
                context = browser.new_context(**ctx_kwargs)
                page = context.new_page()
                if engine != "patchright":
                    _apply_stealth(page)
                yield p, browser, page, engine
                try:
                    context.close()
                    browser.close()
                except Exception:
                    pass
                return
            except Exception as exc:
                launch_err = exc
                logger.info("stealth launch try %s failed: %s", attempt, exc)
                continue
        raise RuntimeError(f"stealth browser launch failed: {launch_err}")


def engine_status() -> Dict[str, Any]:
    return {
        "patchright": _try_patchright() is not None,
        "playwright_stealth": True,
        "camoufox_env": os.environ.get("AMP_USE_CAMOUFOX", ""),
        "note": "Best-effort stealth — not permanently undetectable.",
    }
