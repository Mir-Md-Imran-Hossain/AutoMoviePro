"""Subtitle alignment — proportional baseline + optional WhisperX adapter.

T008: evaluate; do not force WhisperX install on low-RAM Windows hosts.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?…])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def proportional_cues(
    text: str,
    duration_sec: float,
    *,
    max_cps: float = 18.0,
    min_cue_sec: float = 0.7,
    max_cue_sec: float = 6.0,
    is_short: bool = False,
    words_per_chunk: int | None = None,
) -> List[Dict[str, Any]]:
    """Proportional time allocation for subtitle cues — sentence-level for 16:9, punchy 1-3 words for 9:16 shorts."""
    if is_short or words_per_chunk:
        wpc = words_per_chunk or 2
        raw_words = (text or "").split()
        chunks: List[str] = []
        wi = 0
        while wi < len(raw_words):
            rem = len(raw_words) - wi
            if rem == 4:
                take = 2
            elif rem == 1 and chunks:
                chunks[-1] += " " + raw_words[wi]
                break
            else:
                take = min(wpc, rem)
            chunks.append(" ".join(raw_words[wi : wi + take]))
            wi += take
        sentences = chunks or [text or ""]
        min_cue_sec = min(min_cue_sec, 0.3)
        max_cue_sec = min(max_cue_sec, 2.0)
    else:
        sentences = split_sentences(text)
        if not sentences:
            words = (text or "").split()
            sentences = [" ".join(words[i : i + 8]) for i in range(0, len(words), 8)] or [text or ""]
    weights = [max(1, len(s)) for s in sentences]
    total_w = float(sum(weights)) or 1.0
    dur = max(0.5, float(duration_sec))
    cues: List[Dict[str, Any]] = []
    t = 0.0
    for i, sent in enumerate(sentences):
        share = weights[i] / total_w
        span = max(min_cue_sec, min(max_cue_sec, dur * share))
        # CPS soft adjust
        cps = len(sent) / max(0.1, span)
        if cps > max_cps:
            span = min(max_cue_sec, max(min_cue_sec, len(sent) / max_cps))
        end = min(dur, t + span)
        if i == len(sentences) - 1:
            end = dur
        if end <= t:
            end = min(dur, t + min_cue_sec)
        cues.append(
            {
                "index": i + 1,
                "start": round(t, 3),
                "end": round(end, 3),
                "text": sent,
                "method": "proportional",
            }
        )
        t = end
    return cues


def validate_cues(
    cues: Sequence[Dict[str, Any]],
    *,
    duration_sec: float,
    spoken_text: str = "",
) -> Dict[str, Any]:
    issues: List[str] = []
    dur = max(0.0, float(duration_sec))
    prev_end = -1.0
    for c in cues:
        start = float(c.get("start") or 0)
        end = float(c.get("end") or 0)
        if start < 0:
            issues.append(f"cue_{c.get('index')}_start_neg")
        if end <= start:
            issues.append(f"cue_{c.get('index')}_end_le_start")
        if end > dur + 0.05:
            issues.append(f"cue_{c.get('index')}_past_duration")
        if start < prev_end - 0.01:
            issues.append(f"cue_{c.get('index')}_overlap")
        prev_end = max(prev_end, end)
        text = str(c.get("text") or "")
        if len(text) > 84:
            issues.append(f"cue_{c.get('index')}_too_long_line")
    # Spoken words coverage (loose)
    if spoken_text:
        spoken_toks = set(re.findall(r"[a-z0-9\u0980-\u09FF]{3,}", spoken_text.lower()))
        cue_toks = set(
            re.findall(
                r"[a-z0-9\u0980-\u09FF]{3,}",
                " ".join(str(c.get("text") or "") for c in cues).lower(),
            )
        )
        if spoken_toks and len(spoken_toks & cue_toks) / max(1, len(spoken_toks)) < 0.5:
            issues.append("spoken_words_mismatch")
    passed = not issues
    return {
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "issues": issues,
        "cue_count": len(cues),
    }


def whisperx_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("whisperx") is not None
    except Exception:
        return False


def align_with_whisperx(
    audio_path: str,
    text: str = "",
    *,
    language: str = "en",
) -> Dict[str, Any]:
    """
    Optional path. Returns UNKNOWN/REJECT if whisperx not installed.
    Does not download models in unit tests.
    """
    if not whisperx_available():
        return {
            "ok": False,
            "verdict": "UNKNOWN",
            "method": "whisperx",
            "issues": ["whisperx_not_installed"],
            "cues": [],
            "recommendation": "WRAP_LATER",
        }
    # Soft import only when present — still may need torch/CUDA
    try:
        import whisperx  # type: ignore

        _ = whisperx  # noqa: F841
        return {
            "ok": False,
            "verdict": "UNKNOWN",
            "method": "whisperx",
            "issues": ["whisperx_installed_but_runtime_not_invoked_in_v0"],
            "cues": [],
            "recommendation": "WRAP",
            "note": "Invoke in dedicated worker with model cache; keep proportional fallback",
        }
    except Exception as exc:
        return {
            "ok": False,
            "verdict": "FAIL",
            "method": "whisperx",
            "issues": [f"whisperx_import:{exc}"],
            "cues": [],
            "recommendation": "REJECT_RUNTIME",
        }


def evaluate_alignment_methods(
    text: str,
    duration_sec: float,
    *,
    audio_path: str = "",
) -> Dict[str, Any]:
    """Side-by-side evaluation record for OPEN_SOURCE_EVALUATION / T008."""
    prop = proportional_cues(text, duration_sec)
    prop_v = validate_cues(prop, duration_sec=duration_sec, spoken_text=text)
    wx = align_with_whisperx(audio_path, text) if audio_path else {
        "ok": False,
        "verdict": "UNKNOWN",
        "method": "whisperx",
        "issues": ["no_audio_path"],
        "recommendation": "DEFER",
    }
    decision = "KEEP_PROPORTIONAL_PRIMARY"
    if wx.get("ok") and prop_v.get("passed"):
        decision = "WRAP_WHISPERX_WITH_FALLBACK"
    elif not whisperx_available():
        decision = "DEFER_WHISPERX_KEEP_PROPORTIONAL"

    return {
        "proportional": {"cues": prop, "validation": prop_v},
        "whisperx": wx,
        "whisperx_installed": whisperx_available(),
        "decision": decision,
        "license_note": "Verify WhisperX + model licenses before vendor/wrap",
        "windows_ram_risk": "high_on_2gb_hosts",
    }


def cues_to_srt(cues: Sequence[Dict[str, Any]]) -> str:
    def fmt(t: float) -> str:
        ms = int(round(max(0.0, t) * 1000))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    lines: List[str] = []
    for c in cues:
        lines.append(str(c.get("index") or len(lines) + 1))
        lines.append(f"{fmt(float(c.get('start') or 0))} --> {fmt(float(c.get('end') or 0))}")
        lines.append(str(c.get("text") or ""))
        lines.append("")
    return "\n".join(lines)
