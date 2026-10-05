#!/usr/bin/env python3
"""Train-loop confirmation: agent catches F1–F12 subtle faults and does not ship them."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.agent_chat import try_local_faq  # noqa: E402
from pipeline.agent_playbook import should_skip_gemini_critic  # noqa: E402
from pipeline.av_quality_gates import (  # noqa: E402
    HARD_QUALITY_GATES,
    detect_burned_master_subs,
    detect_english_master_narration,
    detect_visual_anchor_lock,
    detect_voice_sidecar_lock,
    is_unshippable,
    promote_missed_visual_keywords,
)
from pipeline.av_self_repair_agent import diagnose_clip, run_av_self_repair_agent  # noqa: E402
from pipeline.av_sync_critic import _normalize_result  # noqa: E402
from pipeline.compose import ffmpeg_bin  # noqa: E402
from pipeline.master_lang import ensure_english_text, looks_like_english_master  # noqa: E402
from pipeline.tts_reuse import write_tts_sidecar  # noqa: E402


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


def test_bangla_master_is_hard_fail():
    bn = "আজকের রিভিউতে Pixel 9a এর ব্যাটারি দেখব ধন্যবাদ।"
    gate = detect_english_master_narration(bn, lang="en")
    assert not gate.get("passed"), gate
    assert "master_not_english" in (gate.get("critical_issues") or []), gate
    assert "master_not_english" in HARD_QUALITY_GATES
    with tempfile.TemporaryDirectory() as td:
        clip = make_tone_mp4(Path(td) / "bn.mp4", seconds=4.0)
        d = diagnose_clip(clip, narration=bn, lang="en")
        assert d.get("needs_language_repair"), d
        assert "master_not_english" in (d.get("hard_hits") or []), d
        assert not d.get("passed"), d


def test_english_documentary_not_flagged_bangla():
    from pipeline.master_lang import looks_like_english_master

    line = "In the heart of ancient Egypt, a pharaoh's tomb was discovered, shrouded in mystery."
    assert looks_like_english_master(line), line
    gate = detect_english_master_narration(line, lang="en")
    assert gate.get("passed"), gate


def test_visual_anchor_missing_is_hard_fail():
    gate = detect_visual_anchor_lock(
        prompt="cinematic forest mist, slow drone, no text",
        product_name="Pixel 9a",
        keywords=["Pixel 9a", "unboxing"],
        narration="The Pixel 9a unboxing shows the teal body.",
    )
    assert not gate.get("passed"), gate
    assert "visual_anchors_missing" in (gate.get("critical_issues") or []), gate
    ok = detect_visual_anchor_lock(
        prompt="Pixel 9a unboxing teal body close-up",
        product_name="Pixel 9a",
        keywords=["Pixel 9a", "unboxing"],
        narration="The Pixel 9a unboxing shows the teal body.",
    )
    assert ok.get("passed"), ok
    empty = detect_visual_anchor_lock(prompt="", product_name="", keywords=[], narration="Hello.")
    assert empty.get("passed"), empty
    # Spoken verbs must not hard-fail a prompt that already names the product
    from pipeline.prompt_hardening import required_visual_tokens

    req = required_visual_tokens(
        keywords=["Pixel 9a"],
        narration="The Pixel 9a unboxing shows the teal body.",
        product_name="Pixel 9a",
    )
    assert not any(t.lower() in {"show", "shows", "showing"} for t in req), req


def test_kore_sidecar_is_voice_drift():
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        audio = work / "narration_00.m4a"
        audio.write_bytes(b"0" * 1200)
        write_tts_sidecar(audio, "Hello world from the locked narrator.", voice_name="Kore")
        gate = detect_voice_sidecar_lock(work, idx=0)
        assert not gate.get("passed"), gate
        assert "voice_drift" in (gate.get("critical_issues") or []), gate
        clip = make_tone_mp4(work / "clip.mp4", seconds=3.0)
        d = diagnose_clip(
            clip,
            narration="Hello world from the locked narrator.",
            lang="en",
            work=work,
            idx=0,
        )
        assert "voice_drift" in (d.get("hard_hits") or []), d
        assert d.get("needs_tts_replace"), d


def test_language_repair_without_live_tts():
    bn = "আজকের গ্যাজেট রিভিউ ধন্যবাদ।"
    out, meta = ensure_english_text(bn, google_api_keys=[], field="narration", topic="Pixel 9a")
    assert looks_like_english_master(out), (out, meta)
    assert meta.get("repaired"), meta
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        clip = make_tone_mp4(work / "src.mp4", seconds=3.0)
        dest = work / "out.mp4"
        report = run_av_self_repair_agent(
            media=clip,
            video_src=clip,
            dest=dest,
            narration=bn,
            google_api_keys=[],
            work=work,
            idx=0,
            prompt="Pixel 9a handheld close-up",
            product_name="Pixel 9a",
            keywords=["Pixel 9a"],
        )
        assert report.get("language_repair", {}).get("repaired"), report
        assert report.get("language_repair", {}).get("ok"), report
        assert "master_not_english" not in (report.get("final_hard_hits") or []), report
        # Diagnose of the ORIGINAL Bangla line must still be a hard fail
        raw = diagnose_clip(clip, narration=bn, lang="en")
        assert raw.get("needs_language_repair"), raw


def test_visual_only_does_not_count_as_agent_pass():
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        # Short English line ~ matching 3s tone so audio gates are closer to pass
        narr = "Hello world."
        clip = make_tone_mp4(work / "ok_audio.mp4", seconds=3.5)
        dest = work / "out.mp4"
        report = run_av_self_repair_agent(
            media=clip,
            video_src=clip,
            dest=dest,
            narration=narr,
            google_api_keys=[],
            work=work,
            idx=1,
            prompt="cinematic forest mist no product",
            product_name="Pixel 9a",
            keywords=["Pixel 9a"],
            force_tts_clarity=False,
        )
        d = diagnose_clip(
            clip,
            narration=narr,
            lang="en",
            prompt="cinematic forest mist no product",
            product_name="Pixel 9a",
            keywords=["Pixel 9a"],
        )
        assert d.get("needs_visual_regen"), d
        assert not report.get("passed"), report
        assert report.get("needs_visual_regen") or report.get("action") == "visual_regen_required"


def test_skip_critic_opt_in_only():
    prev = os.environ.pop("AMP_SKIP_GEMINI_CRITIC", None)
    try:
        assert not should_skip_gemini_critic({"passed": True}, visual_passed=True)
        os.environ["AMP_SKIP_GEMINI_CRITIC"] = "1"
        assert should_skip_gemini_critic({"passed": True}, visual_passed=True)
    finally:
        if prev is None:
            os.environ.pop("AMP_SKIP_GEMINI_CRITIC", None)
        else:
            os.environ["AMP_SKIP_GEMINI_CRITIC"] = prev


def test_agent_chat_knows_quality_contract():
    en = try_local_faq("Why is the Charon voice changing to Kore?", "en")
    assert "Charon" in en
    bn = try_local_faq("ইংরেজি মাস্টার কেন?", "bn")
    assert "ইংরেজি" in bn or "Charon" in bn or "মাস্টার" in bn
    pic = try_local_faq("wrong picture but audio is fine", "en")
    assert "FAIL" in pic or "visual" in pic.lower()
    mixed = try_local_faq("generate video has wrong picture", "en")
    assert "FAIL" in mixed or "visual" in mixed.lower()


def test_unlabeled_tts_is_voice_drift():
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        audio = work / "narration_00.m4a"
        audio.write_bytes(b"0" * 1200)
        gate = detect_voice_sidecar_lock(work, idx=0)
        assert not gate.get("passed"), gate
        assert "voice_drift" in (gate.get("critical_issues") or []), gate


def test_burned_master_subs_detected_and_stripped():
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        (work / "scene_00_feature_a1.mp4.vf.txt").write_text(
            "scale=1080:1920,drawtext=text='Hello Pixel'",
            encoding="utf-8",
        )
        gate = detect_burned_master_subs(work, idx=0, lang="en")
        assert not gate.get("passed"), gate
        assert "burned_master_subs" in HARD_QUALITY_GATES
        clip = make_tone_mp4(work / "src.mp4", seconds=2.5)
        dest = work / "out.mp4"
        d0 = diagnose_clip(clip, narration="Hello world.", lang="en", work=work, idx=0)
        assert d0.get("needs_burnin_strip"), d0
        report = run_av_self_repair_agent(
            media=clip,
            video_src=clip,
            dest=dest,
            narration="Hello world.",
            google_api_keys=[],
            work=work,
            idx=0,
            force_tts_clarity=False,
        )
        assert any(
            (s.get("repair") == "strip_master_drawtext") for s in (report.get("steps") or [])
        ) or "burned_master_subs" not in (report.get("final_hard_hits") or []), report
        leftover = []
        for p in work.glob("scene_00*.vf.txt"):
            if "drawtext" in p.read_text(encoding="utf-8", errors="ignore").lower():
                leftover.append(p.name)
        assert not leftover, leftover


def test_missed_keywords_are_hard_fail():
    promoted = promote_missed_visual_keywords(
        {
            "passed": True,
            "match_score": 88,
            "missed_keywords": ["Pixel 9a"],
            "critical_issues": [],
            "issues": [],
            "raw": {},
        },
        keywords=["Pixel 9a", "unboxing"],
        product_name="Pixel 9a",
    )
    assert not promoted.get("passed"), promoted
    assert "visual_anchors_missing" in (promoted.get("critical_issues") or [])
    skipped = promote_missed_visual_keywords(
        {
            "passed": False,
            "missed_keywords": ["Pixel 9a"],
            "critical_issues": [],
            "raw": {"fallback": True},
        },
        keywords=["Pixel 9a"],
        product_name="Pixel 9a",
    )
    assert "visual_anchors_missing" not in (skipped.get("critical_issues") or [])
    norm = _normalize_result(
        {
            "match_score": 85,
            "passed": True,
            "issues": [],
            "critical_issues": [],
            "missed_keywords": ["Pixel 9a"],
            "matched_keywords": [],
        },
        ["Pixel 9a"],
        "cinematic forest",
        "The Pixel 9a unboxing.",
        "Pixel 9a",
        "intro",
    )
    assert not norm.get("passed"), norm
    assert "visual_anchors_missing" in (norm.get("critical_issues") or [])
    assert is_unshippable(norm)

    covered = promote_missed_visual_keywords(
        {
            "passed": True,
            "match_score": 74,
            "missed_keywords": ["The Mysterious Death of King Tut"],
            "matched_keywords": ["King Tut", "Tomb", "Mystery"],
            "critical_issues": [],
            "issues": [],
            "visual_summary": "Camera pushes into King Tut tomb chamber",
            "raw": {},
        },
        keywords=["King Tut", "Tomb", "Mystery"],
        product_name="The Mysterious Death of King Tut",
    )
    assert "visual_anchors_missing" not in (covered.get("critical_issues") or []), covered
    assert covered.get("passed") is True, covered


def test_abstract_missed_keywords_are_not_unshippable():
    from pipeline.prompt_hardening import is_non_visual_anchor

    assert is_non_visual_anchor("storytellers")
    assert is_non_visual_anchor("macro")
    assert not is_non_visual_anchor("Pixel 9a")
    skipped = promote_missed_visual_keywords(
        {
            "passed": False,
            "match_score": 45,
            "missed_keywords": ["storytellers", "macro"],
            "matched_keywords": ["Apple iPhone 15 Pro", "camera"],
            "critical_issues": ["visual_anchors_missing"],
            "issues": ["visual_anchors_missing:storytellers"],
            "raw": {},
        },
        keywords=["Apple iPhone 15 Pro", "storytellers", "macro"],
        product_name="Apple iPhone 15 Pro",
    )
    assert "visual_anchors_missing" not in (skipped.get("critical_issues") or []), skipped
    assert not is_unshippable(
        {
            "critical_issues": ["visual_anchors_missing"],
            "missed_keywords": ["storytellers", "macro"],
            "issues": ["visual_anchors_missing:storytellers", "visual_anchors_missing:macro"],
        }
    )
    assert is_unshippable({"critical_issues": ["visual_anchors_missing"]})
    assert is_unshippable(
        {
            "critical_issues": ["visual_anchors_missing"],
            "missed_keywords": ["Pixel 9a"],
        }
    )


def main() -> int:
    test_bangla_master_is_hard_fail()
    test_english_documentary_not_flagged_bangla()
    test_visual_anchor_missing_is_hard_fail()
    test_kore_sidecar_is_voice_drift()
    test_unlabeled_tts_is_voice_drift()
    test_language_repair_without_live_tts()
    test_visual_only_does_not_count_as_agent_pass()
    test_skip_critic_opt_in_only()
    test_agent_chat_knows_quality_contract()
    test_burned_master_subs_detected_and_stripped()
    test_missed_keywords_are_hard_fail()
    test_abstract_missed_keywords_are_not_unshippable()
    print("OK agent quality train: language/voice/visual/skip-critic/chat/burnin/missed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
