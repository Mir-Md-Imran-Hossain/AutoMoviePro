"""Custom pipeline — Stage 1: Topic + Titles + Tags + Script (single Grok call).

Replaces the old multi-step topic-research stack for this custom pipeline.
Saves the JSON result under Output/Short|Long/{NN}_{TitleSlug}/.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.custom_pipeline.grok_client import grok_chat
from pipeline.custom_pipeline.prompts import SYSTEM_JSON_ONLY, build_topic_research_prompt

logger = logging.getLogger(__name__)

OUTPUT_FILENAME = "topic_script.json"


def normalize_video_type(video_type: str) -> str:
    raw = str(video_type or "").strip().lower()
    if raw in ("short", "shorts", "reel", "reels"):
        return "short"
    return "long"


def duration_range(video_type: str) -> tuple[int, int]:
    return (40, 120) if normalize_video_type(video_type) == "short" else (240, 300)


def _strip_code_fence(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def parse_grok_json(text: str) -> Dict[str, Any]:
    """Parse model output into a dict; raise ValueError if invalid."""
    raw = _strip_code_fence(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Best-effort: extract first {...} block
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not m:
            raise ValueError("Grok response is not valid JSON")
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("Grok JSON root must be an object")
    return data


def pick_primary_title(payload: Dict[str, Any]) -> str:
    seo = payload.get("seo_metadata") if isinstance(payload.get("seo_metadata"), dict) else {}
    titles = seo.get("suggested_titles") or []
    if isinstance(titles, list):
        for t in titles:
            if str(t or "").strip():
                return str(t).strip()
    topic = str(seo.get("selected_topic") or "").strip()
    if topic:
        return topic
    return "Untitled_Video"


def normalize_payload(
    payload: Dict[str, Any],
    *,
    video_type: str,
) -> Dict[str, Any]:
    """Ensure seo_metadata video_type / duration fields match request."""
    kind = normalize_video_type(video_type)
    lo, hi = duration_range(kind)
    data = dict(payload)
    seo = dict(data.get("seo_metadata") or {})
    seo["video_type"] = "Shorts" if kind == "short" else "Long"
    try:
        dur = int(seo.get("target_duration_seconds") or 0)
    except (TypeError, ValueError):
        dur = 0
    if dur < lo or dur > hi:
        seo["target_duration_seconds"] = (lo + hi) // 2
    data["seo_metadata"] = seo
    scenes = data.get("script_scenes")
    if not isinstance(scenes, list):
        data["script_scenes"] = []
    return data


def save_topic_package(
    payload: Dict[str, Any],
    *,
    video_type: str,
    output_root: Optional[Path] = None,
    primary_title: Optional[str] = None,
    quality_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Save into Output/Short|Long/001_(Title)/File/Script_001_(Title).json."""
    from pipeline.custom_pipeline.package_layout import (
        create_package,
        titled_json_name,
        write_file_json,
    )
    from pipeline.custom_pipeline.script_quality_gate import evaluate_script_quality

    kind = normalize_video_type(video_type)
    title = (primary_title or pick_primary_title(payload)).strip() or "Untitled"
    paths = create_package(title=title, video_type=kind, output_root=output_root)

    script_name = titled_json_name("Script", paths.number, paths.title)
    out_path = write_file_json(paths, script_name, payload)
    # Stable alias for pipeline stages
    write_file_json(paths, "topic_script.json", payload)

    # Save script quality gate evaluation manifest
    if quality_report is None:
        quality_report = evaluate_script_quality(payload, video_type=kind)
    write_file_json(paths, "script_quality_manifest.json", quality_report)

    topic_txt = paths.file_dir / "Topic.txt"
    seo = payload.get("seo_metadata") or {}
    topic_txt.write_text(
        "\n".join(
            [
                f"Topic: {seo.get('selected_topic') or ''}",
                f"Primary Title: {title}",
                f"Video Type: {seo.get('video_type') or kind}",
                f"Duration: {seo.get('target_duration_seconds') or ''}s",
                f"Keywords: {', '.join(seo.get('seo_keywords') or [])}",
                "",
                "Suggested Titles:",
                *[f"- {t}" for t in (seo.get("suggested_titles") or [])],
            ]
        ),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "title": title,
        "package_root": str(paths.root),
        "shared_dir": str(paths.file_dir),
        "json_path": str(out_path),
        "folder_name": paths.folder_name,
        "video_uid": f"{paths.number}_{paths.video_type}_{paths.folder_name}",
        "video_type": kind,
        "number": paths.number,
        "quality_score": quality_report.get("score", 0.0),
        "quality_ok": quality_report.get("ok", False),
    }


