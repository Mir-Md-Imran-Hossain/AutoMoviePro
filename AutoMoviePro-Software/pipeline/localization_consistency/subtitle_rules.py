"""Subtitle readability, identity, line-breaking (AMP-004 Phase-06)."""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence


def validate_subtitle_identity(
    *,
    cue_scene_id: str,
    cue_dialogue_id: str,
    cue_language: str,
    expected_scene_id: str,
    expected_dialogue_id: str,
    expected_language: str,
    cue_segment_id: str = "",
    expected_segment_id: str = "",
    revision_id: str = "",
    expected_revision_id: str = "",
) -> list[str]:
    issues: list[str] = []
    if expected_scene_id and cue_scene_id and cue_scene_id != expected_scene_id:
        issues.append("subtitle_scene_identity_mismatch")
    if expected_dialogue_id and cue_dialogue_id and cue_dialogue_id != expected_dialogue_id:
        issues.append("subtitle_dialogue_identity_mismatch")
    if expected_language and cue_language and cue_language.lower()[:8] != expected_language.lower()[:8]:
        issues.append("subtitle_language_mismatch")
    if expected_segment_id and cue_segment_id and cue_segment_id != expected_segment_id:
        issues.append("subtitle_segment_identity_mismatch")
    if expected_revision_id and revision_id and revision_id != expected_revision_id:
        issues.append("subtitle_revision_mismatch")
    return issues


def validate_subtitle_timing(
    cues: Sequence[dict[str, Any]],
    *,
    audio_duration_sec: Optional[float] = None,
) -> list[str]:
    issues: list[str] = []
    prev_end = -1.0
    for i, c in enumerate(cues or []):
        start = float(c.get("start_time") or c.get("start") or 0)
        end = float(c.get("end_time") or c.get("end") or 0)
        if end <= start:
            issues.append(f"subtitle_invalid_duration:{i}")
        if start < prev_end - 0.05:
            issues.append(f"subtitle_overlap:{i}")
        prev_end = end
    if audio_duration_sec and cues:
        last = float(cues[-1].get("end_time") or cues[-1].get("end") or 0)
        if last > float(audio_duration_sec) + 1.0:
            issues.append("subtitle_audio_timing_mismatch")
        if last < float(audio_duration_sec) * 0.4 and float(audio_duration_sec) > 3:
            issues.append("subtitle_audio_coverage_gap")
    return issues


def attach_speech_timing_observation(
    *,
    audio_path: Optional[str] = None,
    planned_cues: Optional[Sequence[dict[str, Any]]] = None,
    language_hint: str = "",
    speech_observation: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Feed ASR observation into localization timing authority (evidence only).

    Planned cues alone never count as actual timing PASS.
    """
    from pipeline.observation.speech_timing import (
        compare_planned_vs_observed_timing,
        observe_speech_timing,
    )

    obs = speech_observation
    if obs is None and audio_path:
        obs = observe_speech_timing(audio_path, language_hint=language_hint)
    if obs is None:
        obs = {
            "status": "OBSERVATION_UNAVAILABLE",
            "observation_executed": False,
            "reason": "no_audio_path",
            "issues": ["speech_observation_unavailable"],
        }
    comparison = compare_planned_vs_observed_timing(
        planned_cues=list(planned_cues or []),
        observed=obs,
    )
    return {
        "speech_observation": obs,
        "planned_vs_observed": comparison,
        "planned_as_actual_pass": False,
        "unknown_as_pass": False,
        "authority": "localization_consistency.subtitle_rules",
        "does_not_replace": ["AudioPlan", "VoiceIdentity", "write_srt"],
    }

def validate_reading_speed(
    text: str,
    duration_sec: float,
    *,
    max_cps: float = 17.0,
    min_duration_sec: float = 0.8,
    max_duration_sec: float = 7.0,
) -> list[str]:
    issues: list[str] = []
    chars = len((text or "").replace("\n", ""))
    dur = max(0.01, float(duration_sec or 0))
    cps = chars / dur
    if cps > max_cps * 1.35:
        issues.append(f"reading_speed_exceeded:cps={cps:.1f}")
    if dur < min_duration_sec and chars > 12:
        issues.append("subtitle_duration_too_short")
    if dur > max_duration_sec and chars < 20:
        issues.append("subtitle_duration_too_long")
    return issues


def validate_line_breaking(text: str, *, max_chars_per_line: int = 42, max_lines: int = 2) -> list[str]:
    issues: list[str] = []
    lines = [ln for ln in (text or "").splitlines() if ln.strip()] or [text or ""]
    if len(lines) > max_lines:
        issues.append("too_many_subtitle_lines")
    for ln in lines:
        if len(ln) > max_chars_per_line + 8:
            issues.append("line_too_long")
        # number/unit split
        if re.search(r"\d+\s*$", ln) and re.match(r"^\s*(kg|km|m|%|ft)\b", "".join(lines[lines.index(ln) + 1 : lines.index(ln) + 2]), re.I) if lines.index(ln) + 1 < len(lines) else False:
            issues.append("number_unit_line_break")
        if re.search(r"\d+\n\s*(kg|km|m|cm|%|ft|lb)\b", text or "", re.I):
            issues.append("number_unit_line_break")
        # orphan single short word line
    if len(lines) >= 2 and len(lines[-1].strip()) <= 2:
        issues.append("orphan_word_line")
    # name protection: don't break Mid-word Capitalized Names awkwardly — heuristic
    if re.search(r"\b[A-Z][a-z]+\n[A-Z][a-z]+\b", text or ""):
        issues.append("name_line_break")
    return issues


def suggest_semantic_line_break(text: str, *, max_chars_per_line: int = 42) -> str:
    """Prefer phrase boundaries; keep number+unit and names together."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= max_chars_per_line:
        return t
    # avoid splitting number+unit
    t = re.sub(r"(\d+)\s+(kg|km|m|cm|mm|%|ft|lb)\b", lambda m: f"{m.group(1)}\u00A0{m.group(2)}", t, flags=re.I)
    mid = len(t) // 2
    # find space near middle
    candidates = [i for i, ch in enumerate(t) if ch == " " and abs(i - mid) < max_chars_per_line // 2]
    if not candidates:
        return t
    cut = min(candidates, key=lambda i: abs(i - mid))
    return t[:cut].strip() + "\n" + t[cut:].strip()
