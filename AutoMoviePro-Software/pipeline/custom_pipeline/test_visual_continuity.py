"""Tests — multi-still beats, seed continuity, visual mode, AV stock query."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from pipeline.custom_pipeline.visual_continuity import (
    apply_visual_mode_to_render_type,
    av_matched_stock_query,
    frames_for_duration,
    package_seed,
    shot_seed,
    split_narration_beats,
)


def test_frames_for_duration_auto():
    assert frames_for_duration(3.0) == 1
    assert frames_for_duration(5.0) == 2
    assert frames_for_duration(9.0) == 3
    assert frames_for_duration(9.0, forced=2) == 2


def test_split_narration_beats_aligns():
    text = "First secret is night mode. Second is object vanish. Third is cinematic depth."
    beats = split_narration_beats(text, 3)
    assert len(beats) == 3
    assert "night" in beats[0].lower() or "First" in beats[0]
    assert any("vanish" in b.lower() or "Second" in b for b in beats)


def test_package_and_shot_seed_stable():
    a = package_seed("/tmp/pkg_demo_xyz")
    b = package_seed("/tmp/pkg_demo_xyz")
    assert a == b
    s1 = shot_seed(a, 1, frame_index=0)
    s2 = shot_seed(a, 1, frame_index=1)
    assert s1 != s2
    assert abs(s1 - a) < 10_000  # same family


def test_visual_mode_rewrite():
    assert apply_visual_mode_to_render_type("IMAGE", "video_only") == "VIDEO"
    assert apply_visual_mode_to_render_type("VIDEO", "images_only") == "IMAGE"
    assert apply_visual_mode_to_render_type("IMAGE", "prefer_stock_video") == "STOCK_VIDEO"
    assert apply_visual_mode_to_render_type("IMAGE", "auto") == "IMAGE"


def test_av_stock_query_from_dialogue():
    q = av_matched_stock_query(
        "Super Dark AI Night captures daylight photos on your phone camera",
        {"source_camera_angle": "close-up phone screen"},
    )
    low = q.lower()
    assert "phone" in low or "camera" in low or "night" in low or "ai" in low
    assert "cinematic tech studio young man" not in low


def test_multi_still_builder_concat(tmp_path):
    from pipeline.custom_pipeline.multi_still_clip import build_multi_still_master

    # Create two tiny fake pngs via ffmpeg color source
    from pipeline.compose import ffmpeg_bin
    import subprocess

    stills = []
    for i in range(2):
        p = tmp_path / f"s{i}.png"
        subprocess.run(
            [
                ffmpeg_bin(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=blue:s=1080x1920:d=0.1",
                "-frames:v",
                "1",
                str(p),
            ],
            capture_output=True,
            check=True,
        )
        stills.append(p)
    out = tmp_path / "out.mp4"
    with mock.patch(
        "pipeline.custom_pipeline.multi_still_clip.ken_burns_from_image",
        side_effect=lambda img, outp, **kw: _fake_kb(outp, kw.get("duration", 2)),
    ):
        res = build_multi_still_master(
            stills, out, total_duration=6.0, w=1080, h=1920, shot_number=2
        )
    assert res.get("ok") is True
    assert res.get("frame_count") == 2
    assert Path(res["path"]).is_file()


def _fake_kb(outp, dur):
    from pipeline.compose import ffmpeg_bin
    import subprocess

    outp = Path(outp)
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=red:s=1080x1920:d={float(dur):.2f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(outp),
        ],
        capture_output=True,
        check=True,
    )
    return outp


def test_normalize_stock_video_type():
    from pipeline.custom_pipeline.visual_render import normalize_render_type

    assert normalize_render_type("STOCK_VIDEO") == "STOCK_VIDEO"
    assert normalize_render_type("b-roll") == "STOCK_VIDEO"
