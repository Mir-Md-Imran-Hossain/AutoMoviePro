"""Point-6 deep tests: topic/visual/localize skip-if-exists resume."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from pipeline.custom_pipeline.localization import localize_to_languages
from pipeline.custom_pipeline.stage_resume import (
    existing_localize_lang,
    existing_topic_package,
    existing_visual_plan,
)


def _pkg() -> Path:
    root = Path(tempfile.mkdtemp())
    pkg = root / "001_(Resume Stage Test)"
    for d in ("File", "Audio", "Image", "Video"):
        (pkg / d).mkdir(parents=True, exist_ok=True)
    return pkg


def _topic_payload():
    return {
        "seo_metadata": {"selected_topic": "t", "video_type": "Shorts"},
        "script_scenes": [
            {"shot_number": 1, "voiceover_script": "Hello world narration here."}
        ],
    }


def _visual_payload():
    return {
        "production_metadata": {"aspect_ratio": "9:16", "image_shots": 1, "video_shots": 0},
        "render_scenes": [{"shot_number": 1, "render_type": "IMAGE"}],
    }


def test_topic_resume_valid():
    pkg = _pkg()
    p = pkg / "File" / "topic_script.json"
    p.write_text(json.dumps(_topic_payload()), encoding="utf-8")
    got = existing_topic_package(pkg)
    assert got and got["resumed"] is True
    assert got["payload"]["script_scenes"]


def test_topic_rejects_empty_scenes():
    pkg = _pkg()
    (pkg / "File" / "topic_script.json").write_text(
        json.dumps({"seo_metadata": {}, "script_scenes": []}), encoding="utf-8"
    )
    assert existing_topic_package(pkg) is None


def test_topic_rejects_corrupt_json():
    pkg = _pkg()
    (pkg / "File" / "topic_script.json").write_text("{nope", encoding="utf-8")
    assert existing_topic_package(pkg) is None


def test_visual_resume_and_reject():
    pkg = _pkg()
    (pkg / "File" / "visual_render_plan.json").write_text(
        json.dumps(_visual_payload()), encoding="utf-8"
    )
    got = existing_visual_plan(pkg)
    assert got and got["resumed"] is True
    (pkg / "File" / "visual_render_plan.json").write_text(
        json.dumps({"render_scenes": []}), encoding="utf-8"
    )
    assert existing_visual_plan(pkg) is None


def test_localize_resume_valid():
    pkg = _pkg()
    voice = {
        "voice_scenes": [{"shot_number": 1, "voiceover_script": "Namaste friends today."}]
    }
    (pkg / "File" / "localized_voice_HI.json").write_text(
        json.dumps(voice), encoding="utf-8"
    )
    got = existing_localize_lang(pkg, "HI")
    assert got and got["resumed"] is True


def test_localize_to_languages_skips_api_when_present():
    pkg = _pkg()
    source = _topic_payload()
    (pkg / "File" / "topic_script.json").write_text(json.dumps(source), encoding="utf-8")
    voice = {
        "voice_scenes": [
            {"shot_number": 1, "voiceover_script": "Hello world narration here."}
        ]
    }
    (pkg / "File" / "localized_voice_EN.json").write_text(
        json.dumps(voice), encoding="utf-8"
    )
    with mock.patch(
        "pipeline.custom_pipeline.localization.localize_script"
    ) as loc:
        loc.side_effect = AssertionError("API must not run for resumed lang")
        result = localize_to_languages(
            source,
            languages=["English"],
            package_root=pkg,
            save=False,
            force=False,
        )
    assert result["ok"] is True
    assert result["resumed_count"] == 1
    assert result["api_count"] == 0
    assert result["results"]["English"]["resumed"] is True


def test_localize_force_calls_api():
    pkg = _pkg()
    source = _topic_payload()
    voice = {
        "voice_scenes": [
            {"shot_number": 1, "voiceover_script": "Hello world narration here."}
        ]
    }
    (pkg / "File" / "localized_voice_EN.json").write_text(
        json.dumps(voice), encoding="utf-8"
    )

    def fake_loc(*a, **k):
        return {"ok": True, "payload": voice, "save": {}}

    with mock.patch(
        "pipeline.custom_pipeline.localization.localize_script", side_effect=fake_loc
    ) as loc:
        result = localize_to_languages(
            source, languages=["English"], package_root=pkg, save=False, force=True
        )
    assert loc.call_count == 1
    assert result["api_count"] == 1
    assert result["resumed_count"] == 0


def test_live_package_topic_visual_resume():
    root = Path(__file__).resolve().parents[2] / "Output" / "Short"
    if not root.is_dir():
        return
    pkgs = [p for p in root.iterdir() if p.is_dir()]
    if not pkgs:
        return
    pkg = pkgs[0]
    topic = existing_topic_package(pkg)
    visual = existing_visual_plan(pkg)
    print(
        f"LIVE pkg={pkg.name} topic_resume={bool(topic)} visual_resume={bool(visual)}"
    )
    # If files exist they must validate; if missing None is fine
    if (pkg / "File" / "topic_script.json").is_file() or list(
        (pkg / "File").glob("Script_*.json")
    ):
        assert topic is not None


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
    print(f"all {len(tests)} point-6 tests passed")
