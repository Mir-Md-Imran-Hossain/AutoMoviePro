"""Deterministic timeline integrity — intentional vs accidental overlap/gap."""
from __future__ import annotations

from typing import Any

from pipeline.rendering_integrity.contract import TimelineSegment


def validate_timeline(segments: list[TimelineSegment] | list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[str] = []
    segs: list[TimelineSegment] = []
    for s in segments or []:
        if isinstance(s, TimelineSegment):
            segs.append(s)
        else:
            segs.append(
                TimelineSegment(
                    scene_id=str(s.get("scene_id") or ""),
                    start_sec=float(s.get("start_sec") or 0),
                    end_sec=float(s.get("end_sec") or 0),
                    intentional_overlap=bool(s.get("intentional_overlap")),
                    intentional_gap=bool(s.get("intentional_gap")),
                    overlap_reason=str(s.get("overlap_reason") or ""),
                    gap_reason=str(s.get("gap_reason") or ""),
                )
            )
    if not segs:
        return {"status": "BLOCK", "issues": ["empty_timeline"], "method": "DETERMINISTIC"}

    ordered = sorted(segs, key=lambda x: (x.start_sec, x.end_sec))
    # Ordering identity
    for i, seg in enumerate(ordered):
        if not (seg.scene_id or "").strip():
            issues.append(f"missing_scene_id_at_{i}")
        if seg.duration_sec < 0:
            issues.append(f"negative_duration:{seg.scene_id}")
        if seg.duration_sec == 0:
            issues.append(f"zero_duration:{seg.scene_id}")
        if seg.end_sec < seg.start_sec:
            issues.append(f"end_before_start:{seg.scene_id}")

    for i in range(1, len(ordered)):
        prev, cur = ordered[i - 1], ordered[i]
        # Overlap
        if cur.start_sec < prev.end_sec - 1e-6:
            if prev.intentional_overlap or cur.intentional_overlap:
                if not (prev.overlap_reason or cur.overlap_reason):
                    issues.append(f"intentional_overlap_missing_reason:{prev.scene_id}->{cur.scene_id}")
            else:
                issues.append(f"accidental_overlap:{prev.scene_id}->{cur.scene_id}")
        # Gap
        elif cur.start_sec > prev.end_sec + 1e-3:
            if prev.intentional_gap or cur.intentional_gap:
                if not (prev.gap_reason or cur.gap_reason):
                    issues.append(f"intentional_gap_missing_reason:{prev.scene_id}->{cur.scene_id}")
            else:
                issues.append(f"accidental_gap:{prev.scene_id}->{cur.scene_id}")

    # Contiguous concat expectation: starts should be non-decreasing scene order
    ids = [s.scene_id for s in segs]
    if len(ids) != len(set(ids)):
        issues.append("duplicate_scene_id_on_timeline")

    status = "BLOCK" if issues else "PASS"
    total = ordered[-1].end_sec - ordered[0].start_sec if ordered else 0.0
    return {
        "status": status,
        "issues": issues,
        "segment_count": len(segs),
        "total_duration_sec": round(max(0.0, total), 4),
        "method": "DETERMINISTIC",
    }


def validate_av_sync_plan(
    *,
    video_durations: list[float],
    audio_durations: list[float],
    tolerance_sec: float = 1.5,
) -> dict[str, Any]:
    issues: list[str] = []
    n = min(len(video_durations), len(audio_durations))
    if not video_durations and not audio_durations:
        return {
            "status": "UNKNOWN",
            "issues": ["av_sync_unobserved"],
            "method": "HEURISTIC",
        }
    for i in range(n):
        v, a = float(video_durations[i] or 0), float(audio_durations[i] or 0)
        if v > 0 and a > 0 and abs(v - a) > tolerance_sec:
            issues.append(f"av_duration_mismatch_scene_{i}")
    if len(video_durations) != len(audio_durations) and video_durations and audio_durations:
        issues.append("av_scene_count_mismatch")
    status = "BLOCK" if issues else "PASS"
    return {"status": status, "issues": issues, "method": "DETERMINISTIC", "tolerance_sec": tolerance_sec}
