#!/usr/bin/env python3
"""Black-tail + setpts fit tests (no end-frame freeze for AV matching)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.compose import ffmpeg_bin, ffprobe_duration  # noqa: E402
from pipeline.video_extend import (  # noqa: E402
    detect_black_tail,
    detect_end_freeze,
    mux_fit_av_setpts,
    trailing_black_info,
)


def _run(cmd: list) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-500:])


def make_gray_then_black(path: Path, *, content_sec: float = 2.0, black_sec: float = 1.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    g = path.with_suffix(".gray.mp4")
    b = path.with_suffix(".blk.mp4")
    # Moving gray (gradient scroll proxy via color+noise) then black
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x240:rate=25:duration={content_sec:.3f}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={content_sec:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(g),
        ]
    )
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=320x240:d={black_sec:.3f}:r=25",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:duration={black_sec:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(b),
        ]
    )
    lst = path.with_suffix(".txt")
    lst.write_text(f"file '{g.name}'\nfile '{b.name}'\n", encoding="utf-8")
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c",
            "copy",
            str(path),
        ]
    )
    return path


def frame_mean(media: Path, t: float) -> float:
    import tempfile as _tf

    out = Path(_tf.gettempdir()) / f"setpts_frm_{t:.2f}.gray"
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
            "-vf",
            "scale=80:60,format=gray",
            "-f",
            "rawvideo",
            str(out),
        ]
    )
    data = out.read_bytes()
    return sum(data) / max(1, len(data))


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        src = make_gray_then_black(td_path / "gray_black.mp4", content_sec=2.0, black_sec=1.0)
        info = trailing_black_info(src)
        assert info["has_trailing_black"], info
        gate = detect_black_tail(src)
        assert not gate.get("passed"), gate

        audio = td_path / "voice.m4a"
        _run(
            [
                ffmpeg_bin(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=500:duration=3.2",
                "-c:a",
                "aac",
                str(audio),
            ]
        )
        dest = td_path / "fitted.mp4"
        out = mux_fit_av_setpts(
            video_src=src,
            audio_src=audio,
            dest=dest,
            work=td_path,
            stem="t",
            post_silence_sec=0.8,
        )
        assert out and out.exists(), "mux_fit failed"
        assert detect_black_tail(dest).get("passed"), detect_black_tail(dest)
        # End should not be pure black
        d = ffprobe_duration(dest)
        assert frame_mean(dest, max(0.1, d - 0.3)) > 8.0
        # Should not be a long hard freeze
        fr = detect_end_freeze(dest, max_freeze_sec=1.2)
        assert fr.get("passed"), fr

    real = (
        ROOT
        / "output"
        / "Chernobyl_30_TrainCompare"
        / "clip_18"
        / "agnes_00_reveal.mp4"
    )
    if real.exists():
        assert not detect_black_tail(real).get("passed")
        print("OK real clip_18 agnes black_tail detected")

    print("OK black_tail + setpts fit (no freeze pad)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
