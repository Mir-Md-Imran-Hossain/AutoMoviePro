"""Point-3 deep tests: TTS resume (no live paid TTS)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from pipeline.custom_pipeline.tts_synthesize import (
    _script_fingerprint,
    synthesize_language_tts,
    synthesize_package_tts,
)


def _pkg_with_voice(n_shots: int = 3) -> Path:
    root = Path(tempfile.mkdtemp())
    pkg = root / "001_(TTS Resume Test)"
    for d in ("File", "Audio", "Image", "Video"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
    scenes = []
    for i in range(1, n_shots + 1):
        scenes.append(
            {
                "shot_number": i,
                "voiceover_script": f"Hello shot {i} with enough words here.",
                "emotion_tag": "calm",
                "shot_duration_seconds": 3,
            }
        )
    voice = {
        "seo_metadata": {"video_type": "Shorts"},
        "voice_scenes": scenes,
    }
    (pkg / "File" / "localized_voice_EN.json").write_text(
        json.dumps(voice, ensure_ascii=False), encoding="utf-8"
    )
    return pkg


def _write_fake(path: Path, size: int = 2500) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)
    return path


def test_fingerprint_changes_with_script():
    a = [{"shot_number": 1, "voiceover_script": "one"}]
    b = [{"shot_number": 1, "voiceover_script": "two"}]
    assert _script_fingerprint(a) != _script_fingerprint(b)
    assert _script_fingerprint(a) == _script_fingerprint(a)


def test_full_resume_skips_api():
    pkg = _pkg_with_voice(2)
    audio = pkg / "Audio" / "EN"
    _write_fake(audio / "narration_full_EN.m4a", 3000)
    _write_fake(audio / "S01_EN.m4a", 1500)
    _write_fake(audio / "S02_EN.m4a", 1500)

    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration"
    ) as cont:
        cont.side_effect = AssertionError("API must not be called on resume")
        result = synthesize_language_tts(pkg, "English")
    assert result["ok"] is True
    assert result["resumed"] is True
    assert result["resume_reason"] == "full_and_shots"
    assert result["success_count"] == 2
    assert cont.call_count == 0


def test_force_bypasses_resume():
    pkg = _pkg_with_voice(1)
    audio = pkg / "Audio" / "EN"
    _write_fake(audio / "narration_full_EN.m4a", 3000)
    _write_fake(audio / "S01_EN.m4a", 1500)

    def fake_cont(texts, out, **kwargs):
        p = Path(out)
        _write_fake(p, 4000)
        return p

    def fake_split(full, texts, outs):
        paths = []
        for o in outs:
            paths.append(_write_fake(Path(o), 2000))
        return paths

    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration",
        side_effect=fake_cont,
    ) as cont, mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.split_audio_by_word_ratios",
        side_effect=fake_split,
    ), mock.patch(
        "pipeline.custom_pipeline.audio_align.align_and_split_shots",
        side_effect=fake_split,
    ):
        result = synthesize_language_tts(pkg, "English", force=True)
    assert result.get("resumed") is False
    assert cont.call_count == 1
    assert result["ok"] is True


def test_resplit_from_full_without_api():
    pkg = _pkg_with_voice(2)
    audio = pkg / "Audio" / "EN"
    _write_fake(audio / "narration_full_EN.m4a", 5000)
    # shots missing

    def fake_split(full, texts, outs):
        return [_write_fake(Path(o), 2000) for o in outs]

    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration"
    ) as cont, mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.split_audio_by_word_ratios",
        side_effect=fake_split,
    ), mock.patch(
        "pipeline.custom_pipeline.audio_align.align_and_split_shots",
        side_effect=Exception("no whisper"),
    ):
        result = synthesize_language_tts(pkg, "English")
    assert result["resumed"] is True
    assert result["resume_reason"] == "resplit_from_full"
    assert cont.call_count == 0
    assert (audio / "S01_EN.m4a").is_file()


def test_concat_from_shots_without_api():
    pkg = _pkg_with_voice(2)
    audio = pkg / "Audio" / "EN"
    _write_fake(audio / "S01_EN.m4a", 1500)
    _write_fake(audio / "S02_EN.m4a", 1500)

    def fake_concat(parts, out):
        return _write_fake(Path(out), 4000)

    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration"
    ) as cont, mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.concat_audio_files",
        side_effect=fake_concat,
    ):
        result = synthesize_language_tts(pkg, "English")
    assert result["resumed"] is True
    assert result["resume_reason"] == "concat_from_shots"
    assert cont.call_count == 0
    assert (audio / "narration_full_EN.m4a").stat().st_size >= 2000


def test_fingerprint_mismatch_forces_regen():
    pkg = _pkg_with_voice(1)
    audio = pkg / "Audio" / "EN"
    _write_fake(audio / "narration_full_EN.m4a", 3000)
    _write_fake(audio / "S01_EN.m4a", 1500)
    (audio / "tts_resume_EN.json").write_text(
        json.dumps({"script_fingerprint": "deadbeefdeadbeef"}), encoding="utf-8"
    )

    def fake_cont(texts, out, **kwargs):
        return _write_fake(Path(out), 4000)

    def fake_split(full, texts, outs):
        return [_write_fake(Path(o), 2000) for o in outs]

    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration",
        side_effect=fake_cont,
    ) as cont, mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.split_audio_by_word_ratios",
        side_effect=fake_split,
    ), mock.patch(
        "pipeline.custom_pipeline.audio_align.align_and_split_shots",
        side_effect=fake_split,
    ):
        result = synthesize_language_tts(pkg, "English")
    assert result.get("resumed") is False
    assert cont.call_count == 1


def test_per_shot_skips_existing():
    pkg = _pkg_with_voice(2)
    audio = pkg / "Audio" / "EN"
    _write_fake(audio / "S01_EN.m4a", 1500)
    # S02 missing → only one API call

    calls = []

    def fake_shot(text, out, **kwargs):
        calls.append(str(out))
        return _write_fake(Path(out), 2000)

    def fake_concat(parts, out):
        return _write_fake(Path(out), 4000)

    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration",
        side_effect=RuntimeError("force per_shot"),
    ), mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_shot_audio",
        side_effect=fake_shot,
    ), mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.concat_audio_files",
        side_effect=fake_concat,
    ):
        result = synthesize_language_tts(pkg, "English", mode="per_shot")
    assert result["ok"] is True
    assert len(calls) == 1
    assert "S02_EN.m4a" in calls[0]
    resumed = [s for s in result["shots"] if s.get("resumed")]
    assert len(resumed) == 1


def test_package_partial_flag():
    pkg = _pkg_with_voice(1)
    # Bangla missing voice → error; English resume ok
    audio = pkg / "Audio" / "EN"
    _write_fake(audio / "narration_full_EN.m4a", 3000)
    _write_fake(audio / "S01_EN.m4a", 1500)

    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration"
    ):
        result = synthesize_package_tts(
            pkg, languages=["English", "Hindi"], include_bangla=False
        )
    assert result["ok"] is False
    assert result["partial"] is True
    assert result["results"]["English"]["resumed"] is True


def test_live_bn_resume_if_present():
    """Live angle: existing Short BN audio should resume without calling Gemini."""
    root = Path(__file__).resolve().parents[2] / "Output" / "Short"
    if not root.is_dir():
        return
    pkgs = [p for p in root.iterdir() if p.is_dir()]
    if not pkgs:
        return
    pkg = pkgs[0]
    bn = pkg / "Audio" / "BN"
    shots = list(bn.glob("S*_BN.m4a")) if bn.is_dir() else []
    full = bn / "narration_full_BN.m4a"
    if not (full.is_file() and shots):
        print("SKIP live BN — incomplete audio")
        return
    # Need topic/voice json
    if not (pkg / "File").is_dir():
        return
    with mock.patch(
        "pipeline.custom_pipeline.tts_synthesize.synthesize_continuous_narration"
    ) as cont:
        try:
            result = synthesize_language_tts(pkg, "Bangla")
        except FileNotFoundError:
            print("SKIP live BN — no voice json")
            return
    if result.get("resumed"):
        assert cont.call_count == 0
        assert result["ok"] is True
        print(f"LIVE resume ok shots={result.get('success_count')}")
    else:
        # Incomplete vs script — still must not crash
        print(f"LIVE not fully resumed reason ok={result.get('ok')}")


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
    print(f"all {len(tests)} point-3 tests passed")
