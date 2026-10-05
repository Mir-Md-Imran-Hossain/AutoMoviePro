"""Points 7–20 deep tests: P1/P2 industrial remaining items (virtual + live angles)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

from pipeline.custom_pipeline.honest_status import honest_shippable
from pipeline.custom_pipeline.job_budget import BudgetExceeded, ensure_budget, record_spend
from pipeline.custom_pipeline.job_state import new_job_state, save_job_state
from pipeline.custom_pipeline.media_compose import _phrase_cues
from pipeline.custom_pipeline.media_generate import _quality_tier
from pipeline.custom_pipeline.pipeline_control import wall_clock_exceeded
from pipeline.custom_pipeline.visual_render import default_image_ffmpeg


def _pkg() -> Path:
    root = Path(tempfile.mkdtemp())
    pkg = root / "001_(P1P2 Test)"
    for d in ("File", "Audio", "Image", "Video"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
    return pkg


# ── 7 Audio align ─────────────────────────────────────────────
def test_audio_align_length_mismatch_raises():
    from pipeline.custom_pipeline.audio_align import align_and_split_shots

    try:
        align_and_split_shots(Path("x.m4a"), ["a"], [Path("1.m4a"), Path("2.m4a")])
        assert False
    except ValueError:
        pass


def test_audio_align_falls_back_to_word_ratio():
    from pipeline.custom_pipeline.audio_align import align_and_split_shots

    full = Path(tempfile.mkdtemp()) / "full.m4a"
    full.write_bytes(b"\x00" * 100)
    outs = [full.parent / "S01.m4a", full.parent / "S02.m4a"]

    def fake_split(audio, texts, paths):
        return [Path(p).write_bytes(b"\x00" * 600) or Path(p) for p in paths]

    with mock.patch(
        "pipeline.custom_pipeline.audio_align._split_with_whisper", return_value=None
    ), mock.patch(
        "pipeline.custom_pipeline.audio_align._split_with_silence_bias", return_value=None
    ), mock.patch(
        "pipeline.custom_pipeline.tts_client.split_audio_by_word_ratios", side_effect=fake_split
    ):
        got = align_and_split_shots(full, ["one two", "three four five"], outs)
    assert len(got) == 2


# ── 8 Character ref + 9 degraded ──────────────────────────────
def test_quality_tier_degraded_labels():
    assert _quality_tier("pexels_stock", True) == "degraded"
    assert _quality_tier("kenburns_via_pollinations", False) == "degraded"
    assert _quality_tier("agnes", False) == "ai_primary"
    assert _quality_tier("mystery_provider", False) == "ai_fallback"


def test_character_reference_resume_skip():
    from pipeline.custom_pipeline.media_generate import _ensure_character_reference

    pkg = _pkg()

    class Paths:
        image = pkg / "Image"

    Paths.image.mkdir(parents=True, exist_ok=True)
    ref = Paths.image / "character_reference.png"
    ref.write_bytes(b"\x00" * 3000)
    with mock.patch(
        "pipeline.custom_pipeline.media_generate.generate_image_with_fallback"
    ) as gen:
        out = _ensure_character_reference(
            pkg, Paths, [{"character_details": "young man"}], aspect="9:16", art="cine"
        )
    assert out == ref
    assert gen.call_count == 0


# ── 10 Ken Burns 9:16 ─────────────────────────────────────────
def test_kenburns_portrait_canvas():
    assert "1080x1920" in default_image_ffmpeg("9:16")
    assert "1920x1080" not in default_image_ffmpeg("9:16")
    assert "1920x1080" in default_image_ffmpeg("16:9")


# ── 11 Retry ops honesty ──────────────────────────────────────
def test_retry_shot_report_not_soft_ok():
    from pipeline.custom_pipeline.retry_ops import retry_media_shot

    pkg = _pkg()
    with mock.patch(
        "pipeline.custom_pipeline.retry_ops.generate_shared_media",
        return_value={"ok": False, "success_count": 1, "shot_count": 3},
    ), mock.patch(
        "pipeline.custom_pipeline.retry_ops.compose_language_shots",
        return_value={"ok": True},
    ), mock.patch(
        "pipeline.custom_pipeline.retry_ops.assemble_final_video",
        return_value={"ok": True},
    ), mock.patch(
        "pipeline.custom_pipeline.retry_ops.open_package"
    ) as op, mock.patch(
        "pipeline.custom_pipeline.retry_ops.write_json"
    ):
        class P:
            file_dir = pkg / "File"
            video_clips = pkg / "Video" / "Video Clips"
            image = pkg / "Image"
            audio = pkg / "Audio"

            def __init__(self):
                self.file_dir.mkdir(parents=True, exist_ok=True)
                self.video_clips.mkdir(parents=True, exist_ok=True)
                self.image.mkdir(parents=True, exist_ok=True)

        op.return_value = P()
        # No langs detected → ok follows shared.ok only
        report = retry_media_shot(pkg, 1, languages=[])
    assert report.get("shippable") is False
    assert report.get("partial") is True


# ── 12 Budget ─────────────────────────────────────────────────
def test_budget_cap_blocks():
    st = new_job_state(package_root=Path("."), video_type="short")
    st["budget"]["cap_units"] = 5.0
    record_spend(st, kind="video", units=4.0)
    try:
        ensure_budget(st, kind="video")  # needs 8
        assert False
    except BudgetExceeded as exc:
        assert exc.spent >= 4


# ── 13 Phrase subs ────────────────────────────────────────────
def test_phrase_cues_cover_duration():
    cues = _phrase_cues("First. Second! Third?", 6.0)
    assert len(cues) >= 2
    assert abs(cues[-1]["end"] - 6.0) < 0.1 or cues[-1]["end"] <= 6.0
    assert cues[0]["start"] == 0.0


# ── 14 Wall clock + reaper already covered; smoke here ────────
def test_wall_clock_and_reaper_import():
    assert wall_clock_exceeded(time.time() - 100, 10) is True
    from pipeline.custom_pipeline.job_state import is_stale

    st = {"status": "running", "heartbeat_at": time.time() - 9999}
    assert is_stale(st, max_silent_sec=10) is True


# ── 15 Quality gate ───────────────────────────────────────────
def test_quality_gate_missing_finals():
    from pipeline.custom_pipeline.quality_gate import run_custom_quality_gate

    pkg = _pkg()
    (pkg / "Video" / "Video Clips").mkdir(parents=True, exist_ok=True)
    with mock.patch(
        "pipeline.custom_pipeline.quality_gate.open_package"
    ) as op:

        class P:
            video_clips = pkg / "Video" / "Video Clips"
            file_dir = pkg / "File"

            def final_video_lang(self, code):
                d = pkg / "Video" / "Final Video" / code
                d.mkdir(parents=True, exist_ok=True)
                return d

        op.return_value = P()
        report = run_custom_quality_gate(pkg, languages=["English"])
    assert report["ok"] is False
    assert any("missing_final" in x or "no_shared" in x for x in report["ship_blockers"])


# ── 16 Telemetry ──────────────────────────────────────────────
def test_telemetry_writes_jsonl():
    from pipeline.custom_pipeline.telemetry import emit

    pkg = _pkg()

    class P:
        file_dir = pkg / "File"

    with mock.patch(
        "pipeline.custom_pipeline.package_layout.open_package", return_value=P()
    ):
        emit(pkg, "stage.started", "test", shot="S01")
    path = pkg / "File" / "telemetry.jsonl"
    assert path.is_file()
    line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
    data = json.loads(line)
    assert data["kind"] == "stage.started"


# ── 17 Image guard release path covered in point-5 ────────────
def test_image_claim_import():
    from pipeline.custom_pipeline.media_call_guard import claim_create, release_claim

    assert callable(claim_create) and callable(release_claim)


# ── 19 SaaS bridge ────────────────────────────────────────────
def test_custom_pipeline_enabled_flags():
    from app.custom_pipeline_bridge import custom_pipeline_enabled

    os.environ.pop("AMP_CUSTOM_PIPELINE", None)
    assert custom_pipeline_enabled() is False
    assert custom_pipeline_enabled(job_meta={"pipeline_engine": "custom"}) is True
    os.environ["AMP_CUSTOM_PIPELINE"] = "1"
    assert custom_pipeline_enabled() is True
    os.environ.pop("AMP_CUSTOM_PIPELINE", None)


# ── 20 Approval gate ──────────────────────────────────────────
def test_approval_gate_blocks_without_flag():
    from pipeline.custom_pipeline.runner import run_pipeline

    pkg = _pkg()
    topic = {
        "ok": True,
        "payload": {"script_scenes": [{"shot_number": 1, "voiceover_script": "hi"}]},
        "save": {"package_root": str(pkg), "json_path": str(pkg / "File" / "t.json")},
    }
    (pkg / "File" / "topic_script.json").write_text(
        json.dumps(topic["payload"]), encoding="utf-8"
    )
    # Parent must be Short for format check
    short_root = pkg.parent
    short_root.rename(short_root.parent / "Short") if False else None
    # Rebuild under Short/
    root = Path(tempfile.mkdtemp())
    short = root / "Short"
    short.mkdir()
    pkg2 = short / "001_(Approval Test)"
    for d in ("File", "Audio", "Image", "Video"):
        (pkg2 / d).mkdir(parents=True)
    (pkg2 / "File" / "topic_script.json").write_text(
        json.dumps(
            {
                "seo_metadata": {"video_type": "Shorts"},
                "script_scenes": [
                    {"shot_number": 1, "voiceover_script": "Hello approval gate test."}
                ],
            }
        ),
        encoding="utf-8",
    )
    with mock.patch(
        "pipeline.custom_pipeline.runner.run_topic_research",
        return_value={
            "ok": True,
            "payload": json.loads(
                (pkg2 / "File" / "topic_script.json").read_text(encoding="utf-8")
            ),
            "save": {"package_root": str(pkg2)},
        },
    ), mock.patch(
        "pipeline.custom_pipeline.runner.start_session", return_value="sess"
    ), mock.patch(
        "pipeline.custom_pipeline.runner.session_key_report", return_value={}
    ):
        result = run_pipeline(
            video_type="short",
            niche="test",
            resume_package=pkg2,
            require_approval=True,
            force=False,
            skip_localize=True,
            skip_visual=True,
            skip_tts=True,
            skip_media=True,
        )
    assert result.get("awaiting_approval") is True
    assert result.get("ok") is False
    assert (pkg2 / "File" / "AWAITING_APPROVAL.txt").is_file()


def test_honest_ship_still_holds():
    ship = honest_shippable(
        shared_success=1,
        shared_expected=2,
        finals_ok=["English"],
        expected_languages=["English", "Hindi"],
    )
    assert ship["shippable"] is False


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed.append((fn.__name__, exc))
            print(f"FAIL {fn.__name__}: {exc}")
    if failed:
        raise SystemExit(f"{len(failed)}/{len(tests)} failed")
    print(f"all {len(tests)} points-7-20 tests passed")
