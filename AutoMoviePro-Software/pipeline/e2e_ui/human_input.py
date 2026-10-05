"""Human-like input simulation — typing, scrolling, curved mouse clicks."""
from __future__ import annotations

import logging
import math
import random
import time
from typing import Any, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

Selector = Union[str, Any]


def _rand(a: float, b: float) -> float:
    return random.uniform(a, b)


class HumanInteractionManager:
    """Custom action helpers with naturalistic timing."""

    def __init__(self, page: Any, *, seed: Optional[int] = None) -> None:
        self.page = page
        if seed is not None:
            random.seed(seed)
        self._mouse_pos: Tuple[float, float] = (
            float(random.randint(120, 480)),
            float(random.randint(120, 360)),
        )

    # ------------------------------------------------------------------ timing
    def pause(self, a: float = 0.25, b: float = 1.1) -> None:
        time.sleep(_rand(a, b))

    def micro_pause(self) -> None:
        time.sleep(_rand(0.04, 0.22))

    # ------------------------------------------------------------------ mouse
    def _bezier(
        self,
        p0: Tuple[float, float],
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        p3: Tuple[float, float],
        t: float,
    ) -> Tuple[float, float]:
        u = 1 - t
        return (
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        )

    def move_to(self, x: float, y: float, *, steps: int = 0) -> None:
        cur = self._mouse_pos
        dist = math.hypot(x - cur[0], y - cur[1])
        n = steps or max(12, min(42, int(10 + dist / 20))) + random.randint(-2, 4)
        # control points with jitter
        cx1 = cur[0] + (x - cur[0]) * _rand(0.2, 0.45) + _rand(-50, 50)
        cy1 = cur[1] + (y - cur[1]) * _rand(0.05, 0.35) + _rand(-70, 70)
        cx2 = cur[0] + (x - cur[0]) * _rand(0.55, 0.85) + _rand(-40, 40)
        cy2 = cur[1] + (y - cur[1]) * _rand(0.55, 0.95) + _rand(-50, 50)
        for i in range(1, max(2, n) + 1):
            t = i / n
            # ease-in-out
            te = t * t * (3 - 2 * t)
            px, py = self._bezier(cur, (cx1, cy1), (cx2, cy2), (x, y), te)
            try:
                self.page.mouse.move(px, py)
            except Exception:
                break
            time.sleep(_rand(0.004, 0.018))
        self._mouse_pos = (x, y)

    def _box_center(self, locator: Any) -> Tuple[float, float]:
        box = locator.bounding_box()
        if not box:
            raise RuntimeError("element has no bounding box")
        # Slight random offset inside the box (not dead-center every time)
        x = box["x"] + box["width"] * _rand(0.35, 0.65)
        y = box["y"] + box["height"] * _rand(0.35, 0.65)
        return x, y

    def resolve(self, target: Selector, *, timeout_ms: int = 15000) -> Any:
        if not isinstance(target, str):
            return target
        loc = self.page.locator(target).first
        loc.wait_for(state="visible", timeout=timeout_ms)
        return loc

    def click(
        self,
        target: Selector,
        *,
        timeout_ms: int = 15000,
        button: str = "left",
        click_count: int = 1,
    ) -> None:
        loc = self.resolve(target, timeout_ms=timeout_ms)
        try:
            loc.scroll_into_view_if_needed(timeout=timeout_ms)
        except Exception:
            pass
        self.pause(0.15, 0.45)
        x, y = self._box_center(loc)
        self.move_to(x, y)
        self.micro_pause()
        self.page.mouse.click(x, y, button=button, click_count=click_count)
        self.micro_pause()
        logger.debug("human click @ (%.0f, %.0f) target=%s", x, y, target)

    # ------------------------------------------------------------------ typing
    def type_text(
        self,
        target: Selector,
        text: str,
        *,
        clear: bool = True,
        min_delay_ms: int = 50,
        max_delay_ms: int = 180,
        timeout_ms: int = 15000,
    ) -> None:
        loc = self.resolve(target, timeout_ms=timeout_ms)
        self.click(loc, timeout_ms=timeout_ms)
        if clear:
            try:
                import sys

                mod = "Meta" if sys.platform == "darwin" else "Control"
                self.page.keyboard.down(mod)
                self.page.keyboard.press("a")
                self.page.keyboard.up(mod)
                self.page.keyboard.press("Backspace")
            except Exception:
                try:
                    loc.fill("")
                except Exception:
                    pass
        for ch in text or "":
            self.page.keyboard.type(ch, delay=0)
            time.sleep(_rand(min_delay_ms, max_delay_ms) / 1000.0)
            # Occasional longer hesitation (thinking)
            if random.random() < 0.04:
                time.sleep(_rand(0.2, 0.55))
        logger.debug("human typed %s chars", len(text or ""))

    # ------------------------------------------------------------------ scroll
    def scroll(
        self,
        *,
        delta_y: Optional[float] = None,
        steps: int = 0,
        toward: Optional[Selector] = None,
    ) -> None:
        """Natural mouse-wheel scrolls with staggered delays."""
        if toward is not None:
            loc = self.resolve(toward)
            try:
                box = loc.bounding_box()
                if box:
                    # Scroll in chunks toward element rather than jump
                    for _ in range(random.randint(3, 7)):
                        self.page.mouse.wheel(0, _rand(180, 420))
                        time.sleep(_rand(0.12, 0.38))
                        try:
                            if loc.is_visible():
                                break
                        except Exception:
                            pass
                    return
            except Exception:
                pass

        total = delta_y if delta_y is not None else _rand(400, 1200)
        n = steps or random.randint(4, 9)
        chunk = total / n
        for i in range(n):
            jitter = chunk * _rand(0.7, 1.3)
            self.page.mouse.wheel(0, jitter)
            time.sleep(_rand(0.08, 0.32))
            if random.random() < 0.15:
                time.sleep(_rand(0.25, 0.7))  # reading pause
        logger.debug("human scroll total≈%.0f steps=%s", total, n)

    def wait_for(
        self,
        selector: str,
        *,
        state: str = "visible",
        timeout_ms: int = 20000,
    ) -> Any:
        loc = self.page.locator(selector).first
        loc.wait_for(state=state, timeout=timeout_ms)
        return loc

    def watch_dwell(self, seconds: float) -> None:
        """Simulate realistic watch/view time with tiny idle motions."""
        end = time.time() + max(0.5, seconds)
        while time.time() < end:
            if random.random() < 0.25:
                self.page.mouse.wheel(0, _rand(-40, 80))
            if random.random() < 0.15:
                nx = self._mouse_pos[0] + _rand(-30, 30)
                ny = self._mouse_pos[1] + _rand(-20, 20)
                self.move_to(nx, ny, steps=8)
            time.sleep(_rand(0.4, 1.2))
