"""
Stealth Browser Engine with Ultra-Realistic Human Behavior Simulation
=====================================================================
Designed for undetected automated interactions with AI Video platforms:
- Dreamina (CapCut/ByteDance)
- Kling AI
- PixVerse
- Leonardo AI
- Muse AI

Features:
- Complete anti-bot evasion (Cloudflare, Akamai, PerimeterX, Datadome bypass)
- Cubic Bezier human-curved mouse trajectories with micro-jitters
- Realistic human typing with Gaussian keystroke latency & hesitation
- Smooth human scrolling
- Multi-session isolation with persistent cookies & storage states
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Real Windows 11 Chrome User-Agents
REAL_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

# Advanced anti-fingerprinting JS payload
EVASION_JS = """
(() => {
    // Overwrite webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });

    // Mock chrome runtime
    window.chrome = {
        app: { isInstalled: false },
        runtime: {
            OnInstalledReason: { INSTALL: "install" },
            PlatformArch: { X86_64: "x86-64" },
            PlatformNaclArch: { X86_64: "x86-64" },
            PlatformOs: { WIN: "win" },
            RequestUpdateCheckStatus: { NO_UPDATE: "no_update" }
        },
        loadTimes: () => ({}),
        csi: () => ({})
    };

    // Plugins mock
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: "Chrome PDF Plugin", filename: "internal-pdf-viewer", description: "Portable Document Format" },
            { name: "Chrome PDF Viewer", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai", description: "" },
            { name: "Native Client", filename: "internal-nacl-plugin", description: "" }
        ]
    });

    // Languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'bn']
    });

    // Hardware Concurrency
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8
    });

    // Device Memory
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8
    });

    // Permissions query mock
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
})();
"""


async def create_stealth_context(
    playwright_instance,
    storage_state_path: Optional[Path] = None,
    headless: bool = True,
):
    """Create an undetectable Chromium browser context with human fingerprints."""
    from playwright_stealth.stealth import Stealth

    ua = random.choice(REAL_USER_AGENTS)
    viewport = random.choice([
        {"width": 1920, "height": 1080},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
    ])

    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--ignore-certificate-errors",
        "--window-position=0,0",
    ]

    context_kwargs = {
        "user_agent": ua,
        "viewport": viewport,
        "locale": "en-US",
        "timezone_id": "Asia/Dhaka",
        "color_scheme": "dark",
        "device_scale_factor": 1,
        "has_touch": False,
        "is_mobile": False,
    }

    if storage_state_path and Path(storage_state_path).exists():
        context_kwargs["storage_state"] = str(storage_state_path)

    browser = await playwright_instance.chromium.launch(
        headless=headless,
        args=args,
    )
    context = await browser.new_context(**context_kwargs)
    await context.add_init_script(EVASION_JS)

    # Apply playwright_stealth suite
    stealth = Stealth()
    await stealth.apply_stealth_async(context)

    return browser, context


# -------------------------------------------------------------
# Human Behavior Physics & Trajectory Math
# -------------------------------------------------------------

def _bezier_curve(p0: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float], t: float) -> Tuple[float, float]:
    """Calculate point along Cubic Bezier curve."""
    cx = 3 * (p1[0] - p0[0])
    bx = 3 * (p2[0] - p1[0]) - cx
    ax = p3[0] - p0[0] - cx - bx

    cy = 3 * (p1[1] - p0[1])
    by = 3 * (p2[1] - p1[1]) - cy
    ay = p3[1] - p0[1] - cy - by

    t2 = t * t
    t3 = t2 * t
    return (ax * t3) + (bx * t2) + (cx * t) + p0[0], (ay * t3) + (by * t2) + (cy * t) + p0[1]


async def human_move_mouse(page, target_x: float, target_y: float, start_x: Optional[float] = None, start_y: Optional[float] = None):
    """Move mouse along a natural curved trajectory with micro-jitters."""
    if start_x is None or start_y is None:
        start_x = random.randint(100, 400)
        start_y = random.randint(100, 300)

    # Control points for natural arc
    deviation = random.uniform(30, 120)
    p0 = (start_x, start_y)
    p3 = (target_x, target_y)
    
    mid_x = (start_x + target_x) / 2 + random.uniform(-deviation, deviation)
    mid_y = (start_y + target_y) / 2 + random.uniform(-deviation, deviation)
    p1 = (start_x + (mid_x - start_x) * 0.5, start_y + (mid_y - start_y) * 0.8)
    p2 = (mid_x + (target_x - mid_x) * 0.5, mid_y + (target_y - mid_y) * 0.2)

    steps = random.randint(18, 32)
    for i in range(steps + 1):
        t = i / steps
        eased_t = math.sin(t * math.pi / 2) if t < 0.5 else 1 - math.cos(t * math.pi / 2)
        cur_x, cur_y = _bezier_curve(p0, p1, p2, p3, eased_t)
        jitter_x = random.uniform(-1.2, 1.2)
        jitter_y = random.uniform(-1.2, 1.2)
        await page.mouse.move(cur_x + jitter_x, cur_y + jitter_y)
        await asyncio.sleep(random.uniform(0.008, 0.022))


async def human_click(page, locator):
    """Hover naturally over an element, pause slightly, then click with variable hold."""
    box = await locator.bounding_box()
    if not box:
        await locator.click()
        return

    padding_x = box["width"] * random.uniform(0.2, 0.8)
    padding_y = box["height"] * random.uniform(0.2, 0.8)
    target_x = box["x"] + padding_x
    target_y = box["y"] + padding_y

    await human_move_mouse(page, target_x, target_y)

    await asyncio.sleep(random.uniform(0.08, 0.22))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.05, 0.12))
    await page.mouse.up()
    await asyncio.sleep(random.uniform(0.05, 0.15))


async def human_type(locator, text: str, error_rate: float = 0.01):
    """
    Type text with realistic inter-keystroke pauses, word breaks,
    and occasional typing mistakes + backspaces.
    """
    await locator.focus()
    await asyncio.sleep(random.uniform(0.1, 0.25))

    for idx, ch in enumerate(text):
        if random.random() < error_rate and ch.isalpha():
            wrong_char = chr(ord(ch) + random.choice([-1, 1]))
            await locator.type(wrong_char, delay=random.randint(50, 120))
            await asyncio.sleep(random.uniform(0.12, 0.28))
            await locator.press("Backspace")
            await asyncio.sleep(random.uniform(0.08, 0.2))

        delay_ms = random.gauss(85, 25)
        delay_ms = max(35, min(240, delay_ms))
        await locator.type(ch, delay=int(delay_ms))

        if ch in (" ", ",", ".", "-", "\n"):
            await asyncio.sleep(random.uniform(0.08, 0.35))
        elif random.random() < 0.04:
            await asyncio.sleep(random.uniform(0.15, 0.45))


async def human_scroll(page, direction: str = "down", distance: int = 350):
    """Smooth human scroll with deceleration."""
    delta = distance if direction == "down" else -distance
    steps = random.randint(5, 10)
    for _ in range(steps):
        step_delta = delta / steps + random.uniform(-10, 10)
        await page.mouse.wheel(0, step_delta)
        await asyncio.sleep(random.uniform(0.03, 0.08))
    await asyncio.sleep(random.uniform(0.2, 0.5))
