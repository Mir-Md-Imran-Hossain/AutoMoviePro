"""
Universal Master Browser Video Dispatcher
=========================================
Coordinates generation across the 5 human-like stealth browser engines:
1. Dreamina (ByteDance / CapCut)
2. Kling AI
3. PixVerse
4. Leonardo AI
5. Muse AI
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.multi_video_pool import (
    get_active_account,
    record_successful_generation,
    SUPPORTED_PLATFORMS,
)
from pipeline.stealth_browser import (
    create_stealth_context,
    human_click,
    human_move_mouse,
    human_scroll,
    human_type,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 1. Dreamina (Seedance 2.0 / 1.0) Automation Adapter
# ----------------------------------------------------------------------
async def generate_dreamina_video(
    prompt: str,
    out_path: Path,
    account: Dict[str, Any],
    *,
    aspect_ratio: str = "9:16",
    duration_sec: float = 5.0,
    max_wait_sec: int = 150,
) -> Optional[Path]:
    """Generates video on Dreamina using human-like stealth browsing."""
    from playwright.async_api import async_playwright

    session_path = Path(account["session_file"])
    async with async_playwright() as p:
        browser, context = await create_stealth_context(p, storage_state_path=session_path, headless=True)
        page = await context.new_page()
        try:
            logger.info("[Dreamina] Navigating stealthily with account: %s", account["email"])
            await page.goto("https://dreamina.capcut.com/ai-tool/generate/video", wait_until="networkidle", timeout=45000)
            await asyncio.sleep(2.0)

            # Locate prompt textarea
            prompt_input = page.locator('textarea[placeholder*="describe" i], textarea[placeholder*="prompt" i], textarea').first
            if await prompt_input.count() == 0:
                logger.warning("[Dreamina] Prompt input not found or session expired")
                await browser.close()
                return None

            # Human-like click and typing
            await human_click(page, prompt_input)
            enhanced_prompt = f"{prompt}, cinematic lighting, photoreal 8k, stable motion"
            await human_type(prompt_input, enhanced_prompt)
            await asyncio.sleep(1.2)

            # Click Generate Button
            gen_btn = page.locator('button:has-text("Generate"), button[class*="generate" i]').first
            if await gen_btn.count() > 0:
                await human_click(page, gen_btn)
                logger.info("[Dreamina] Video generation submitted. Monitoring render...")

            # Wait for video output to render
            start_t = time.time()
            video_url = None
            while time.time() - start_t < max_wait_sec:
                vids = page.locator('video[src*="http"], video source[src*="http"]')
                if await vids.count() > 0:
                    src = await vids.first.get_attribute("src")
                    if src and ("blob:" not in src):
                        video_url = src
                        break
                # Download buttons
                dl_btn = page.locator('a[download], button:has-text("Download")')
                if await dl_btn.count() > 0:
                    href = await dl_btn.first.get_attribute("href")
                    if href and href.startswith("http"):
                        video_url = href
                        break
                await asyncio.sleep(4.0)

            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(video_url)
                    if resp.status_code == 200 and len(resp.content) > 15000:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(resp.content)
                        record_successful_generation("dreamina", account["email"], credit_cost=15)
                        logger.info("[Dreamina] Video downloaded successfully (%d bytes)", len(resp.content))
                        await browser.close()
                        return out_path

        except Exception as exc:
            logger.warning("[Dreamina] Generation exception: %s", exc)

        await browser.close()
    return None


# ----------------------------------------------------------------------
# 2. Kling AI Automation Adapter
# ----------------------------------------------------------------------
async def generate_kling_video(
    prompt: str,
    out_path: Path,
    account: Dict[str, Any],
    *,
    aspect_ratio: str = "9:16",
    duration_sec: float = 5.0,
    max_wait_sec: int = 160,
) -> Optional[Path]:
    """Generates video on Kling AI using human-like stealth browsing."""
    from playwright.async_api import async_playwright

    session_path = Path(account["session_file"])
    async with async_playwright() as p:
        browser, context = await create_stealth_context(p, storage_state_path=session_path, headless=True)
        page = await context.new_page()
        try:
            logger.info("[Kling AI] Navigating stealthily with account: %s", account["email"])
            await page.goto("https://klingai.com/text-to-video", wait_until="networkidle", timeout=45000)
            await asyncio.sleep(2.5)

            prompt_input = page.locator('textarea, input[placeholder*="Prompt" i]').first
            if await prompt_input.count() == 0:
                await browser.close()
                return None

            await human_click(page, prompt_input)
            await human_type(prompt_input, f"{prompt}, high aesthetic, 8k resolution")
            await asyncio.sleep(1.0)

            # Generate
            gen_btn = page.locator('button:has-text("Generate"), button[class*="submit" i]').first
            if await gen_btn.count() > 0:
                await human_click(page, gen_btn)
                logger.info("[Kling AI] Prompt submitted successfully.")

            # Monitor creation
            start_t = time.time()
            video_url = None
            while time.time() - start_t < max_wait_sec:
                vids = page.locator("video")
                if await vids.count() > 0:
                    src = await vids.first.get_attribute("src")
                    if src and src.startswith("http"):
                        video_url = src
                        break
                await asyncio.sleep(5.0)

            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(video_url)
                    if resp.status_code == 200 and len(resp.content) > 15000:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(resp.content)
                        record_successful_generation("kling", account["email"], credit_cost=10)
                        logger.info("[Kling AI] Video downloaded successfully (%d bytes)", len(resp.content))
                        await browser.close()
                        return out_path

        except Exception as exc:
            logger.warning("[Kling AI] Generation exception: %s", exc)

        await browser.close()
    return None


# ----------------------------------------------------------------------
# 3. PixVerse Automation Adapter
# ----------------------------------------------------------------------
async def generate_pixverse_video(
    prompt: str,
    out_path: Path,
    account: Dict[str, Any],
    *,
    aspect_ratio: str = "9:16",
    duration_sec: float = 5.0,
    max_wait_sec: int = 140,
) -> Optional[Path]:
    """Generates video on PixVerse using human-like stealth browsing."""
    from playwright.async_api import async_playwright

    session_path = Path(account["session_file"])
    async with async_playwright() as p:
        browser, context = await create_stealth_context(p, storage_state_path=session_path, headless=True)
        page = await context.new_page()
        try:
            logger.info("[PixVerse] Navigating stealthily with account: %s", account["email"])
            await page.goto("https://pixverse.ai/create", wait_until="networkidle", timeout=40000)
            await asyncio.sleep(2.0)

            prompt_input = page.locator('textarea[placeholder*="prompt" i], textarea').first
            if await prompt_input.count() == 0:
                await browser.close()
                return None

            await human_click(page, prompt_input)
            await human_type(prompt_input, prompt)
            await asyncio.sleep(1.0)

            # Generate Button
            gen_btn = page.locator('button:has-text("Create"), button:has-text("Generate")').first
            if await gen_btn.count() > 0:
                await human_click(page, gen_btn)
                logger.info("[PixVerse] Prompt submitted. Waiting for generation...")

            start_t = time.time()
            video_url = None
            while time.time() - start_t < max_wait_sec:
                vids = page.locator('video[src*="http"]')
                if await vids.count() > 0:
                    src = await vids.first.get_attribute("src")
                    if src:
                        video_url = src
                        break
                await asyncio.sleep(4.0)

            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(video_url)
                    if resp.status_code == 200 and len(resp.content) > 15000:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(resp.content)
                        record_successful_generation("pixverse", account["email"], credit_cost=10)
                        logger.info("[PixVerse] Video downloaded successfully (%d bytes)", len(resp.content))
                        await browser.close()
                        return out_path

        except Exception as exc:
            logger.warning("[PixVerse] Generation exception: %s", exc)

        await browser.close()
    return None


# ----------------------------------------------------------------------
# 4. Leonardo AI Automation Adapter
# ----------------------------------------------------------------------
async def generate_leonardo_video(
    prompt: str,
    out_path: Path,
    account: Dict[str, Any],
    *,
    aspect_ratio: str = "9:16",
    duration_sec: float = 5.0,
    max_wait_sec: int = 140,
) -> Optional[Path]:
    """Generates motion clip on Leonardo AI using human-like stealth browsing."""
    from playwright.async_api import async_playwright

    session_path = Path(account["session_file"])
    async with async_playwright() as p:
        browser, context = await create_stealth_context(p, storage_state_path=session_path, headless=True)
        page = await context.new_page()
        try:
            logger.info("[Leonardo AI] Navigating stealthily with account: %s", account["email"])
            await page.goto("https://app.leonardo.ai/motion", wait_until="networkidle", timeout=45000)
            await asyncio.sleep(2.0)

            prompt_input = page.locator('textarea, input[placeholder*="Type a prompt" i]').first
            if await prompt_input.count() > 0:
                await human_click(page, prompt_input)
                await human_type(prompt_input, prompt)
                await asyncio.sleep(1.0)
                gen_btn = page.locator('button:has-text("Generate"), button:has-text("Motion")').first
                if await gen_btn.count() > 0:
                    await human_click(page, gen_btn)

            # Wait for generation output
            start_t = time.time()
            video_url = None
            while time.time() - start_t < max_wait_sec:
                vids = page.locator("video")
                if await vids.count() > 0:
                    src = await vids.first.get_attribute("src")
                    if src and src.startswith("http"):
                        video_url = src
                        break
                await asyncio.sleep(4.0)

            if video_url:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.get(video_url)
                    if resp.status_code == 200 and len(resp.content) > 15000:
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(resp.content)
                        record_successful_generation("leonardo", account["email"], credit_cost=25)
                        logger.info("[Leonardo AI] Video downloaded successfully (%d bytes)", len(resp.content))
                        await browser.close()
                        return out_path

        except Exception as exc:
            logger.warning("[Leonardo AI] Generation exception: %s", exc)

        await browser.close()
    return None


# ----------------------------------------------------------------------
# Master Multi-Platform Synchronous Dispatcher
# ----------------------------------------------------------------------
def dispatch_browser_video_generation(
    prompt: str,
    out_path: Path,
    *,
    aspect_ratio: str = "9:16",
    duration_sec: float = 5.0,
) -> Optional[Path]:
    """
    Intelligently checks and routes to the best available platform:
    Dreamina -> Kling AI -> PixVerse -> Leonardo AI -> Muse AI.
    Returns generated Path on success or None if all browser accounts are exhausted/unconfigured.
    """
    priority_order = ("dreamina", "kling", "pixverse", "leonardo", "muse")

    for plat in priority_order:
        acc = get_active_account(plat)
        if not acc:
            continue

        logger.info("Attempting browser video via %s (account: %s, credits: %s)", plat, acc["email"], acc.get("credits_remaining"))
        res = None
        try:
            if plat == "dreamina":
                res = asyncio.run(generate_dreamina_video(prompt, out_path, acc, aspect_ratio=aspect_ratio, duration_sec=duration_sec))
            elif plat == "kling":
                res = asyncio.run(generate_kling_video(prompt, out_path, acc, aspect_ratio=aspect_ratio, duration_sec=duration_sec))
            elif plat == "pixverse":
                res = asyncio.run(generate_pixverse_video(prompt, out_path, acc, aspect_ratio=aspect_ratio, duration_sec=duration_sec))
            elif plat == "leonardo":
                res = asyncio.run(generate_leonardo_video(prompt, out_path, acc, aspect_ratio=aspect_ratio, duration_sec=duration_sec))
            elif plat == "muse":
                from pipeline.muse_engine import generate_muse_video_clip
                res = asyncio.run(generate_muse_video_clip(prompt, out_path, duration_sec=duration_sec, aspect_ratio=aspect_ratio))

            if res and res.is_file() and res.stat().st_size > 15000:
                logger.info("Successfully produced native video from platform: %s", plat)
                return res

        except Exception as exc:
            logger.warning("Platform %s run failed: %s — trying next platform in pool", plat, exc)

    return None
