"""Bounded frame sampling — uses existing compose FFmpeg boundary only."""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional, Sequence

from pipeline.observation.common import (
    SCHEMA_FRAME_SAMPLE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_UNAVAILABLE,
    STATUS_UNKNOWN,
    unavailable,
)
from pipeline.retrieval.common import content_hash_file, strip_secrets

logger = logging.getLogger(__name__)

# Hard caps — no full-video explosion
MAX_SAMPLES_SHORT = 3  # begin/mid/end
MAX_SAMPLES_LONG = 7
SHORT_DURATION_SEC = 4.0
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def _sampling_contract(
    *,
    media_type: str,
    duration: float,
    max_samples: int,
    strategy: str,
    beat_windows: Sequence[dict[str, Any]],
    scene_cuts: Sequence[float],
    dialogue_windows: Optional[Sequence[dict[str, Any]]] = None,
) -> dict[str, Any]:
    return {
        "media_type": media_type,
        "duration_sec": round(float(duration), 3),
        "max_samples": int(max_samples),
        "strategy": strategy,
        "beat_windows": list(beat_windows or []),
        "scene_cuts": [round(float(x), 3) for x in (scene_cuts or [])],
        "dialogue_windows": list(dialogue_windows or []),
        "schema": "amp_frame_sampling_contract_v1",
    }


