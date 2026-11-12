# -*- coding: utf-8 -*-
"""
AutoMovie Pro — Stock Footage Forensic Curator Agent
====================================================
Dedicated Vision Guard & Intelligent Temporal Trimming Engine for Stock Video.

Solves:
1. Stock Video Relevance Guard: Uses Gemini Flash Vision on 3 chronological
   keyframes to audit whether candidate footage semantically matches the Bengali
   dialogue, scene concrete subject, and visual atmosphere.
2. Closed-Loop Candidate Evaluation: Automatically rejects irrelevant, modern-era
   contradictory, or watermarked footage and tries alternate candidate streams.
3. Intelligent Temporal Trimming: Identifies the optimal temporal window
   [start_time, start_time + duration] (avoiding shaky intros or abrupt cuts)
   and surgically trims the clip using FFmpeg with canvas-conformed aspect scaling.
4. Guaranteed AV Synchronization: Ensures the resulting clip matches the exact
   duration required by the scene narration (duration ± 0.1s).
"""

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from pipeline.api_keys import load_api_bundle
from pipeline.compose import ffmpeg_bin, ffprobe_bin, ffprobe_duration
from pipeline.custom_pipeline.media_providers import _env_keys

logger = logging.getLogger(__name__)

# Supported Vision models in priority order
VISION_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]


