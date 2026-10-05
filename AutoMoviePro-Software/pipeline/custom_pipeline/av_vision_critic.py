"""Thrifty AV vision critic — AI looks at the frame ONLY when heuristics fail.

Hard thrift rules (never burn quota casually):
  - Default mode: auto → call vision ONLY if local AV gate already failed
    OR brand_ui + stock/fallback provider.
  - Max 1 vision call per shot; max N per package (env).
  - Uses cheapest Gemini flash multimodal; reuses IMAGE_GOOGLE key pool only
    (never opens new provider circuits for critique alone).
  - Short YES/NO JSON answer — tiny tokens.
  - Off when AMP_AV_VISION_CRITIC=0|off|false.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_package_calls: Dict[str, int] = {}
_shot_done: set[str] = set()


def vision_critic_mode() -> str:
    raw = (os.environ.get("AMP_AV_VISION_CRITIC") or "auto").strip().lower()
    if raw in ("0", "off", "false", "no", "disabled"):
        return "off"
    if raw in ("1", "on", "true", "always", "force"):
        return "on"
    return "auto"


def _max_per_package() -> int:
    try:
        return max(0, int(os.environ.get("AMP_AV_VISION_MAX_PER_PKG") or "4"))
    except ValueError:
        return 4


def should_run_vision(
    *,
    heuristic_ok: bool,
    visual_subject: str = "",
    provider: str = "",
    fallback: bool = False,
    package_id: str = "",
    shot_key: str = "",
) -> bool:
    mode = vision_critic_mode()
    if mode == "off":
        return False
    with _lock:
        sk = f"{package_id}:{shot_key}"
        if sk in _shot_done:
            return False
        used = _package_calls.get(package_id or "_", 0)
        if used >= _max_per_package():
            logger.info("AV vision skip — package budget exhausted (%s)", used)
            return False

    if mode == "on":
        return True

    # auto: only when local gate failed OR suspicious stock on brand UI
    subj = (visual_subject or "").lower()
    prov = (provider or "").lower()
    is_stock = fallback or "stock" in prov or "pexels" in prov or "pixabay" in prov
    if not heuristic_ok:
        return True
    if is_stock and subj in ("product_ui", "hands_ui"):
        return True
    return False


def _mark_used(package_id: str, shot_key: str) -> None:
    with _lock:
        _shot_done.add(f"{package_id}:{shot_key}")
        pid = package_id or "_"
        _package_calls[pid] = int(_package_calls.get(pid) or 0) + 1


def critique_frame_vs_dialogue(
    image_path: Path,
    *,
    narration: str,
    must_show: List[str],
    visual_subject: str = "",
    package_id: str = "",
    shot_key: str = "",
) -> Dict[str, Any]:
    """One cheap multimodal call. Caller must already pass should_run_vision()."""
    skipped = {
        "ok": True,
        "skipped": True,
        "match_score": None,
        "missing": [],
        "reason": "skipped",
        "api_used": False,
    }
    mode = vision_critic_mode()
    if mode == "off":
        skipped["reason"] = "vision_critic_off"
        return skipped
    with _lock:
        sk = f"{package_id}:{shot_key}"
        if sk in _shot_done:
            skipped["reason"] = "already_critiqued_shot"
            return skipped
        if _package_calls.get(package_id or "_", 0) >= _max_per_package():
            skipped["reason"] = "package_budget"
            return skipped

    path = Path(image_path)
    if not path.is_file() or path.stat().st_size < 1500:
        return {
            "ok": False,
            "skipped": False,
            "match_score": 0.0,
            "missing": ["no_image"],
            "reason": "image_missing",
            "api_used": False,
        }

    try:
        from pipeline.custom_pipeline.session_keys import list_image_google_keys

        keys = list_image_google_keys()
    except Exception:
        keys = []
    if not keys:
        # Do NOT borrow for critique — never burn localize/TTS keys on vision
        skipped["reason"] = "no_image_google_key_for_critic"
        skipped["ok"] = True  # don't block pipeline on missing critic key
        return skipped

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        skipped["reason"] = "no_genai_sdk"
        return skipped

    raw = path.read_bytes()
    # Cap payload — shrink huge PNG via jpeg if needed is skipped; just truncate check
    if len(raw) > 4_000_000:
        skipped["reason"] = "image_too_large_skip_critic"
        return skipped

    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    must_blob = "; ".join((must_show or [])[:6]) or "match spoken meaning on screen"
    narr_short = " ".join((narration or "").split())[:220]
    user = (
        "You are a strict AV-sync QA. Look at the image. "
        "Does it visually depict the dialogue intent (UI/props), not a random face/stock? "
        "Reply JSON only: "
        '{"match":true|false,"score":0-100,"missing":["…"],"note":"…"} '
        f"Dialogue: {narr_short}. MUST SHOW: {must_blob}. "
        f"Subject hint: {visual_subject or 'auto'}."
    )

    last_err = ""
    vision_models = [
        m.strip()
        for m in (
            (os.environ.get("AMP_AV_VISION_MODEL") or "")
            + ",gemini-3-flash-preview,gemini-flash-latest,gemini-3.6-flash"
        ).split(",")
        if m.strip()
    ]
    # de-dupe preserve order
    seen_m: set[str] = set()
    vision_models = [m for m in vision_models if not (m in seen_m or seen_m.add(m))]  # type: ignore

    for key in keys[:2]:  # at most 2 key tries — thrift
        model_ok = False
        for model in vision_models[:4]:
            try:
                client = genai.Client(api_key=key)
                resp = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_bytes(data=raw, mime_type=mime),
                                types.Part.from_text(text=user),
                            ],
                        )
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=120,
                        response_mime_type="application/json",
                    ),
                )
                text = (getattr(resp, "text", None) or "").strip()
                if not text and getattr(resp, "candidates", None):
                    for cand in resp.candidates or []:
                        for part in getattr(getattr(cand, "content", None), "parts", None) or []:
                            t = getattr(part, "text", None)
                            if t:
                                text = str(t)
                                break
                data = _parse_json(text)
                _mark_used(package_id, shot_key)
                score = float(data.get("score") or (100 if data.get("match") else 35))
                match = bool(data.get("match")) if "match" in data else score >= 60
                return {
                    "ok": match and score >= 55,
                    "skipped": False,
                    "match_score": score,
                    "missing": list(data.get("missing") or []),
                    "reason": str(data.get("note") or ("match" if match else "mismatch")),
                    "api_used": True,
                    "model": model,
                    "raw": data,
                }
            except Exception as exc:
                last_err = str(exc)[:160]
                low = last_err.lower()
                if any(x in low for x in ("429", "quota", "resource_exhausted")):
                    logger.warning("AV vision critic quota …%s — stop (thrift)", key[-4:])
                    model_ok = True  # stop model loop; break outer too
                    break
                if "404" in low or "not found" in low or "no longer available" in low:
                    logger.warning("AV vision model dead %s — try next", model)
                    continue
                logger.warning("AV vision critic failed …%s %s: %s", key[-4:], model, last_err)
                continue
        if model_ok:
            break

    skipped["reason"] = f"critic_failed:{last_err[:80]}"
    skipped["ok"] = True  # fail-open to avoid infinite regen loops
    return skipped


def _parse_json(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    if not t:
        return {}
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(t[start : end + 1])
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
    return {}


def reset_vision_budget_for_tests() -> None:
    with _lock:
        _package_calls.clear()
        _shot_done.clear()
