"""Google Pro & Multi-Provider Pacing Guard and Intelligent Quota Manager.

Addresses the two core operational directives:
1. Pacing & Random Jitter Gap between consecutive API calls:
   - Enforces a defined, randomized time gap between consecutive Google Pro / Gemini API calls
     (video generation, image generation, audio/TTS synthesis, or general text/chat/critic).
   - Video, Audio, and Image generation have longer randomized gaps.
   - Enforces post-generation cooldown after each video clip, audio clip, and image.
2. Quota Error Analysis & Smart Wait vs. Complete-by-Any-Means Fallback:
   - When a 429 / RESOURCE_EXHAUSTED / quota message occurs, analyzes the exact error message
     and headers to determine the cooldown duration (e.g., 30s-60s burst RPM, 10m, 30m, 1h, 6h, or daily limit).
   - If the duration is short (<= max_auto_wait, default 30 mins): pauses pipeline cleanly and retries.
   - If the duration is long (6h / daily):
     - If today's video is already completed: pauses / enters rest mode safely.
     - If today's video is NOT yet completed: guarantees the video completes by any means
       (rotates keys or immediately falls over to alternative providers like Workers AI FLUX,
       Agnes, Kling, Edge-TTS, Pollinations, Ken Burns, etc.).
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Modality default random delay ranges in seconds: (min_sec, max_sec)
DEFAULT_PACING_RANGES: Dict[str, Tuple[float, float]] = {
    # Video generation: heaviest compute and strictest RPM
    "video": (45.0, 75.0),
    # Audio / TTS synthesis: Gemini TTS per-shot / continuous rate limits
    "audio": (35.0, 65.0),
    # Image generation: Google Imagen / Flash Image / Workers AI
    "image": (20.0, 40.0),
    # General / Text: Localization, script analysis, vision critique
    "general": (8.0, 16.0),
}

# Maximum duration (in seconds) the pipeline will automatically sleep to wait for quota refill.
# Anything <= this threshold will auto-pause and resume; anything > this threshold triggers fallback.
DEFAULT_MAX_AUTO_WAIT_SEC = 1800.0  # 30 minutes

_pacing_lock = threading.RLock()
_last_call_timestamps: Dict[str, float] = {}
_tls = threading.local()


@dataclass
class QuotaAnalysis:
    is_quota: bool
    cooldown_seconds: float
    window_type: str  # 'burst_rpm', 'short_window', 'hourly', 'six_hour', 'daily', 'unknown'
    human_duration: str
    can_auto_wait: bool
    raw_message: str
    action_recommendation: str  # 'WAIT_AND_RETRY', 'ROTATE_KEY', 'FALLBACK_IMMEDIATELY'


def get_pacing_range(modality: str) -> Tuple[float, float]:
    """Returns (min_sec, max_sec) for a given modality, allowing env overrides."""
    mod = (modality or "general").strip().lower()
    base_min, base_max = DEFAULT_PACING_RANGES.get(mod, DEFAULT_PACING_RANGES["general"])

    env_min_key = f"AMP_GAP_{mod.upper()}_MIN"
    env_max_key = f"AMP_GAP_{mod.upper()}_MAX"

    min_val = base_min
    max_val = base_max

    raw_min = (os.environ.get(env_min_key) or "").strip()
    if raw_min:
        try:
            min_val = max(0.0, float(raw_min))
        except ValueError:
            pass

    raw_max = (os.environ.get(env_max_key) or "").strip()
    if raw_max:
        try:
            max_val = max(min_val, float(raw_max))
        except ValueError:
            pass

    multiplier_raw = (os.environ.get("AMP_GAP_MULTIPLIER") or "1.0").strip()
    try:
        mult = max(0.1, float(multiplier_raw))
        min_val *= mult
        max_val *= mult
    except ValueError:
        pass

    if max_val < min_val:
        max_val = min_val

    return min_val, max_val


def compute_random_gap(modality: str) -> float:
    """Generates a randomized jittered duration for the given modality."""
    min_sec, max_sec = get_pacing_range(modality)
    if min_sec >= max_sec:
        return min_sec
    return round(random.uniform(min_sec, max_sec), 2)


def set_pacing_package_context(package_root: str = "", state: Any = None) -> None:
    """Stores thread-local context for cancel handling."""
    _tls.package_root = package_root or ""
    _tls.state = state


def wait_pacing_gap(
    *,
    modality: str = "general",
    provider: str = "google",
    reason: str = "",
    package_root: str = "",
    state: Any = None,
) -> float:
    """Enforces a randomized time gap before making an API call.

    Guarantees:
      - Two calls of the same modality/provider won't fire in quick succession.
      - Delay duration is randomized to prevent server synchronization.
      - Cancellation immediately aborts the sleep without hanging.
    """
    from pipeline.custom_pipeline.pipeline_control import (
        PipelineCancelled,
        check_cancelled,
        interruptible_sleep,
    )

    pkg = package_root or getattr(_tls, "package_root", "") or ""
    st = state if state is not None else getattr(_tls, "state", None)

    target_gap = compute_random_gap(modality)
    if target_gap <= 0:
        return 0.0

    key = f"{provider.lower()}:{modality.lower()}"
    with _pacing_lock:
        now = time.monotonic()
        last_ts = _last_call_timestamps.get(key, 0.0)
        elapsed = now - last_ts if last_ts > 0 else 999999.0
        wait = target_gap - elapsed if elapsed < target_gap else 0.0
        if wait <= 0:
            _last_call_timestamps[key] = time.monotonic()
            return 0.0

    logger.info(
        "API Pacing: waiting %.1fs (randomized %.0f-%.0fs gap for %s/%s)%s",
        wait,
        *get_pacing_range(modality),
        provider,
        modality,
        f" [{reason}]" if reason else "",
    )

    try:
        interruptible_sleep(wait, package_root=pkg, state=st)
    except PipelineCancelled:
        raise
    except Exception as exc:
        logger.debug("interruptible_sleep soft-fail during pacing: %s", exc)
        check_cancelled(pkg, st)
        time.sleep(wait)

    with _pacing_lock:
        _last_call_timestamps[key] = time.monotonic()

    return wait


def record_api_call_start(modality: str = "general", provider: str = "google") -> None:
    """Updates the last call timestamp for a modality/provider."""
    key = f"{provider.lower()}:{modality.lower()}"
    with _pacing_lock:
        _last_call_timestamps[key] = time.monotonic()


def post_generation_cooldown(
    *,
    modality: str = "image",
    provider: str = "google",
    reason: str = "",
    package_root: str = "",
    state: Any = None,
) -> float:
    """Randomized cooldown explicitly executed after each video clip, audio clip, or image generation.

    Fulfills the user requirement:
      'প্রতিটি ভিডিও ক্লিপ, অডিও ক্লিপ এবং ইমেজ জেনারেশন হওয়ার পর একটা রেনডম সময়
       অপেক্ষা করে তারপরে পরবর্তী কল আসবে যেন সময় বেশি লাগলেও এ পি আই এর লিমিট রিচ করে না দেয়'
    """
    from pipeline.custom_pipeline.pipeline_control import (
        PipelineCancelled,
        check_cancelled,
        interruptible_sleep,
    )

    pkg = package_root or getattr(_tls, "package_root", "") or ""
    st = state if state is not None else getattr(_tls, "state", None)

    cooldown = compute_random_gap(modality)
    if cooldown <= 0:
        return 0.0

    logger.info(
        "Post-generation cooldown: waiting %.1fs after %s %s generation to prevent rate limits...",
        cooldown,
        provider,
        modality,
    )

    try:
        interruptible_sleep(cooldown, package_root=pkg, state=st)
    except PipelineCancelled:
        raise
    except Exception as exc:
        logger.debug("interruptible_sleep soft-fail in cooldown: %s", exc)
        check_cancelled(pkg, st)
        time.sleep(cooldown)

    key = f"{provider.lower()}:{modality.lower()}"
    with _pacing_lock:
        _last_call_timestamps[key] = time.monotonic()

    return cooldown


def analyze_quota_error(
    error_or_text: Any,
    response_headers: Optional[Dict[str, str]] = None,
    *,
    max_auto_wait_sec: Optional[float] = None,
) -> QuotaAnalysis:
    """Exhaustive inspection of quota / rate-limit errors from Google / Gemini / AI APIs.

    Discovers:
      - Explicit retry-after instructions (e.g. 'retry after 43s', 'retry after 10m')
      - Quota window limits:
        * 15 RPM / 60-second burst
        * 10-minute / 30-minute refill intervals
        * Hourly quotas
        * 6-hour or Daily (24h) free-tier reset
    """
    text = str(error_or_text or "")
    low = text.lower()
    headers = {str(k).lower(): str(v) for k, v in (response_headers or {}).items()}

    needles = (
        "429",
        "402",
        "resource_exhausted",
        "quota",
        "rate limit",
        "rate_limit",
        "too many requests",
        "usage limit",
        "exhausted",
        "free_tier",
        "free-tier",
        "high demand",
        "retry after",
        "retry-after",
        "please retry",
    )

    is_quota = any(n in low for n in needles)
    if not is_quota:
        return QuotaAnalysis(
            is_quota=False,
            cooldown_seconds=0.0,
            window_type="none",
            human_duration="0s",
            can_auto_wait=True,
            raw_message=text[:200],
            action_recommendation="NONE",
        )

    max_wait = max_auto_wait_sec if max_auto_wait_sec is not None else DEFAULT_MAX_AUTO_WAIT_SEC

    # 1. Check response headers for explicit Retry-After
    retry_header = headers.get("retry-after", "")
    if retry_header.strip():
        try:
            sec = float(retry_header.strip())
            return _build_analysis(
                sec + random.uniform(2.0, 8.0),
                "explicit_retry_after",
                text,
                max_wait,
            )
        except ValueError:
            pass

    # 2. Regex for textual retry-after / please retry
    m = re.search(r"retry[- ]after[:= ]*(\d+)\s*(s|sec|seconds|m|min|minutes|h|hr|hours)?", low)
    if m:
        val = float(m.group(1))
        unit = (m.group(2) or "s").lower()
        multiplier = 60.0 if "m" in unit else (3600.0 if "h" in unit else 1.0)
        cooldown = (val * multiplier) + random.uniform(3.0, 10.0)
        return _build_analysis(cooldown, "text_retry_after", text, max_wait)

    m = re.search(r"please retry after (\d+)\s*(s|sec|seconds|m|min|minutes|h|hr|hours)?", low)
    if m:
        val = float(m.group(1))
        unit = (m.group(2) or "s").lower()
        multiplier = 60.0 if "m" in unit else (3600.0 if "h" in unit else 1.0)
        cooldown = (val * multiplier) + random.uniform(3.0, 10.0)
        return _build_analysis(cooldown, "text_retry_after", text, max_wait)

    # 3. Detect Daily / 6-hour exhaustion phrases (limit: 0, per day, free tier exhausted)
    if any(
        x in low
        for x in (
            "limit: 0",
            "limit:0",
            "generate_content_free_tier",
            "perday",
            "per day",
            "daily limit",
            "day quota",
            "exceeded your daily",
        )
    ):
        # Daily limit reached: standard 6 hours to 24 hours cooldown
        cooldown = 6.0 * 3600.0
        return _build_analysis(cooldown, "daily", text, max_wait)

    # 4. Check for metric quota phrases: 'per 60 seconds', 'per 10 minutes', 'per hour'
    if "per 60 second" in low or "per minute" in low or "15 rpm" in low:
        cooldown = 60.0 + random.uniform(5.0, 15.0)
        return _build_analysis(cooldown, "burst_rpm", text, max_wait)

    if "per 10 minute" in low or "10 minute" in low:
        cooldown = 600.0 + random.uniform(10.0, 30.0)
        return _build_analysis(cooldown, "short_window", text, max_wait)

    if "per 30 minute" in low or "30 minute" in low:
        cooldown = 1800.0 + random.uniform(15.0, 45.0)
        return _build_analysis(cooldown, "short_window", text, max_wait)

    if "per hour" in low or "hourly" in low:
        cooldown = 3600.0 + random.uniform(20.0, 60.0)
        return _build_analysis(cooldown, "hourly", text, max_wait)

    # 5. Default 429 without explicit duration: usually 60-120 seconds burst RPM
    cooldown = 75.0 + random.uniform(5.0, 25.0)
    return _build_analysis(cooldown, "burst_rpm", text, max_wait)


def _build_analysis(cooldown_sec: float, window_type: str, raw_text: str, max_auto_wait: float) -> QuotaAnalysis:
    can_wait = cooldown_sec <= max_auto_wait
    if cooldown_sec < 60:
        human = f"{int(cooldown_sec)}s"
    elif cooldown_sec < 3600:
        human = f"{cooldown_sec / 60.0:.1f}m"
    else:
        human = f"{cooldown_sec / 3600.0:.1f}h"

    if can_wait:
        action = "WAIT_AND_RETRY"
    elif window_type in ("daily", "six_hour"):
        action = "FALLBACK_IMMEDIATELY"
    else:
        action = "ROTATE_KEY"

    return QuotaAnalysis(
        is_quota=True,
        cooldown_seconds=round(cooldown_sec, 1),
        window_type=window_type,
        human_duration=human,
        can_auto_wait=can_wait,
        raw_message=raw_text[:250],
        action_recommendation=action,
    )


def is_package_video_completed(package_root: Path | str) -> bool:
    """Verifies whether the package has already generated its final completed video(s)."""
    if not package_root:
        return False
    pkg = Path(package_root)
    # Check for final videos in Video/ or Video/{LANG}/
    video_dir = pkg / "Video"
    if not video_dir.is_dir():
        return False

    final_candidates = list(video_dir.glob("Final_*.mp4")) + list(video_dir.glob("final_*.mp4"))
    for sub in video_dir.iterdir():
        if sub.is_dir():
            final_candidates.extend(sub.glob("final_*.mp4"))
            final_candidates.extend(sub.glob("Final_*.mp4"))

    for v in final_candidates:
        if v.is_file() and v.stat().st_size > 50000:
            return True

    # Also check media_stage_manifest.json
    manifest = pkg / "File" / "media_stage_manifest.json"
    if manifest.is_file():
        try:
            import json
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("shippable") or data.get("ok"):
                return True
        except Exception:
            pass

    return False


def handle_quota_exhaustion(
    *,
    error_or_text: Any,
    modality: str = "general",
    provider: str = "google",
    package_root: Path | str = "",
    response_headers: Optional[Dict[str, str]] = None,
    state: Any = None,
    max_auto_wait_sec: Optional[float] = None,
) -> Tuple[str, QuotaAnalysis]:
    """Central decision engine for quota handling.

    Implements the user's exact specification:
      1. Analyze how long the quota limit is for (10m, 30m, 1h, 6h, etc.).
      2. If short: pauses the entire pipeline cleanly for that duration and resumes.
      3. If daily / 6-hour limit:
         - If today's video is already completed -> safe to pause / rest.
         - If today's video is NOT yet completed -> NEVER abort; complete the video by ANY means
           (signals caller to switch to alternative fallback providers immediately).

    Returns:
      (action_code, QuotaAnalysis)
      action_code in ('RETRY', 'PAUSE_UNTIL_RESET', 'FALLBACK_BY_ANY_MEANS')
    """
    from pipeline.custom_pipeline.pipeline_control import (
        PipelineCancelled,
        check_cancelled,
        interruptible_sleep,
    )

    analysis = analyze_quota_error(error_or_text, response_headers, max_auto_wait_sec=max_auto_wait_sec)
    if not analysis.is_quota:
        return "NONE", analysis

    pkg_str = str(package_root or getattr(_tls, "package_root", "") or "")
    st = state if state is not None else getattr(_tls, "state", None)

    # Case A: Short duration -> Pause and auto-resume
    if analysis.can_auto_wait:
        logger.warning(
            "⏳ Google API quota touched (window=%s, cooldown=%s). "
            "Pipeline pausing cleanly for %s to let quota refill, then will auto-resume...",
            analysis.window_type,
            analysis.human_duration,
            analysis.human_duration,
        )
        try:
            interruptible_sleep(analysis.cooldown_seconds, package_root=pkg_str, state=st)
            logger.info("⏳ Quota refill window elapsed (%s). Resuming operation...", analysis.human_duration)
            return "RETRY", analysis
        except PipelineCancelled:
            raise

    # Case B: Long duration (6-hour or daily limit)
    video_completed = is_package_video_completed(pkg_str)
    if video_completed:
        logger.info(
            "✅ Today's video package (%s) is already completed! "
            "Safe to rest until quota resets (%s).",
            pkg_str,
            analysis.human_duration,
        )
        return "PAUSE_UNTIL_RESET", analysis

    # Video is NOT completed yet! User mandate: "যেকোনো উপায়ে ভিডিও কমপ্লিট করবে"
    logger.warning(
        "⚠️ Google Pro API %s quota reached (%s), but today's video is NOT completed yet! "
        "Engaging alternative providers (Fallback Chains) to complete the video by any means...",
        analysis.window_type,
        analysis.human_duration,
    )
    return "FALLBACK_BY_ANY_MEANS", analysis
