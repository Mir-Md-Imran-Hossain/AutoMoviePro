"""
AutoMovie Pro — Multimodal Vision & Real-Market Auditor (Agent 1)
================================================================
Performs zero-dummy, vision-model driven comparative auditing on rendered scene frames
against top-performing YouTube Shorts and Facebook Reels commercial benchmarks.
Uses official google-genai SDK with multi-key failover.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from pipeline.api_keys import load_api_bundle
from pipeline.compose import ffmpeg_bin

logger = logging.getLogger("VisionAuditor")

CRITIC_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-latest",
]


@dataclass
class VisionAuditResult:
    pass_verdict: bool
    hook_critique: str
    typography_critique: str
    color_and_contrast_critique: str
    missing_viral_elements: List[str] = field(default_factory=list)
    concrete_code_fixes: List[str] = field(default_factory=list)
    market_comparison_notes: str = ""
    audited_model: str = ""
    frame_count_analyzed: int = 0


def extract_probe_frames_to_disk(clip_path: Path, output_dir: Path, count: int = 2) -> List[Path]:
    """Extracts probe frames at key timestamps as JPEG files for multimodal analysis."""
    clip_path = Path(clip_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not clip_path.exists() or clip_path.stat().st_size < 1000:
        return []

    cmd_probe = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)
    ]
    try:
        dur = float(subprocess.check_output(cmd_probe, stderr=subprocess.DEVNULL).decode().strip())
    except Exception:
        dur = 3.0

    extracted = []
    ffmpeg = ffmpeg_bin()
    timestamps = [max(0.2, dur * (i + 1) / (count + 1)) for i in range(count)]

    for idx, t in enumerate(timestamps):
        out_jpg = output_dir / f"probe_f{idx}_{clip_path.stem}.jpg"
        cmd = [
            ffmpeg, "-y", "-ss", f"{t:.2f}", "-i", str(clip_path),
            "-vframes", "1", "-q:v", "2", str(out_jpg)
        ]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0 and out_jpg.exists() and out_jpg.stat().st_size > 1000:
            extracted.append(out_jpg)

    return extracted


def audit_scene_with_multimodal_vision(
    clip_path: Path,
    scene_data: Dict[str, Any],
    *,
    work_dir: Path,
    google_api_keys: Optional[List[str]] = None,
) -> VisionAuditResult:
    """
    Agent 1 Execution: Sends real frame image(s) to multimodal vision model (Gemini 3.5 Flash-Lite)
    to perform market-benchmarked critique against top commercial viral videos.
    """
    from google import genai
    from google.genai import types

    keys = google_api_keys or (load_api_bundle() or {}).get("google_keys") or []
    if not keys:
        logger.error("No Google API keys available for Multimodal Vision Auditor")
        return VisionAuditResult(
            pass_verdict=False,
            hook_critique="Audit skipped: Missing Google Vision API credentials",
            typography_critique="",
            color_and_contrast_critique="",
            missing_viral_elements=["google_vision_api_unreachable"],
            concrete_code_fixes=["Ensure valid Google API keys are loaded"],
        )

    # 1. Extract frames
    probe_dir = work_dir / "vision_probes"
    frames = extract_probe_frames_to_disk(clip_path, probe_dir, count=2)
    if not frames:
        return VisionAuditResult(
            pass_verdict=False,
            hook_critique="Failed to extract visual frames from video stream",
            typography_critique="",
            color_and_contrast_critique="",
            missing_viral_elements=["unplayable_video_stream"],
            concrete_code_fixes=["Re-encode video with valid h264 pixel format"],
        )

    # 2. Build Vision Prompt
    narr = str(scene_data.get("narration") or scene_data.get("text_card_headline") or "Educational content")
    niche = str(scene_data.get("niche") or scene_data.get("video_category") or "General Viral").title()
    scene_idx = int(scene_data.get("scene_index", 0))

    audit_prompt = f"""
You are the Chief Quality Auditor for viral commercial social media content (YouTube Shorts & Facebook Reels).
Analyze the attached video frame(s) from Scene #{scene_idx} ({niche} niche).
Planned narration/topic: "{narr}"