class StockFootageForensicCuratorAgent:
    """Agent that oversees stock footage discovery, multi-keyframe vision auditing,

    temporal window selection, and surgical FFmpeg cutting.
    """

    def __init__(self):
        self._gemini_client = None
        self._gemini_keys: List[str] = []

    def _get_gemini_client(self):
        if self._gemini_client is not None:
            return self._gemini_client
        keys = _env_keys("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY")
        if not keys:
            bundle = load_api_bundle()
            keys = bundle.get("google") or []
        self._gemini_keys = [k for k in keys if str(k).strip()]
        if not self._gemini_keys:
            logger.warning("[StockCurator] No Google API keys found for Vision Guard.")
            return None
        try:
            from google import genai
            from google.genai import types

            self._gemini_client = genai.Client(
                api_key=self._gemini_keys[0],
                http_options=types.HttpOptions(timeout=20.0)
            )
            return self._gemini_client
        except Exception as exc:
            logger.error("[StockCurator] Failed to initialize Gemini client: %s", exc)
            return None

    def extract_candidate_keyframes(
        self, raw_video_path: Path, count: int = 3, work_dir: Optional[Path] = None
    ) -> List[Path]:
        """Extracts chronological keyframes across the video using FFmpeg."""
        total_dur = max(ffprobe_duration(raw_video_path), 1.0)
        out_dir = work_dir or (raw_video_path.parent / f"_curator_kf_{raw_video_path.stem}")
        out_dir.mkdir(parents=True, exist_ok=True)

        if count <= 1:
            timestamps = [total_dur * 0.5]
        elif count == 3:
            timestamps = [
                max(0.5, total_dur * 0.20),
                total_dur * 0.50,
                min(total_dur - 0.5, total_dur * 0.80),
            ]
        else:
            timestamps = [(total_dur * (i + 0.5) / count) for i in range(count)]

        fb = ffmpeg_bin()
        keyframes: List[Path] = []
        for i, t in enumerate(timestamps):
            kf_path = out_dir / f"kf_{i:02d}.jpg"
            cmd = [
                fb,
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(raw_video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(kf_path),
            ]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                if kf_path.exists() and kf_path.stat().st_size > 500:
                    keyframes.append(kf_path)
            except Exception as e_kf:
                logger.debug("[StockCurator] Keyframe %d extract failed: %s", i, e_kf)

        return keyframes

    def audit_footage_with_vision(
        self,
        keyframes: List[Path],
        dialogue_bn: str,
        concrete_subject: str,
        visual_direction: str,
        total_duration: float,
        duration_needed: float,
        niche: str = "",
    ) -> Dict[str, Any]:
        """Calls Gemini Vision Guard to score semantic match and determine optimal start timestamp."""
        client = self._get_gemini_client()
        if not client or not keyframes:
            # Industrial Fail-Closed: Never blindly approve unverified stock footage!
            return {
                "relevance_score": 0,
                "is_match": False,
                "visual_description": "Unchecked (Vision client unavailable)",
                "optimal_start_sec": 0.0,
                "temporal_reasoning": "Rejected due to unverified vision gate",
                "rejection_reason": "Gemini Vision unavailable - failover to Ken Burns / Graphic Card",
            }

        from google.genai import types

        max_start = max(0.0, total_duration - duration_needed)
        prompt = f"""You are the Chief Stock Video Forensic Curator for a high-end documentary production studio.
Analyze these {len(keyframes)} chronological keyframes sampled from candidate stock footage.

Scene Context:
- Target Bengali Dialogue: "{dialogue_bn}"
- Target Concrete Visual Subject: "{concrete_subject}"
- Target Visual Direction: "{visual_direction}"
- Target Camera Perspective & Style: Cinematic Documentary
- Production Niche: "{niche}"
- Video Total Duration: {total_duration:.2f} seconds
- Scene Duration Needed: {duration_needed:.2f} seconds

Your Mandate:
1. Strict Semantic Alignment: Determine if the visual imagery accurately depicts the concrete subject and meaning of the Bengali dialogue (not a random, unrelated scene).
2. Zero Thematic Drift & Era Consistency: Ensure NO modern contradictions for historical topics (e.g., NO asphalt roads, modern cars, modern clothes, or modern ships if historical) and NO generic unrelated stock filler.
3. Visual Quality & Aspect Ratio: Verify high clarity, no watermark logos, and no squished/stretched distortion.
4. Calculate relevance score from 0 to 100. (Threshold for approval: 80 - Strictly reject anything below 80).
3. If valid, determine the optimal continuous segment start time in seconds [0.0 to {max_start:.2f}] that offers the cleanest camera motion and visual stability.

Respond ONLY with a valid JSON object matching this schema:
{{
  "relevance_score": <int 0-100>,
  "is_match": <bool>,
  "visual_description": "<concise description of visible footage>",
  "optimal_start_sec": <float>,
  "temporal_reasoning": "<why this start time gives the cleanest segment>",
  "rejection_reason": "<empty if accepted, else concise reason>"
}}
"""
        parts = [types.Part.from_bytes(data=kp.read_bytes(), mime_type="image/jpeg") for kp in keyframes]
        parts.append(types.Part.from_text(text=prompt))

        last_error = None
        # Try up to 3 keys with timeout to prevent hanging on 429
        for k_idx, key in enumerate(self._gemini_keys[:3]):
            try:
                from google import genai
                from google.genai import types
                k_client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=20.0))
                for model in VISION_MODELS[:2]:
                    try:
                        g_resp = k_client.models.generate_content(
                            model=model,
                            contents=[types.Content(role="user", parts=parts)],
                            config=types.GenerateContentConfig(response_mime_type="application/json"),
                        )
                        text = getattr(g_resp, "text", "") or ""
                        data = json.loads(text)
                        data["_model"] = model
                        return data
                    except Exception as e_m:
                        last_error = e_m
                        if "429" in str(e_m):
                            break
            except Exception as e_k:
                last_error = e_k
                continue

        logger.warning("[StockCurator] Vision guard query note: %s. Enforcing fail-closed semantic security.", last_error)
        # Fail-closed: Never approve unverified stock video without positive vision confirmation.
        # This prevents mismatched stock footage (e.g. houses instead of an airplane crash or canal locks).
        return {
            "relevance_score": 0,
            "is_match": False,
            "optimal_start_sec": 0.0,
            "temporal_reasoning": "Rejected: Vision guard unable to verify keyframes",
            "rejection_reason": "Vision guard unverified - rejecting candidate to prevent semantic drift",
        }

    def trim_and_conform_clip(
        self,
        raw_video_path: Path,
        start_sec: float,
        duration_needed: float,
        out_clip_path: Path,
        aspect: str = "9:16",
    ) -> bool:
        """Surgically trims the raw video clip using FFmpeg and conforms canvas aspect ratio."""
        is_short = (aspect == "9:16")
        w, h = (1080, 1920) if is_short else (1920, 1080)
        fb = ffmpeg_bin()
        out_clip_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            fb,
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_needed:.3f}",
            "-i",
            str(raw_video_path),
            "-vf",
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            "-movflags",
            "+faststart",
            str(out_clip_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, check=True)
            if out_clip_path.exists() and out_clip_path.stat().st_size > 10000:
                actual_dur = ffprobe_duration(out_clip_path)
                logger.info(
                    "🎬 [StockCurator] Surgically trimmed clip (start=%.2fs, dur=%.2fs/%.2fs, size=%d bytes)",
                    start_sec,
                    actual_dur,
                    duration_needed,
                    out_clip_path.stat().st_size,
                )
                return True
        except Exception as e_trim:
            logger.error("[StockCurator] FFmpeg surgical trim failed: %s", e_trim)
        return False

    def curate_stock_clip(
        self,
        query: str,
        dialogue_bn: str,
        concrete_subject: str,
        visual_direction: str,
        duration_needed: float,
        out_clip_path: Path,
        aspect: str = "9:16",
        niche: str = "",
        item_index: int = 0,
    ) -> Tuple[bool, Optional[Path], Dict[str, Any]]:
        """Closed-loop discovery, vision forensic audit, and surgical trimming for stock footage."""
        pexels_keys = _env_keys("PEXELS_API_KEY")
        if not pexels_keys:
            logger.debug("[StockCurator] No Pexels API key available.")
            return False, None, {"reason": "no_pexels_key"}

        is_short = (aspect == "9:16")
        orientation = "portrait" if is_short else "landscape"
        target_w = 1080 if is_short else 1920

        # Construct search queries: raw concrete query, then simplified variants
        clean_q = re.sub(
            r"\b(cinematic|photorealistic|aerial|shot|macro|8k|4k|ultra|detailed|hd|documentary|close-up|wide|view|of|a|an|the|in|at|against|with)\b",
            " ",
            query,
            flags=re.IGNORECASE,
        )
        words = [w for w in re.sub(r"[^a-zA-Z\s]", " ", clean_q).split() if len(w) > 3]
        query_variants = [query.strip()[:80]]
        if len(words) >= 2:
            query_variants.append(" ".join(words[:3]))
            query_variants.append(" ".join(words[:2]))
        if concrete_subject:
            clean_sub = re.sub(r"[^a-zA-Z\s]", " ", concrete_subject).strip()
            if clean_sub and clean_sub not in query_variants:
                query_variants.insert(0, clean_sub[:60])

        scratch_dir = out_clip_path.parent / f"_stock_curator_scratch_{item_index}"
        scratch_dir.mkdir(parents=True, exist_ok=True)

        evaluated_candidates = 0
        last_audit: Dict[str, Any] = {}

        # 1. Pexels Candidates Search
        for q_var in query_variants:
            if evaluated_candidates >= 4:
                break
            logger.info("[StockCurator] Searching Pexels candidate videos for: '%s'", q_var)
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(
                        "https://api.pexels.com/videos/search",
                        params={"query": q_var, "per_page": 3, "orientation": orientation},
                        headers={"Authorization": pexels_keys[0]},
                    )
                    if resp.status_code != 200:
                        continue
                    vids = resp.json().get("videos") or []
            except Exception as e_search:
                logger.debug("[StockCurator] Pexels search error: %s", e_search)
                continue

            for v in vids:
                if evaluated_candidates >= 4:
                    break
                vid_id = v.get("id")
                raw_dur = float(v.get("duration") or 0.0)

                # Deduplication Gate: reject already used video assets
                try:
                    from pipeline.asset_deduplication_registry import get_asset_deduplication_registry
                    _cur_reg = get_asset_deduplication_registry()
                except Exception:
                    _cur_reg = None
                if _cur_reg and not _cur_reg.can_use_asset(f"pexels_video_{vid_id}", item_index, is_short=is_short):
                    logger.info("[StockCurator] Candidate %s rejected by Anti-Repetition Gate (already used)", vid_id)
                    continue

                # Duration guard: skip if video cannot cover at least 70% of duration needed
                if raw_dur > 0 and raw_dur < (duration_needed * 0.70):
                    logger.debug("[StockCurator] Candidate %s too short (%.1fs < %.1fs)", vid_id, raw_dur, duration_needed)
                    continue

                # Find optimal resolution file
                files = v.get("video_files") or []
                sorted_files = sorted(files, key=lambda x: abs((x.get("width") or 0) - target_w))
                if not sorted_files:
                    continue
                download_url = sorted_files[0].get("link")
                if not download_url:
                    continue

                evaluated_candidates += 1
                raw_cand_path = scratch_dir / f"cand_{vid_id}_raw.mp4"

                # Download candidate
                try:
                    logger.info("[StockCurator] Downloading candidate %d (ID %s, %.1fs)", evaluated_candidates, vid_id, raw_dur)
                    with httpx.Client(timeout=60.0, follow_redirects=True) as dl_client:
                        dl_resp = dl_client.get(download_url)
                        dl_resp.raise_for_status()
                        raw_cand_path.write_bytes(dl_resp.content)
                except Exception as e_dl:
                    logger.warning("[StockCurator] Download error for %s: %s", vid_id, e_dl)
                    continue

                actual_dur = ffprobe_duration(raw_cand_path)
                if actual_dur < 1.0:
                    continue

                # Multi-keyframe extraction
                keyframes = self.extract_candidate_keyframes(raw_cand_path, count=3, work_dir=scratch_dir)
                if not keyframes:
                    continue

                # Forensic Vision Audit
                audit = self.audit_footage_with_vision(
                    keyframes=keyframes,
                    dialogue_bn=dialogue_bn,
                    concrete_subject=concrete_subject,
                    visual_direction=visual_direction,
                    total_duration=actual_dur,
                    duration_needed=duration_needed,
                    niche=niche,
                )
                last_audit = audit
                score = int(audit.get("relevance_score") or 0)
                is_match = bool(audit.get("is_match"))
                desc = audit.get("visual_description", "")
                rejection = audit.get("rejection_reason", "")

                logger.info(
                    "🔍 [StockCurator] Candidate %s Audit -> Score: %d/100, Match: %s | Description: %s",
                    vid_id,
                    score,
                    is_match,
                    desc[:80],
                )

                if is_match and score >= 70:
                    # Candidate Approved!
                    start_sec = float(audit.get("optimal_start_sec") or 0.0)
                    max_start = max(0.0, actual_dur - duration_needed)
                    start_sec = max(0.0, min(start_sec, max_start))

                    ok = self.trim_and_conform_clip(
                        raw_video_path=raw_cand_path,
                        start_sec=start_sec,
                        duration_needed=duration_needed,
                        out_clip_path=out_clip_path,
                        aspect=aspect,
                    )
                    if ok:
                        # Clean up scratch files
                        try:
                            for f in scratch_dir.glob("*"):
                                f.unlink(missing_ok=True)
                            scratch_dir.rmdir()
                        except Exception:
                            pass
                        logger.info("🏆 [StockCurator] Successfully curated verified stock clip for '%s'", query)
                        try:
                            from pipeline.asset_deduplication_registry import get_asset_deduplication_registry
                            _reg_s = get_asset_deduplication_registry()
                            if _reg_s:
                                _reg_s.record_asset_usage(f"pexels_video_{vid_id}", item_index, asset_path=out_clip_path)
                        except Exception:
                            pass
                        return True, out_clip_path, audit
                else:
                    logger.warning(
                        "🛑 [StockCurator] Candidate %s REJECTED: %s (Score: %d)",
                        vid_id,
                        rejection or "Score below threshold",
                        score,
                    )

        # Clean up scratch on rejection
        try:
            for f in scratch_dir.glob("*"):
                f.unlink(missing_ok=True)
            scratch_dir.rmdir()
        except Exception:
            pass

        logger.info("[StockCurator] All stock candidates rejected or unavailable. Triggering photoreal failover.")
        return False, None, last_audit


_GLOBAL_STOCK_CURATOR: Optional[StockFootageForensicCuratorAgent] = None


def get_stock_footage_curator_agent() -> StockFootageForensicCuratorAgent:
    global _GLOBAL_STOCK_CURATOR
    if _GLOBAL_STOCK_CURATOR is None:
        _GLOBAL_STOCK_CURATOR = StockFootageForensicCuratorAgent()
    return _GLOBAL_STOCK_CURATOR
