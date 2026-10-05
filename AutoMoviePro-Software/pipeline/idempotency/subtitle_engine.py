"""Subtitle cue generation with explicit identity binding (BUILD-04E)."""
from __future__ import annotations

import re
from typing import Any, List

from pipeline.subtitle_align import cues_to_srt


def generate_bound_cues(
    text: str,
    audio_duration_sec: float,
    *,
    scene_id: str,
    dialogue_id: str,
    segment_id: str = "",
    language: str = "en",
    words_per_chunk: int = 6,
) -> list[dict[str, Any]]:
    """Audio-relative timing (0 .. audio_duration). Each cue carries explicit identity."""
    dur = max(1.0, float(audio_duration_sec))
    body = re.sub(r"\s+", " ", (text or "").strip()) or " "
    try:
        from pipeline.subtitle_burn import chunk_words_for_cues

        max_chars = 28 if str(language or "en").lower()[:2] != "en" else 36
        chunks = chunk_words_for_cues(body, words_per_chunk=words_per_chunk, max_chars_per_line=max_chars)
    except Exception:
        words = body.split()
        chunks = []
        buf: List[str] = []
        for w in words:
            buf.append(w)
            if len(buf) >= words_per_chunk:
                chunks.append(" ".join(buf))
                buf = []
        if buf:
            chunks.append(" ".join(buf))
    if not chunks:
        chunks = [body]

    n = len(chunks)
    cues: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        start = dur * (i / n)
        end = dur * ((i + 1) / n)
        cues.append(
            {
                "cue_id": str(i + 1),
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "text": chunk,
                "scene_id": scene_id,
                "dialogue_id": dialogue_id,
                "segment_id": segment_id,
                "language": language,
            }
        )
    return cues


def cues_to_srt_file(cues: list[dict[str, Any]]) -> str:
    return cues_to_srt(
        [
            {
                "index": c.get("cue_id"),
                "start": c.get("start_time"),
                "end": c.get("end_time"),
                "text": c.get("text"),
            }
            for c in cues
        ]
    )
