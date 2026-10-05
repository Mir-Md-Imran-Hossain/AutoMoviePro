#!/usr/bin/env python3
"""Tests for speech-pace / last-word gates + self-repair agent diagnose."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.av_quality_gates import (  # noqa: E402
    detect_last_word_integrity,
    detect_speech_pace,
)
from pipeline.av_self_repair_agent import diagnose_clip  # noqa: E402
from pipeline.compose import ffmpeg_bin  # noqa: E402


def _run(cmd: list) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-400:])


def make_tone_mp4(path: Path, *, seconds: float, freq: float = 440.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=gray:s=320x240:d={seconds:.3f}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:sample_rate=16000:duration={seconds:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )
    return path


def main() -> int:
    narration = (
        "Summer brought no bloom, only yellowed leaves. "
        "Milk unsellable, fruit toxic. Nature itself bore witness to the crime."
    )
    # ~18 words → est ~7.5s at 2.4 wps. Ultra-short clip = too fast.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        rushed = make_tone_mp4(td_path / "rushed.mp4", seconds=3.0)
        pace = detect_speech_pace(rushed, narration_text=narration, lang="en")
        assert not pace.get("passed"), pace
        assert "speech_pace_too_fast" in (pace.get("critical_issues") or []), pace

        # Long tone with silence-ish end still has speech energy entire time → too slow vs short text
        short_line = "Hello world."
        dragged = make_tone_mp4(td_path / "dragged.mp4", seconds=8.0)
        pace2 = detect_speech_pace(dragged, narration_text=short_line, lang="en")
        assert not pace2.get("passed"), pace2
        assert "speech_pace_too_slow" in (pace2.get("critical_issues") or []), pace2

        lw = detect_last_word_integrity(rushed, narration_text=narration)
        assert not lw.get("passed"), lw
        assert "last_word_incomplete" in (lw.get("critical_issues") or []), lw

        d = diagnose_clip(rushed, narration=narration, lang="en")
        assert d.get("needs_tts_replace"), d
        assert not d.get("passed"), d

    print("OK speech_pace + last_word + diagnose")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
