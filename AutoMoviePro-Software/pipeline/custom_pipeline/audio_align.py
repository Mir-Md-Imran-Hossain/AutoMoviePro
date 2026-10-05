"""Improve continuous-TTS shot splits beyond pure word-count ratios.

Tries (in order):
  1) faster-whisper / whisper timestamps if installed
  2) ffmpeg silencedetect to bias cut points toward pauses
  3) fall back to existing word-ratio splitter
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)


def align_and_split_shots(
    full_audio: Path,
    texts: Sequence[str],
    out_paths: Sequence[Path],
) -> List[Path]:
    """Return per-shot audio paths; never raises — falls back to word ratios.

    Guarantees: either returns exactly len(out_paths) existing files, or falls through
    to word-ratio splitter (which callers treat as authoritative).
    """
    from pipeline.custom_pipeline.tts_client import split_audio_by_word_ratios

    if len(texts) != len(out_paths):
        raise ValueError("texts and out_paths length mismatch")
    if not texts:
        return []

    def _valid(paths: Sequence[Path]) -> bool:
        return len(paths) == len(out_paths) and all(
            Path(p).is_file() and Path(p).stat().st_size > 500 for p in paths
        )

    try:
        got = _split_with_whisper(full_audio, texts, out_paths)
        if got and _valid(got):
            logger.info("audio_align mode=whisper shots=%s", len(got))
            return list(got)
    except Exception as exc:
        logger.info("whisper align unavailable: %s", exc)

    try:
        got = _split_with_silence_bias(full_audio, texts, out_paths)
        if got and _valid(got):
            logger.info("audio_align mode=silence_bias shots=%s", len(got))
            return list(got)
    except Exception as exc:
        logger.info("silence-bias split soft-fail: %s", exc)

    logger.info("audio_align mode=word_ratio shots=%s", len(out_paths))
    return split_audio_by_word_ratios(full_audio, list(texts), list(out_paths))


def _split_with_whisper(
    full_audio: Path,
    texts: Sequence[str],
    out_paths: Sequence[Path],
) -> Optional[List[Path]]:
    # Optional dependency — skip cleanly if missing
    model = None
    try:
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(full_audio), word_timestamps=False)
        segs = list(segments)
    except Exception:
        try:
            import whisper  # type: ignore

            wmodel = whisper.load_model("base")
            result = wmodel.transcribe(str(full_audio))
            segs = result.get("segments") or []
        except Exception:
            return None

    if not segs:
        return None
    # Map cumulative text lengths to segment end times
    # Simple: allocate by word ratio but snap boundaries to nearest segment end
    from pipeline.compose import ffprobe_duration, ffmpeg_bin

    total = float(ffprobe_duration(full_audio) or 0)
    if total <= 0.1:
        return None
    weights = [max(1, len(str(t).split())) for t in texts]
    tw = float(sum(weights)) or 1.0
    ideal_ends = []
    acc = 0.0
    for w in weights:
        acc += total * (w / tw)
        ideal_ends.append(acc)
    seg_ends = []
    for s in segs:
        if isinstance(s, dict):
            seg_ends.append(float(s.get("end") or 0))
        else:
            seg_ends.append(float(getattr(s, "end", 0) or 0))
    cuts = []
    for ideal in ideal_ends[:-1]:
        nearest = min(seg_ends, key=lambda x: abs(x - ideal)) if seg_ends else ideal
        cuts.append(max(0.05, min(total - 0.05, nearest)))
    cuts.append(total)
    return _cut_ranges(full_audio, cuts, out_paths)


def _split_with_silence_bias(
    full_audio: Path,
    texts: Sequence[str],
    out_paths: Sequence[Path],
) -> Optional[List[Path]]:
    from pipeline.compose import ffprobe_duration, ffmpeg_bin

    total = float(ffprobe_duration(full_audio) or 0)
    if total <= 0.1:
        return None
    ff = ffmpeg_bin()
    cmd = [
        ff,
        "-i",
        str(full_audio),
        "-af",
        "silencedetect=noise=-30dB:d=0.25",
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    silence_ends = [
        float(m.group(1))
        for m in re.finditer(r"silence_end:\s*([0-9.]+)", r.stderr or "")
    ]
    weights = [max(1, len(str(t).split())) for t in texts]
    tw = float(sum(weights)) or 1.0
    ideal_ends = []
    acc = 0.0
    for w in weights:
        acc += total * (w / tw)
        ideal_ends.append(acc)
    cuts = []
    for ideal in ideal_ends[:-1]:
        if silence_ends:
            nearest = min(silence_ends, key=lambda x: abs(x - ideal))
            # only snap if within 0.75s of ideal
            cuts.append(nearest if abs(nearest - ideal) <= 0.75 else ideal)
        else:
            cuts.append(ideal)
    cuts.append(total)
    return _cut_ranges(full_audio, cuts, out_paths)


def _cut_ranges(full_audio: Path, ends: List[float], out_paths: Sequence[Path]) -> List[Path]:
    from pipeline.compose import ffmpeg_bin

    ff = ffmpeg_bin()
    start = 0.0
    outs: List[Path] = []
    for end, out in zip(ends, out_paths):
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        dur = max(0.2, float(end) - start)
        cmd = [
            ff,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(full_audio),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out),
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if out.is_file() and out.stat().st_size > 500:
            outs.append(out)
        start = float(end)
    return outs if len(outs) == len(out_paths) else []
