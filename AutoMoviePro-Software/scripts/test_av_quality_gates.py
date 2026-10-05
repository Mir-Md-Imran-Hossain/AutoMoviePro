#!/usr/bin/env python3
"""
Synthetic + real-media unit tests for deterministic AV quality gates.

Proves the agent can DETECT (and for hold, repair via pad) each fault class:
  1) dialogue_cutoff
  2) localize_freeze_risk (ratio)
  3) missing_tail_hold
  4) subtitle_timing
  5) localization_text (wrong script)
  6) duration_window / av_length_match
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.av_quality_gates import (  # noqa: E402
    apply_gates_to_critique,
    detect_av_length_match,
    detect_dialogue_cutoff,
    detect_duration_window,
    detect_localization_text,
    detect_localize_ratio,
    detect_subtitle_coverage,
    detect_tail_hold,
)
from pipeline.compose import ffmpeg_bin  # noqa: E402
from pipeline.dialogue_sync import DIALOGUE_TAIL_PAD_SEC, pad_av_tail  # noqa: E402
from pipeline.localization import write_srt  # noqa: E402


def _run(cmd: list) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{(r.stderr or r.stdout)[-500:]}")


def make_tone_wav(path: Path, *, seconds: float, freq: float = 440.0, amp: float = 0.25) -> Path:
    """Generate a continuous sine tone (speech-energy proxy)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:sample_rate=16000:duration={seconds:.3f}",
            "-af",
            f"volume={amp}",
            str(path),
        ]
    )
    return path


def make_silence_wav(path: Path, *, seconds: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=16000:cl=mono",
            "-t",
            f"{seconds:.3f}",
            str(path),
        ]
    )
    return path


def mux_color_av(video: Path, audio: Path, dest: Path, *, seconds: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=320x240:d={seconds:.3f}",
            "-i",
            str(audio),
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(dest),
        ]
    )
    return dest


def assert_fail(name: str, gate: dict, code: str) -> None:
    if gate.get("passed", True):
        raise AssertionError(f"{name}: expected FAIL, got PASS: {gate}")
    crits = gate.get("critical_issues") or []
    if code not in crits and not any(code in str(c) for c in crits):
        # also allow issue text
        issues = " ".join(gate.get("issues") or [])
        if code not in issues and code not in "".join(crits):
            raise AssertionError(f"{name}: expected critical/issue '{code}', got {gate}")
    print(f"  OK detect FAIL [{name}] → {crits or gate.get('issues')}")


def assert_pass(name: str, gate: dict) -> None:
    if not gate.get("passed", False):
        raise AssertionError(f"{name}: expected PASS, got FAIL: {gate}")
    print(f"  OK detect PASS [{name}]")


def test_dialogue_cutoff(tmpdir: Path) -> None:
    print("\n[1] dialogue_cutoff")
    # Speech energy to the absolute end → FAIL
    tone = make_tone_wav(tmpdir / "speech_end.wav", seconds=3.0)
    bad = mux_color_av(tmpdir / "v.mp4", tone, tmpdir / "cutoff_bad.mp4", seconds=3.0)
    g = detect_dialogue_cutoff(bad, narration_text="This narration is deliberately long enough to exceed three seconds of audio.", lang="en")
    assert_fail("speech_at_end", g, "dialogue_cutoff")

    # Tone then silence pad → PASS cutoff
    tone2 = make_tone_wav(tmpdir / "speech.wav", seconds=2.0)
    sil = make_silence_wav(tmpdir / "sil.wav", seconds=1.2)
    concat = tmpdir / "ok_audio.wav"
    _run(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(tone2),
            "-i",
            str(sil),
            "-filter_complex",
            "[0:a][1:a]concat=n=2:v=0:a=1",
            str(concat),
        ]
    )
    good = mux_color_av(tmpdir / "v2.mp4", concat, tmpdir / "cutoff_good.mp4", seconds=3.2)
    g2 = detect_dialogue_cutoff(good, narration_text="Short line.", lang="en")
    assert_pass("silence_after_speech", g2)

    # Real Chernobyl Agnes sample if present
    real = ROOT / "output" / "Chernobyl_30_TrainCompare" / "clip_01" / "agnes_00_hook.mp4"
    if real.exists():
        g3 = detect_dialogue_cutoff(real, narration_text="", lang="en")
        print(f"  real clip_01 agnes cutoff passed={g3.get('passed')} end_rms={g3.get('end_rms')}")


