"""Browser Core & State Persistence — Camoufox-first with Playwright fallback."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)


def _default_profile_dir(platform: str = "e2e") -> Path:
    try:
        from app.config import DATA_DIR

        base = Path(DATA_DIR) / "e2e_ui_profiles" / platform
    except Exception:
        base = Path(__file__).resolve().parents[2] / "data" / "e2e_ui_profiles" / platform
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class BrowserSession:
    """Live browser handles for a single automation run."""

    page: Any
    context: Any
    browser: Any = None
    playwright: Any = None
    engine: str = "unknown"
    user_data_dir: str = ""
    storage_state_path: str = ""
    extras: dict = field(default_factory=dict)

    def save_storage_state(self, path: Optional[str] = None) -> str:
        out = path or self.storage_state_path
        if not out:
            out = str(Path(self.user_data_dir or ".") / "storage_state.json")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        try:
            self.context.storage_state(path=out)
            self.storage_state_path = out
            logger.info("E2E storage_state saved → %s", out)
        except Exception as exc:
            logger.warning("storage_state save failed: %s", exc)
        return out


class BrowserEngine:
    """
    Launch Camoufox (preferred) or Playwright persistent context.

    Env:
      AMP_E2E_HEADLESS=1          force headless
      AMP_E2E_FORCE_PLAYWRIGHT=1  skip Camoufox
      AMP_E2E_PROFILE_DIR=...     override user_data_dir root
    """

    def __init__(
        self,
        *,
        platform: str = "generic",
        user_data_dir: str = "",
        storage_state: str = "",
        headless: Optional[bool] = None,
        humanize: bool = True,
    ) -> None:
        self.platform = (platform or "generic").strip().lower()
        env_root = (os.environ.get("AMP_E2E_PROFILE_DIR") or "").strip()
        if user_data_dir:
            self.user_data_dir = str(Path(user_data_dir))
        elif env_root:
            self.user_data_dir = str(Path(env_root) / self.platform)
        else:
            self.user_data_dir = str(_default_profile_dir(self.platform))
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

        st = storage_state or str(Path(self.user_data_dir) / "storage_state.json")
        self.storage_state = st if Path(st).exists() else ""
        self.storage_state_path = st
        self.humanize = bool(humanize)

        if headless is None:
            headless = (os.environ.get("AMP_E2E_HEADLESS") or "").strip() in ("1", "true", "yes")
        self.headless = bool(headless)

    @contextmanager
    def session(self) -> Iterator[BrowserSession]:
        force_pw = (os.environ.get("AMP_E2E_FORCE_PLAYWRIGHT") or "").strip() in (
            "1",
            "true",
            "yes",
        )
        if not force_pw:
            try:
                with self._camoufox_session() as sess:
                    yield sess
                    return
            except Exception as exc:
                logger.warning("Camoufox launch failed (%s) — Playwright fallback", exc)

        with self._playwright_session() as sess:
            yield sess

    @contextmanager
    def _camoufox_session(self) -> Iterator[BrowserSession]:
        from camoufox.sync_api import Camoufox

        # Camoufox supports humanize + persistent profile via Firefox user path.
        # API varies slightly by version — try rich kwargs then degrade.
        kwargs: dict = {
            "headless": self.headless,
            "humanize": self.humanize,
        }
        # Persistent profile (cookies / localStorage / IndexedDB)
        try:
            kwargs["user_data_dir"] = self.user_data_dir
        except Exception:
            pass

        logger.info(
            "E2E BrowserEngine: Camoufox humanize=%s headless=%s profile=%s",
            self.humanize,
            self.headless,
            self.user_data_dir,
        )
        try:
            cm = Camoufox(**kwargs)
        except TypeError:
            # Older camoufox without user_data_dir / humanize
            cm = Camoufox(headless=self.headless)

        with cm as browser:
            ctx_kwargs: dict = {
                "viewport": None,  # window-sized
                "locale": "en-US",
                "timezone_id": "Asia/Dhaka",
            }
            if self.storage_state:
                ctx_kwargs["storage_state"] = self.storage_state
            try:
                context = browser.new_context(**ctx_kwargs)
            except TypeError:
                context = browser.new_context(
                    storage_state=self.storage_state or None,
                )
            page = context.new_page()
            self._harden_navigator(page)
            sess = BrowserSession(
                page=page,
                context=context,
                browser=browser,
                engine="camoufox",
                user_data_dir=self.user_data_dir,
                storage_state_path=self.storage_state_path,
            )
            try:
                yield sess
            finally:
                try:
                    sess.save_storage_state()
                except Exception:
                    pass

    @contextmanager
    def _playwright_session(self) -> Iterator[BrowserSession]:
        from playwright.sync_api import sync_playwright

        logger.info(
            "E2E BrowserEngine: Playwright persistent context profile=%s",
            self.user_data_dir,
        )
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=self.headless,
                channel="chrome",
                no_viewport=True,
                locale="en-US",
                timezone_id="Asia/Dhaka",
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            if self.storage_state and Path(self.storage_state).exists():
                try:
                    # Already in persistent profile; storage_state optional hydrate
                    pass
                except Exception:
                    pass
            page = context.pages[0] if context.pages else context.new_page()
            try:
                from playwright_stealth import stealth_sync

                stealth_sync(page)
            except Exception:
                pass
            self._harden_navigator(page)
            sess = BrowserSession(
                page=page,
                context=context,
                playwright=p,
                engine="playwright",
                user_data_dir=self.user_data_dir,
                storage_state_path=self.storage_state_path,
            )
            try:
                yield sess
            finally:
                try:
                    sess.save_storage_state()
                except Exception:
                    pass
                try:
                    context.close()
                except Exception:
                    pass

    @staticmethod
    def _harden_navigator(page: Any) -> None:
        """Natural navigator / canvas hints (best-effort; Camoufox already hardens heavily)."""
        script = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        if (!window.chrome) { window.chrome = { runtime: {} }; }
        """
        try:
            page.add_init_script(script)
        except Exception as exc:
            logger.debug("navigator harden skip: %s", exc)
