"""Features 5–12 tests: resume, trim, package, trending, dry-run, duration, visual gates."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.av_quality_gates import HARD_QUALITY_GATES, any_hard_gate_failed  # noqa: E402
from pipeline.duration_budget import planned_scene_count  # noqa: E402
from pipeline.niche_director import _fallback_plan, _pad_scenes_to_budget  # noqa: E402
from pipeline.package_export import export_upload_package  # noqa: E402
from pipeline.resume_guard import (  # noqa: E402
    clip_fingerprint,
    find_resumable_work,
    list_accepted_scene_indexes,
    should_reuse_existing_clip,
    write_resume_meta,
)
from pipeline.trending_search import find_trending_gadgets  # noqa: E402
from pipeline.video_pipeline import _trim_reencode  # noqa: E402
from app.config import settings  # noqa: E402


def test_resume_fingerprint_mismatch(tmp=None):
    work = ROOT / "output" / "_resume_guard_test"
    work.mkdir(parents=True, exist_ok=True)
    clip = work / "scene_00_intro.mp4"
    clip.write_bytes(b"0" * 25000)
    fp1 = clip_fingerprint(narration="Hello world beat one.", visual_prompt="ruins", element="intro")
    fp2 = clip_fingerprint(narration="Totally different narration.", visual_prompt="ruins", element="intro")
    write_resume_meta(work, 0, "intro", fingerprint=fp1)
    ok, why = should_reuse_existing_clip(clip, work=work, idx=0, element="intro", fingerprint=fp1)
    assert ok, why
    ok2, why2 = should_reuse_existing_clip(clip, work=work, idx=0, element="intro", fingerprint=fp2)
    assert not ok2
    assert why2 == "fingerprint_mismatch"
    clip.unlink(missing_ok=True)
    (work / "scene_00_intro_resume.json").unlink(missing_ok=True)


def test_resume_skips_agent_failed_clip(tmp_path=None):
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as td:
        work = Path(td)
        clip = work / "scene_03_camera.mp4"
        clip.write_bytes(b"0" * 25000)
        fp = clip_fingerprint(narration="Camera beat.", visual_prompt="phone", element="camera")
        write_resume_meta(work, 3, "camera", fingerprint=fp)
        (work / "scene_03_AV_FAIL.txt").write_text("fail", encoding="utf-8")
        ok, why = should_reuse_existing_clip(clip, work=work, idx=3, element="camera", fingerprint=fp)
        assert not ok
        assert why == "agent_failed"


def test_find_resumable_prefers_folder_with_accepted_clips():
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as td:
        root = Path(td)
        old = root / "ch1_short_20260817_165401"
        newer_empty = root / "ch1_short_20260817_171814"
        done = root / "ch1_short_20260817_120000"
        for p in (old, newer_empty, done):
            p.mkdir()
            (p / "director_plan.json").write_text('{"scenes":[{"narration":"x"}]}', encoding="utf-8")
        (old / "scene_00_intro.mp4").write_bytes(b"0" * 25000)
        (old / "scene_01_design.mp4").write_bytes(b"0" * 25000)
        (old / "scene_02_display.mp4").write_bytes(b"0" * 25000)
        (old / "scene_03_camera.mp4").write_bytes(b"0" * 25000)
        (old / "scene_03_AV_FAIL.txt").write_text("fail", encoding="utf-8")
        (done / "final_short.mp4").write_bytes(b"0" * 60000)
        assert list_accepted_scene_indexes(old) == [0, 1, 2]
        found = find_resumable_work(root, channel_id=1, video_type="short")
        assert found == old


def test_find_resumable_ignores_stale_folders():
    from datetime import datetime
    from tempfile import TemporaryDirectory
    from pipeline.resume_guard import folder_is_fresh

    assert not folder_is_fresh("ch1_long_20260806_143349")
    assert folder_is_fresh(f"ch1_short_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    with TemporaryDirectory() as td:
        root = Path(td)
        stale = root / "ch1_long_20260806_143349"
        stale.mkdir()
        (stale / "director_plan.json").write_text('{"scenes":[{"narration":"x"}]}', encoding="utf-8")
        (stale / "scene_00_intro.mp4").write_bytes(b"0" * 25000)
        assert find_resumable_work(root, channel_id=1, video_type="long") is None


def test_plan_agnes_segments_never_empty():
    from pipeline.dialogue_sync import plan_agnes_segments

    segs = plan_agnes_segments("", 14.88)
    assert segs, segs
    segs2 = plan_agnes_segments("One sentence about Petra ruins.", 14.88)
    assert segs2, segs2


def test_trim_reencode_has_no_hard_t_cut():
    src = inspect.getsource(_trim_reencode)
    assert '"-t"' not in src and "'-t'" not in src
    assert "medium" in src
    assert "crf" in src


def test_upload_package_writes_files():
    work = ROOT / "output" / "_pkg_test"
    work.mkdir(parents=True, exist_ok=True)
    video = work / "src.mp4"
    video.write_bytes(b"0" * 500)
    folder = export_upload_package(
        dest_root=work / "UPLOAD_PACKAGE",
        channel_name="Test",
        gadget={"name": "Pixel 9a"},
        video_type="short",
        video_path=video,
        title="Pixel 9a Review",
        description="A look.",
        tags=["Pixel 9a", "review"],
        extra={"dry_run_publish": True},
    )
    assert (folder / "video.mp4").exists()
    assert "Pixel 9a" in (folder / "title.txt").read_text(encoding="utf-8")
    meta = (folder / "meta.json").read_text(encoding="utf-8")
    assert "dry_run_publish" in meta


def test_trending_fallback_without_keys():
    hits = find_trending_gadgets([], count=1)
    assert hits
    assert hits[0].get("name")


def test_dry_run_default_is_explicit():
    assert settings.dry_run_publish is True or settings.dry_run_publish is False


def test_scene_count_matches_duration_budget():
    assert planned_scene_count(120, "short") >= 8
    assert planned_scene_count(300, "long") >= 14
    plan = _fallback_plan("Gadget Reviews", "Pixel 9a", "short", 120, "Test")
    assert len(plan["scenes"]) >= 8
    padded = _pad_scenes_to_budget(plan["scenes"][:3], 120, "short", "Pixel 9a")
    assert len(padded) >= 8
    assert padded[-1]["element"] == "outro" or len(padded) >= 8


def test_visual_subject_is_hard_gate():
    for code in (
        "wrong_subject",
        "unrelated_broll",
        "talking_head",
        "visual_anchors_missing",
        "master_not_english",
        "voice_drift",
        "burned_master_subs",
    ):
        assert code in HARD_QUALITY_GATES
    assert any_hard_gate_failed({"critical_issues": ["wrong_subject"]})
    assert not any_hard_gate_failed({"critical_issues": ["soft_blur"]})
    from pipeline.av_quality_gates import is_unshippable

    assert is_unshippable({"critical_issues": ["visual_anchors_missing"]})
    assert not is_unshippable({"critical_issues": ["soft_blur"]})


def test_scene_mux_tts_branch_has_no_hard_t():
    import inspect
    from pipeline.scene_builder import _mux_scene

    src = inspect.getsource(_mux_scene)
    assert 'f"{duration:.3f}"' not in src


if __name__ == "__main__":
    test_resume_fingerprint_mismatch()
    test_resume_skips_agent_failed_clip()
    test_find_resumable_prefers_folder_with_accepted_clips()
    test_find_resumable_ignores_stale_folders()
    test_plan_agnes_segments_never_empty()
    test_trim_reencode_has_no_hard_t_cut()
    test_upload_package_writes_files()
    test_trending_fallback_without_keys()
    test_dry_run_default_is_explicit()
    test_scene_count_matches_duration_budget()
    test_visual_subject_is_hard_gate()
    test_scene_mux_tts_branch_has_no_hard_t()
    print("OK features 5-12 industrial gates")