def _contract_hash(contract: dict[str, Any]) -> str:
    raw = json.dumps(contract, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _pick_timestamps(
    duration: float,
    *,
    beat_windows: Sequence[dict[str, Any]],
    scene_cuts: Sequence[float],
    max_samples: int,
    dialogue_windows: Optional[Sequence[dict[str, Any]]] = None,
) -> tuple[list[float], str]:
    dur = max(0.0, float(duration))
    if dur <= 0.05:
        return [0.0], "zero_duration_single"

    times: list[float] = []
    strategy = "uniform_bounded"

    # Dialogue / ASR cue windows (speech timing) — prefer mid-cue samples
    for w in dialogue_windows or []:
        start = float(w.get("start_sec") or w.get("start") or w.get("begin") or 0.0)
        end = float(w.get("end_sec") or w.get("end") or start)
        mid = (start + max(start, end)) / 2.0
        times.append(max(0.0, min(dur - 0.04, mid)))
    if times:
        strategy = "dialogue_boundary_assisted"

    # Prefer beat windows when present
    if not times:
        for w in beat_windows or []:
            start = float(w.get("start_sec") or w.get("start") or 0.0)
            end = float(w.get("end_sec") or w.get("end") or start)
            mid = (start + max(start, end)) / 2.0
            times.append(max(0.0, min(dur - 0.04, mid)))
        if times:
            strategy = "beat_boundary_preferred"
    if not times and scene_cuts:
        for c in scene_cuts:
            t = float(c)
            if 0.0 <= t < dur:
                times.append(min(dur - 0.04, max(0.0, t + 0.05)))
        if times:
            times.append(min(dur - 0.04, dur * 0.5))
            strategy = "scene_boundary_assisted"
    if not times and dur <= SHORT_DURATION_SEC:
        times = [0.0, dur * 0.5, max(0.0, dur - 0.05)]
        strategy = "short_begin_mid_end"
        max_samples = min(max_samples, MAX_SAMPLES_SHORT)
    elif not times:
        n = min(max_samples, MAX_SAMPLES_LONG)
        times = [dur * (i + 0.5) / n for i in range(n)]
        strategy = "long_uniform_bounded"

    # Dedupe + bound
    uniq: list[float] = []
    for t in sorted(times):
        t = max(0.0, min(dur - 0.04 if dur > 0.04 else 0.0, float(t)))
        if not uniq or abs(uniq[-1] - t) >= 0.08:
            uniq.append(round(t, 3))
        if len(uniq) >= max_samples:
            break
    if not uniq:
        uniq = [0.0]
    return uniq[:max_samples], strategy


def _extract_one(ffmpeg: str, media: Path, t: float, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{t:.3f}",
        "-i",
        str(media),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(dest),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and dest.exists() and dest.stat().st_size > 200
    except Exception as exc:
        logger.debug("frame extract failed t=%.3f: %s", t, exc)
        return False


def sample_frames(
    media_path: Path | str,
    *,
    out_dir: Path | str,
    asset_id: str = "",
    scene_id: str = "",
    beat_id: str = "",
    customer_id: str = "",
    channel_id: str = "",
    beat_windows: Optional[Sequence[dict[str, Any]]] = None,
    scene_cuts: Optional[Sequence[float]] = None,
    dialogue_windows: Optional[Sequence[dict[str, Any]]] = None,
    max_samples: int = MAX_SAMPLES_LONG,
    use_scene_detect: bool = False,
) -> dict[str, Any]:
    """
    Deterministic bounded sampling. IMAGE → single frame copy/reference.
    Never treats frames as semantic PASS.
    """
    media = Path(media_path)
    out = Path(out_dir)
    if not media.exists():
        return unavailable(
            schema=SCHEMA_FRAME_SAMPLE,
            tool="frame_sampling",
            reason="missing_media",
            detail=str(media),
        )

    from pipeline.compose import ffmpeg_bin, ffprobe_duration

    try:
        ch = content_hash_file(media)
    except OSError as exc:
        return unavailable(
            schema=SCHEMA_FRAME_SAMPLE,
            tool="frame_sampling",
            reason="content_hash_failed",
            detail=str(exc)[:200],
        )

    suffix = media.suffix.lower()
    is_image = suffix in IMAGE_EXTS
    duration = 0.0 if is_image else float(ffprobe_duration(media) or 0.0)

    cuts = list(scene_cuts or [])
    if use_scene_detect and not is_image and not cuts:
        try:
            from pipeline.observation.scene_boundary import observe_scene_boundaries

            obs = observe_scene_boundaries(media)
            if obs.get("status") == STATUS_PASS or obs.get("observation_executed"):
                cuts = list(obs.get("boundary_times_sec") or [])
        except Exception as exc:
            logger.debug("scene boundary assist skipped: %s", exc)

    if is_image:
        strategy = "image_single_frame"
        timestamps = [0.0]
        media_type = "image"
        max_samples = 1
    else:
        if duration <= 0.0:
            return {
                "schema": SCHEMA_FRAME_SAMPLE,
                "status": STATUS_UNKNOWN,
                "observation_executed": False,
                "provider_verified": False,
                "reason": "video_duration_unknown_or_corrupt",
                "issues": ["sampling_unknown:bad_duration"],
                "unknown_as_pass": False,
                "frames": [],
                "asset_id": asset_id,
                "scene_id": scene_id,
                "beat_id": beat_id,
                "source_path": str(media),
                "content_hash": ch,
            }
        timestamps, strategy = _pick_timestamps(
            duration,
            beat_windows=list(beat_windows or []),
            scene_cuts=cuts,
            dialogue_windows=list(dialogue_windows or []),
            max_samples=min(int(max_samples), MAX_SAMPLES_LONG),
        )
        media_type = "video"

    contract = _sampling_contract(
        media_type=media_type,
        duration=duration,
        max_samples=len(timestamps),
        strategy=strategy,
        beat_windows=list(beat_windows or []),
        scene_cuts=cuts,
        dialogue_windows=list(dialogue_windows or []),
    )
    c_hash = _contract_hash(contract)
    cache_dir = out / f"frames_{ch[:16]}_{c_hash}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta_path = cache_dir / "sampling.json"
    if meta_path.exists():
        try:
            cached = json.loads(meta_path.read_text(encoding="utf-8"))
            if cached.get("content_hash") == ch and cached.get("contract_hash") == c_hash:
                cached["cache_hit"] = True
                return cached
        except Exception:
            pass

    frames: list[dict[str, Any]] = []
    ffmpeg = ffmpeg_bin()
    for i, t in enumerate(timestamps):
        if is_image:
            dest = cache_dir / f"frame_{i:02d}_image{suffix if suffix else '.png'}"
            try:
                if not dest.exists():
                    dest.write_bytes(media.read_bytes())
                ok = dest.exists() and dest.stat().st_size > 50
            except OSError:
                ok = False
        else:
            dest = cache_dir / f"frame_{i:02d}_{int(t * 1000):07d}ms.jpg"
            ok = dest.exists() and dest.stat().st_size > 200
            if not ok:
                ok = _extract_one(ffmpeg, media, t, dest)
        if not ok:
            continue
        try:
            fch = content_hash_file(dest)
        except OSError:
            fch = ""
        frames.append(
            strip_secrets(
                {
                    "asset_id": asset_id,
                    "scene_id": scene_id,
                    "beat_id": beat_id,
                    "timestamp": float(t),
                    "frame_index": i,
                    "source_path": str(media),
                    "frame_path": str(dest),
                    "content_hash": fch,
                    "parent_content_hash": ch,
                    "customer_id": customer_id,
                    "channel_id": channel_id,
                    "semantic_pass": False,
                }
            )
        )

    if not frames:
        return {
            "schema": SCHEMA_FRAME_SAMPLE,
            "status": STATUS_UNKNOWN,
            "observation_executed": False,
            "provider_verified": False,
            "reason": "sampling_failed",
            "issues": ["observation_unknown:sampling_failed"],
            "unknown_as_pass": False,
            "creates_final_gate": False,
            "creates_ffmpeg_engine": False,
            "frames": [],
            "asset_id": asset_id,
            "scene_id": scene_id,
            "beat_id": beat_id,
            "source_path": str(media),
            "content_hash": ch,
            "sampling_contract": contract,
            "contract_hash": c_hash,
        }

    result = {
        "schema": SCHEMA_FRAME_SAMPLE,
        "status": STATUS_PASS,
        "observation_executed": True,
        "provider_verified": False,
        "semantic_pass": False,
        "unknown_as_pass": False,
        "creates_final_gate": False,
        "creates_ffmpeg_engine": False,
        "reuses_compose_ffmpeg": True,
        "asset_id": asset_id,
        "scene_id": scene_id,
        "beat_id": beat_id,
        "source_path": str(media),
        "content_hash": ch,
        "customer_id": customer_id,
        "channel_id": channel_id,
        "media_type": media_type,
        "duration_sec": duration,
        "sampling_contract": contract,
        "contract_hash": c_hash,
        "strategy": strategy,
        "frame_count": len(frames),
        "frames": frames,
        "cache_hit": False,
        "cache_dir": str(cache_dir),
    }
    try:
        meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return result