Compare this frame against top-performing viral commercial videos (e.g., Vox, Kurzgesagt, top financial/tech creators):
1. Semantic Dialogue-Visual Harmony: Does this frame accurately and faithfully represent what is spoken in the narration: "{narr}"? If the dialogue describes a specific structure, place, or historical/geopolitical event, is that concrete subject clearly depicted? (Strictly fail if image is generic or unrelated).
2. Zero Thematic Drift: Does this visual belong to the authentic era and world of {niche}? (Zero tolerance for modern cars/roads in ancient history, or cartoonish CGI in serious documentary).
3. Framing & Aspect Integrity: Is the visual full-bleed and natural, or is it squished, stretched, or trapped in an ugly tiny box?
4. Hook Visual & Aesthetic Quality: Is the image captivating, sharp, and cinematic with high dynamic range?
5. Typography & UI Safe Zone: Is text sharp, grammatically correct Bengali, and completely free from UI button cutoffs?
6. Pass Verdict: Answer true ONLY if the frame has BOTH high aesthetic quality AND strict semantic relevance to the dialogue. Otherwise answer false.
6. Concrete Code Fixes: List 2-3 specific, actionable technical changes the rendering engine or pipeline must make to fix these weaknesses.

Respond strictly in valid JSON format with keys:
"hook_critique": string,
"typography_critique": string,
"color_and_contrast_critique": string,
"missing_viral_elements": list of strings,
"pass_verdict": boolean,
"concrete_code_fixes": list of strings,
"market_comparison_notes": string
"""

    parts: List[Any] = []
    for fp in frames:
        parts.append(types.Part.from_bytes(data=fp.read_bytes(), mime_type="image/jpeg"))
    parts.append(types.Part.from_text(text=audit_prompt))

    # Multi-key failover loop
    last_err = None
    for key in keys:
        try:
            client = genai.Client(api_key=key)
            for model in CRITIC_MODELS:
                try:
                    resp = client.models.generate_content(
                        model=model,
                        contents=[types.Content(role="user", parts=parts)],
                        config=types.GenerateContentConfig(response_mime_type="application/json"),
                    )
                    raw_text = resp.text.strip()
                    # Clean markdown code blocks if wrapped
                    if raw_text.startswith("```"):
                        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                        raw_text = re.sub(r"\s*```$", "", raw_text)

                    data = json.loads(raw_text)
                    logger.info("Vision Auditor [Model: %s] Result: Pass=%s", model, data.get("pass_verdict"))
                    return VisionAuditResult(
                        pass_verdict=bool(data.get("pass_verdict", False)),
                        hook_critique=str(data.get("hook_critique", "")),
                        typography_critique=str(data.get("typography_critique", "")),
                        color_and_contrast_critique=str(data.get("color_and_contrast_critique", "")),
                        missing_viral_elements=list(data.get("missing_viral_elements", [])),
                        concrete_code_fixes=list(data.get("concrete_code_fixes", [])),
                        market_comparison_notes=str(data.get("market_comparison_notes", "")),
                        audited_model=model,
                        frame_count_analyzed=len(frames),
                    )
                except Exception as m_exc:
                    if "404" in str(m_exc):
                        continue
                    if "429" in str(m_exc) or "RESOURCE_EXHAUSTED" in str(m_exc):
                        logger.warning("Quota exhausted on key for model %s: %s", model, str(m_exc)[:100])
                        break
                    logger.warning("Vision audit model %s error: %s", model, str(m_exc)[:120])
        except Exception as k_exc:
            last_err = k_exc
            continue

    logger.error("All Vision Auditor models failed across all keys: %s", last_err)
    return VisionAuditResult(
        pass_verdict=False,
        hook_critique=f"Vision model evaluation failed: {last_err}",
        typography_critique="",
        color_and_contrast_critique="",
        missing_viral_elements=["vision_engine_error"],
        concrete_code_fixes=["Check API network connectivity and model endpoints"],
    )
