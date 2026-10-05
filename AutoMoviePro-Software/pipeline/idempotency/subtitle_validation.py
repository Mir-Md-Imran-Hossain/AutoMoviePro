"""Subtitle validation (BUILD-04E)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional, Sequence

TIMING_TOLERANCE_SEC = 0.05


def parse_srt(content: str) -> list[dict[str, Any]]:
    blocks = re.split(r"\n\s*\n", (content or "").strip())
    cues: list[dict[str, Any]] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        try:
            cue_id = str(lines[0])
            times = lines[1]
            m = re.match(
                r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",
                times,
            )
            if not m:
                continue
            start = _srt_time_to_sec(m.group(1))
            end = _srt_time_to_sec(m.group(2))
            text = "\n".join(lines[2:])
            cues.append(
                {
                    "cue_id": cue_id,
                    "start_time": start,
                    "end_time": end,
                    "text": text,
                }
            )
        except Exception:
            continue
    return cues


def _srt_time_to_sec(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def validate_cue_timestamps(cues: Sequence[dict[str, Any]]) -> tuple[bool, str]:
    prev_end = -1.0
    for i, c in enumerate(cues):
        start = float(c.get("start_time") or 0)
        end = float(c.get("end_time") or 0)
        if start < 0:
            return False, f"cue_{i}_negative_start"
        if end <= start:
            return False, f"cue_{i}_end_before_start"
        if start < prev_end - TIMING_TOLERANCE_SEC:
            return False, f"cue_{i}_overlap"
        prev_end = end
    return True, "ok"


def validate_subtitle_bindings(
    cues: Sequence[dict[str, Any]],
    *,
    expected_scene_id: str,
    expected_dialogue_id: str,
    expected_language: str,
    expected_segment_id: str = "",
) -> tuple[bool, str]:
    for i, c in enumerate(cues):
        if c.get("scene_id") and str(c["scene_id"]) != expected_scene_id:
            return False, f"cue_{i}_wrong_scene"
        if c.get("dialogue_id") and str(c["dialogue_id"]) != expected_dialogue_id:
            return False, f"cue_{i}_wrong_dialogue"
        if c.get("language") and str(c["language"]).lower()[:8] != expected_language.lower()[:8]:
            return False, f"cue_{i}_wrong_language"
        if expected_segment_id and c.get("segment_id") and str(c["segment_id"]) != expected_segment_id:
            return False, f"cue_{i}_wrong_segment"
    return True, "ok"


def validate_scene_margins(
    *,
    audio_duration_sec: float,
    scene_duration_sec: float,
    leading_gap_sec: float = 0.5,
    trailing_gap_sec: float = 0.5,
) -> tuple[bool, str]:
    if scene_duration_sec <= 0:
        return True, "no_scene_duration"
    required = audio_duration_sec + leading_gap_sec + trailing_gap_sec
    if required > scene_duration_sec + TIMING_TOLERANCE_SEC:
        return False, f"margin_impossible:need={required:.3f},scene={scene_duration_sec:.3f}"
    return True, "ok"


def load_subtitle_meta(srt_path: Path) -> dict[str, Any]:
    meta_path = srt_path.with_suffix(srt_path.suffix + ".meta.json")
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def validate_meta_bindings(meta: dict[str, Any], spec_meta: dict[str, Any]) -> tuple[bool, str]:
    for key in ("scene_id", "dialogue_id", "language", "segment_id"):
        expected = str(spec_meta.get(key) or "")
        actual = str(meta.get(key) or "")
        if expected and actual and actual != expected:
            return False, f"meta_wrong_{key}"
    if spec_meta.get("text_hash") and meta.get("text_hash"):
        if str(spec_meta["text_hash"]) != str(meta["text_hash"]):
            return False, "meta_text_hash_mismatch"
    return True, "ok"


def validate_subtitle_asset(
    srt_path: str,
    *,
    spec_meta: dict[str, Any],
    expected_text_hash: str = "",
    audio_duration_sec: float = 0.0,
) -> tuple[bool, str]:
    p = Path(srt_path)
    if not p.is_file() or p.stat().st_size < 10:
        return False, "missing_or_empty"
    try:
        content = p.read_text(encoding="utf-8")
    except Exception:
        return False, "unreadable"
    cues = parse_srt(content)
    if not cues:
        return False, "malformed_or_empty"
    ok, reason = validate_cue_timestamps(cues)
    if not ok:
        return False, reason
    meta = load_subtitle_meta(p)
    if meta:
        ok, reason = validate_meta_bindings(meta, spec_meta)
        if not ok:
            return False, reason
    ok, reason = validate_subtitle_bindings(
        cues,
        expected_scene_id=str(spec_meta.get("scene_id") or ""),
        expected_dialogue_id=str(spec_meta.get("dialogue_id") or ""),
        expected_language=str(spec_meta.get("language") or "en"),
        expected_segment_id=str(spec_meta.get("segment_id") or ""),
    )
    if not ok:
        return False, reason
    cue_ids = [str(c.get("cue_id") or "") for c in cues]
    if len(cue_ids) != len(set(cue_ids)):
        return False, "duplicate_cue_id"
    dlg_ids = [str(c.get("dialogue_id") or spec_meta.get("dialogue_id") or "") for c in cues]
    if len(set(dlg_ids)) > 1:
        return False, "duplicate_dialogue_mapping"
    dur = float(cues[-1].get("end_time") or 0)
    if audio_duration_sec > 0 and dur > audio_duration_sec + 0.25:
        return False, "exceeds_audio_duration"
    if expected_text_hash and spec_meta.get("text_hash") and spec_meta["text_hash"] != expected_text_hash:
        return False, "text_hash_mismatch"
    scene_dur = float(spec_meta.get("scene_duration_sec") or 0)
    if scene_dur > 0:
        ok, reason = validate_scene_margins(
            audio_duration_sec=audio_duration_sec or dur,
            scene_duration_sec=scene_dur,
            leading_gap_sec=float(spec_meta.get("leading_gap_sec") or 0.5),
            trailing_gap_sec=float(spec_meta.get("trailing_gap_sec") or 0.5),
        )
        if not ok:
            return False, reason
    return True, "ok"
