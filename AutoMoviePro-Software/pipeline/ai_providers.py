from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


def _client_for_keys(api_keys: List[str]):
    try:
        from google import genai
    except ImportError:
        return None, None
    for key in api_keys:
        key = (key or "").strip()
        if not key:
            continue
        try:
            client = genai.Client(api_key=key)
            return client, key
        except Exception as exc:
            logger.warning("Google AI key failed: %s", exc)
    return None, None


def generate_script_bundle(
    channel: Dict[str, Any],
    video_type: str,
    *,
    topic: str = "",
    research_notes: str = "",
) -> Dict[str, Any]:
    niche = channel.get("niche") or "general"
    max_sec = 120 if video_type == "short" else 300
    focus = topic or niche
    from pipeline.prompt_engineering import script_bundle_instruction

    prompt = script_bundle_instruction(
        channel_name=channel.get("youtube_name") or "Gadget Review",
        niche=niche,
        focus=focus,
        research_notes=research_notes or "",
        video_type=video_type,
        max_sec=max_sec,
        video_special=channel.get("video_special") or "",
        generation_special=channel.get("generation_special") or "",
        title_desc_special=channel.get("title_desc_special") or "",
        example_script=channel.get("example_script") or "",
    )
    # Burn-proof purpose chain: Groq → Cerebras → OR → HF → FreeTheAI → Google
    try:
        from pipeline.llm_router import chat_text, extract_json_object
        from pipeline.api_keys import load_api_bundle

        bundle = load_api_bundle(channel=channel)
        hit = chat_text(
            prompt,
            purpose="script",
            # Google keys intentionally omitted — script uses Groq/OR/HF only
            openrouter_api=(channel.get("openrouter_api") or ""),
            openrouter_keys=list(bundle.get("openrouter_keys") or []),
            groq_keys=list(bundle.get("groq_keys") or []),
            json_mode=True,
        )
        data = json.loads(extract_json_object(hit["text"]))
        data["video_type"] = video_type
        data["max_seconds"] = max_sec
        data["topic"] = focus
        data["provider"] = hit.get("provider")
        from pipeline.master_lang import lock_english_master_plan

        return lock_english_master_plan(data)
    except Exception as exc:
        logger.warning("script llm_router failed: %s", exc)

    from pipeline.master_lang import lock_english_master_plan

    return lock_english_master_plan(_fallback_bundle(focus, video_type, max_sec))


def _via_openrouter(api_key: str, prompt: str) -> Dict[str, Any]:
    """Routed through llm_router budget/circuit (do not raw-POST OpenRouter)."""
    from pipeline.llm_router import extract_json_object, openrouter_chat

    content = openrouter_chat(prompt, api_keys=[api_key], json_mode=True)
    return json.loads(extract_json_object(content))


def _fallback_bundle(niche: str, video_type: str, max_sec: int) -> Dict[str, Any]:
    is_short = video_type == "short"
    title = (
        f"{niche} Review 2026 — Should You Buy It?"
        if is_short
        else f"{niche} Full Review 2026 — Specs, Camera/Sound, Battery, Price"
    )
    if is_short:
        scenes = [
            {"narration": f"Today's trending gadget — {niche}.", "visual": f"{niche} product hero shot"},
            {"narration": "Design and build quality already feel premium in the hand.", "visual": "close-up design details"},
            {"narration": "Performance and battery are enough for everyday use.", "visual": "usage lifestyle b-roll"},
            {"narration": "Would you buy it? Tell us in the comments — and stay for the next review.", "visual": "call to action end screen"},
        ]
    else:
        scenes = [
            {"narration": f"Welcome back. Today we fully review {niche}.", "visual": f"{niche} unboxing cinematic"},
            {"narration": "First, design and build — weight, finish, and how it feels in hand.", "visual": "design close-ups"},
            {"narration": "Core features and specs, explained simply.", "visual": "specs infographic style footage"},
            {"narration": "Real-world performance — gaming, multitasking, or media.", "visual": "performance demo b-roll"},
            {"narration": "Battery and charging matter for daily use.", "visual": "battery charging scene"},
            {"narration": "Pros and cons in one look — who should buy, who should skip.", "visual": "pros cons checklist visual"},
            {"narration": "Value for the price and the final verdict. Thanks for watching.", "visual": "final verdict endcard"},
        ]
    tags = [
        niche,
        "gadget review",
        "tech review",
        "shorts" if is_short else "full review",
        "2026",
        "english master",
    ]
    description = (
        f"{title}\n\n"
        f"Trending gadget review — {niche}\n\n"
        f"00:00 Intro\n"
        f"Highlights, pros/cons, and a buyer's call.\n\n"
        f"#{''.join(ch for ch in niche if ch.isalnum())} #GadgetReview #TechReview #Review2026"
    )
    return {
        "title": title,
        "description": description,
        "tags": tags,
        "script": " ".join(s["narration"] for s in scenes),
        "scenes": scenes,
        "video_type": video_type,
        "max_seconds": max_sec,
        "provider": "fallback_rich",
        "master_lang": "en",
    }


def _extract_json(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("{"):
        return text
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else "{}"


def fetch_pexels_videos(
    api_key: str,
    query: str,
    per_page: int = 3,
    orientation: str = "",
) -> List[str]:
    if not api_key:
        return []
    q = (query or "").strip()
    if not q:
        logger.debug("pexels skipped: empty query")
        return []
    try:
        # Heuristic orientation from query/explicit
        orient = orientation
        if not orient:
            qlow = q.lower()
            orient = "portrait" if any(x in qlow for x in ("short", "portrait", "9:16", "vertical")) else "landscape"
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                "https://api.pexels.com/videos/search",
                params={"query": q, "per_page": per_page, "orientation": orient},
                headers={"Authorization": api_key},
            )
            r.raise_for_status()
            data = r.json()
            urls: List[str] = []
            for video in data.get("videos") or []:
                files = sorted(video.get("video_files") or [], key=lambda x: x.get("width") or 0, reverse=True)
                if files:
                    urls.append(files[0]["link"])
            return urls
    except Exception as exc:
        logger.warning("pexels failed: %s", exc)
        return []


def request_agnes_clip(api_key: str, prompt: str, out_path: str) -> Optional[str]:
    """Best-effort Agnes API call; returns path if downloaded, else None."""
    if not api_key:
        return None
    # Agnes endpoints vary by account; keep pluggable stub with HTTP attempt.
    endpoints = [
        "https://api.agn.ist/v1/video/generate",
        "https://api.agnes-ai.com/v1/videos",
    ]
    for url in endpoints:
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"prompt": prompt, "duration": 5},
                )
                if r.status_code >= 400:
                    continue
                data = r.json()
                video_url = data.get("url") or data.get("video_url") or (data.get("data") or {}).get("url")
                if not video_url:
                    continue
                media = client.get(video_url)
                media.raise_for_status()
                PathWrite = __import__("pathlib").Path
                PathWrite(out_path).write_bytes(media.content)
                return out_path
        except Exception as exc:
            logger.debug("agnes endpoint %s failed: %s", url, exc)
    return None
