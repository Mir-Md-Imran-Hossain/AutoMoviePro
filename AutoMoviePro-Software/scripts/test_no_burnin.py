"""Feature 3 tests: never burn English into master frames."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.scene_builder import master_mux_vf  # noqa: E402
from pipeline.localization import write_srt  # noqa: E402


def test_english_master_never_gets_drawtext():
    os.environ.pop("AMP_BURN_MASTER_SUBS", None)
    vf = master_mux_vf("1080x1920", subtitle_text="Today we review Pixel 9a.", subtitle_lang="en")
    assert "drawtext" not in vf
    os.environ["AMP_BURN_MASTER_SUBS"] = "1"
    try:
        vf2 = master_mux_vf("1080x1920", subtitle_text="Today we review Pixel 9a.", subtitle_lang="en")
        assert "drawtext" not in vf2, vf2
        vf3 = master_mux_vf("1080x1920", subtitle_text="আজকের রিভিউ", subtitle_lang="bn")
        assert "drawtext" in vf3
    finally:
        os.environ.pop("AMP_BURN_MASTER_SUBS", None)


def test_empty_subs_clean_filter():
    vf = master_mux_vf("1280x720", subtitle_text="", subtitle_lang="en")
    assert vf.startswith("scale=")
    assert "drawtext" not in vf


def test_soft_srt_not_empty(tmp_path_style: Path | None = None):
    work = ROOT / "output" / "_burnin_test"
    work.mkdir(parents=True, exist_ok=True)
    audio = work / "dummy.m4a"
    # tiny valid-enough file for write_srt duration probe — ffprobe may return 0 → max(1.0)
    audio.write_bytes(b"\x00" * 64)
    srt = work / "english_master.srt"
    write_srt("Today we review the Pixel 9a in one tight look.", audio, srt)
    body = srt.read_text(encoding="utf-8")
    assert "Pixel 9a" in body
    assert "-->" in body
    srt.unlink(missing_ok=True)
    audio.unlink(missing_ok=True)


if __name__ == "__main__":
    test_english_master_never_gets_drawtext()
    test_empty_subs_clean_filter()
    test_soft_srt_not_empty()
    print("OK feature3 no english burn-in")