def run_topic_research(
    *,
    niche: str,
    video_type: str = "short",
    audience: str = "সাধারণ দর্শক",
    api_keys: Optional[Sequence[str]] = None,
    output_root: Optional[Path] = None,
    temperature: float = 0.7,
    save: bool = True,
    max_dedupe_retries: int = 5,
    dedupe_threshold: float = 0.45,
) -> Dict[str, Any]:
    """Generate topic + titles + tags + script via Grok, with duplicate guard across all formats.

    If topic/script matches existing history, re-calls the API with a
    blocked-topic list until a fresh result arrives (or retries exhausted).
    """
    from pipeline.custom_pipeline.duplicate_guard import (
        DEFAULT_THRESHOLD,
        blocked_topic_list,
        build_dedupe_retry_suffix,
        find_duplicate,
        load_history,
    )

    from pipeline.custom_pipeline.script_quality_gate import (
        evaluate_script_quality,
    )

    kind = normalize_video_type(video_type)
    # Always scan across both Short and Long outputs so topics are never repeated across formats
    history = load_history(video_type=kind, output_root=output_root, include_all_formats=True)
    blocked = blocked_topic_list(history)
    attempts: List[Dict[str, Any]] = []
    payload: Dict[str, Any] = {}
    prompt = ""
    raw = ""
    last_match: Optional[Dict[str, Any]] = None
    last_quality_feedback: str = ""
    quality: Dict[str, Any] = {}

    for attempt in range(1, max(1, int(max_dedupe_retries)) + 1):
        dedupe_note = ""
        current_temp = temperature
        if attempt > 1 and (blocked or last_match):
            dedupe_note = build_dedupe_retry_suffix(blocked, match=last_match)
            if attempt >= 4:
                # Elevate temperature and inject emergency diversity directive on repeated retries
                current_temp = min(1.0, temperature + 0.15)
                dedupe_note += (
                    "\n\n⚡ জরুরি ডাইভার্সিটি ইনস্ট্রাকশন: পরিচিত সব টপিক ও কোম্পানি বাদ দিয়ে "
                    "সম্পূর্ণ আনকমন ও চমকপ্রদ অন্য কোনো আবিষ্কার, ঘটনা বা ফ্যাক্ট নিয়ে ভাবো।"
                )

        prompt = build_topic_research_prompt(
            niche=niche,
            video_type=kind,
            audience=audience,
            blocked_topics=blocked,
            dedupe_note=dedupe_note,
            quality_feedback=last_quality_feedback if attempt > 1 else "",
        )
        raw = grok_chat(
            prompt,
            system=SYSTEM_JSON_ONLY,
            api_keys=api_keys,
            json_mode=True,
            temperature=current_temp,
        )
        parsed = parse_grok_json(raw)
        payload = normalize_payload(parsed, video_type=kind)
        match = find_duplicate(payload, history, threshold=dedupe_threshold)
        quality = evaluate_script_quality(payload, video_type=kind)

        attempt_info = {
            "attempt": attempt,
            "duplicate": bool(match),
            "match": match,
            "quality_ok": bool(quality.get("ok")),
            "quality_score": quality.get("score"),
            "quality_issues": quality.get("issues"),
            "selected_topic": ((payload.get("seo_metadata") or {}).get("selected_topic")),
        }
        attempts.append(attempt_info)

        if match:
            last_match = match
            logger.warning(
                "Duplicate topic/script (score=%.2f ≥ %.2f) attempt=%s — regenerating. matched≈%s",
                float(match.get("score") or 0),
                dedupe_threshold,
                attempt,
                match.get("existing_topic"),
            )
            # Add rejected topic to blocked list for next prompt
            rej = str(((payload.get("seo_metadata") or {}).get("selected_topic")) or "").strip()
            if rej and rej not in blocked:
                blocked.insert(0, rej)
            continue

        if not quality.get("ok"):
            last_quality_feedback = quality.get("rewrite_feedback") or ""
            logger.warning(
                "Script quality rejected attempt=%s (score=%.2f): %s — regenerating with feedback.",
                attempt,
                quality.get("score", 0.0),
                quality.get("issues", []),
            )
            continue

        # Both dedupe and quality gate passed
        logger.info(
            "Topic and script accepted on attempt=%s (quality_score=%.2f, history=%s)",
            attempt,
            quality.get("score", 0.0),
            len(history),
        )
        break
    else:
        # Zero tolerance on duplicate topics
        if match:
            logger.error(
                "CRITICAL: Dedupe retries exhausted (%s attempts) and topic is still a duplicate! "
                "Refusing to emit duplicate payload for topic: %s (matched with: %s, score=%.2f)",
                max_dedupe_retries,
                ((payload.get("seo_metadata") or {}).get("selected_topic")),
                match.get("existing_topic"),
                float(match.get("score") or 0.0),
            )
            raise RuntimeError(
                f"Duplicate topic detected after {max_dedupe_retries} attempts: "
                f"'{((payload.get('seo_metadata') or {}).get('selected_topic'))}' collides with "
                f"'{match.get('existing_topic')}' (score={match.get('score')}). Aborting to prevent duplicate video."
            )
        else:
            logger.warning(
                "Quality retries exhausted — keeping last payload (quality_ok=%s, score=%.2f)",
                quality.get("ok", False),
                quality.get("score", 0.0),
            )

    quality_report = quality or evaluate_script_quality(payload, video_type=kind)

    result: Dict[str, Any] = {
        "ok": True,
        "payload": payload,
        "prompt": prompt,
        "raw_text": raw,
        "niche": (niche or "").strip(),
        "audience": (audience or "").strip(),
        "video_type": kind,
        "duration_range": list(duration_range(kind)),
        "script_quality": quality_report,
        "dedupe": {
            "threshold": dedupe_threshold,
            "history_count": len(history),
            "attempts": attempts,
            "accepted_unique": not bool(attempts and attempts[-1].get("duplicate")),
            "accepted_quality": bool(quality_report.get("ok")),
        },
    }
    if save:
        result["save"] = save_topic_package(
            payload,
            video_type=kind,
            output_root=output_root,
            quality_report=quality_report,
        )
        logger.info("Topic package saved → %s", result["save"].get("json_path"))
    return result


# Back-compat / clear public alias
generate_topic_package = run_topic_research


def __getattr__(name: str):
    if name == "DURATION_LABEL":
        from pipeline.custom_pipeline.prompts import DURATION_LABEL

        return DURATION_LABEL
    raise AttributeError(name)