def test_localize_ratio(tmpdir: Path) -> None:
    print("\n[2] localize_freeze_risk (ratio)")
    short_v_audio = make_tone_wav(tmpdir / "sv.wav", seconds=4.0)
    short_v = mux_color_av(tmpdir / "sv.mp4", short_v_audio, tmpdir / "short_v.mp4", seconds=4.0)
    long_a = make_tone_wav(tmpdir / "long_a.wav", seconds=10.0)
    bad = detect_localize_ratio(short_v, long_a, max_stretch=1.18)
    assert_fail("long_tts_vs_picture", bad, "localize_freeze_risk")
    ok_a = make_tone_wav(tmpdir / "ok_a.wav", seconds=4.2)
    good = detect_localize_ratio(short_v, ok_a, max_stretch=1.18)
    assert_pass("matched_lengths", good)


def test_tail_hold_and_repair(tmpdir: Path) -> None:
    print("\n[3] missing_tail_hold + pad repair")
    tone = make_tone_wav(tmpdir / "t.wav", seconds=2.5)
    no_hold = mux_color_av(tmpdir / "nh.mp4", tone, tmpdir / "no_hold.mp4", seconds=2.5)
    g = detect_tail_hold(no_hold, min_hold_sec=1.0)
    assert_fail("no_hold", g, "missing_tail_hold")
    repaired = tmpdir / "held.mp4"
    pad_av_tail(no_hold, repaired, DIALOGUE_TAIL_PAD_SEC)
    g2 = detect_tail_hold(repaired, min_hold_sec=1.0)
    assert_pass("after_pad_repair", g2)


def test_subtitle_coverage(tmpdir: Path) -> None:
    print("\n[4] subtitle_timing")
    audio = make_tone_wav(tmpdir / "sub_a.wav", seconds=5.0)
    srt_ok = tmpdir / "ok.srt"
    write_srt("One two three four five six seven eight nine ten eleven twelve thirteen.", audio, srt_ok)
    assert_pass("write_srt_covers", detect_subtitle_coverage(srt_ok, audio))
    srt_bad = tmpdir / "bad.srt"
    srt_bad.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nHi\n\n",
        encoding="utf-8",
    )
    assert_fail("ends_early", detect_subtitle_coverage(srt_bad, audio), "subtitle_timing")


def test_localization_text() -> None:
    print("\n[5] localization_text")
    assert_fail(
        "bn_latin",
        detect_localization_text(lang_code="bn", narration="This is English not Bangla text here"),
        "localization_text",
    )
    assert_pass(
        "bn_script",
        detect_localization_text(
            lang_code="bn",
            narration="চেরনোবিলের এই বিস্ফোরণের পর পুরো শহর বিপদের মুখে পড়ে।",
        ),
    )
    assert_fail(
        "identical_en",
        detect_localization_text(
            lang_code="hi",
            narration="Same English line for both.",
            english_narration="Same English line for both.",
        ),
        "localization_text",
    )


def test_duration_and_av_match(tmpdir: Path) -> None:
    print("\n[6] duration_window + av_length_match")
    tone = make_tone_wav(tmpdir / "d.wav", seconds=8.5)
    ok = mux_color_av(tmpdir / "d.mp4", tone, tmpdir / "dur_ok.mp4", seconds=8.5)
    assert_pass("window_ok", detect_duration_window(ok))
    short = mux_color_av(tmpdir / "s.mp4", make_tone_wav(tmpdir / "s.wav", seconds=3.0), tmpdir / "dur_short.mp4", seconds=3.0)
    assert_fail("too_short", detect_duration_window(short), "duration_too_short")
    assert_pass("embedded_av", detect_av_length_match(ok))


def test_critic_merge(tmpdir: Path) -> None:
    print("\n[7] apply_gates_to_critique hard-fail merge")
    tone = make_tone_wav(tmpdir / "c.wav", seconds=2.0)
    bad = mux_color_av(tmpdir / "c.mp4", tone, tmpdir / "c_bad.mp4", seconds=2.0)
    soft = {"passed": True, "match_score": 90, "issues": [], "critical_issues": [], "raw": {"fallback": True}}
    merged = apply_gates_to_critique(soft, [detect_dialogue_cutoff(bad, narration_text="Long narration that should exceed.", lang="en")])
    if merged.get("passed"):
        raise AssertionError(f"soft LLM pass must become hard fail: {merged}")
    print(f"  OK critic soft-pass overridden → score={merged.get('match_score')} crit={merged.get('critical_issues')}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="amp_gates_"))
    print(f"workdir: {tmp}")
    try:
        test_dialogue_cutoff(tmp)
        test_localize_ratio(tmp)
        test_tail_hold_and_repair(tmp)
        test_subtitle_coverage(tmp)
        test_localization_text()
        test_duration_and_av_match(tmp)
        test_critic_merge(tmp)
    except Exception as exc:
        print(f"\nFAILED: {exc}")
        return 1
    summary = {"ok": True, "tmpdir": str(tmp)}
    print("\nALL GATE TESTS PASSED")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
