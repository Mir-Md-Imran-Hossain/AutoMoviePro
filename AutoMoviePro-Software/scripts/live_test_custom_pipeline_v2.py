"""Live test: short pipeline + quota rotate + complete JSON archive verification."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> int:
    from pipeline.custom_pipeline import run_short_pipeline, session_key_report

    print("=== LIVE TEST: short pipeline (EN+HI) ===")
    result = run_short_pipeline(
        niche="AI Tech Facts",
        audience="তরুণ প্রজন্ম",
        languages=["English", "Hindi"],
    )

    summary = {
        "ok": result.get("ok"),
        "video_type": result.get("video_type"),
        "session_id": result.get("session_id"),
        "session_keys": result.get("session_keys"),
        "package_root": result.get("package_root"),
        "outputs": result.get("outputs"),
        "complete_json_archive": result.get("complete_json_archive"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Verify fixes
    checks = []
    pkg = Path(result.get("package_root") or "")
    topic = pkg / "Shared" / "topic_script.json"
    visual = pkg / "Shared" / "visual_render_plan.json"
    en = pkg / "English" / "Script" / "localized_voice.json"
    if not en.exists():
        en = pkg / "English" / "Script" / "localized_script.json"
    hi = pkg / "Hindi" / "Script" / "localized_voice.json"
    if not hi.exists():
        hi = pkg / "Hindi" / "Script" / "localized_script.json"

    checks.append(("topic_exists", topic.is_file()))
    checks.append(("visual_exists", visual.is_file()))
    checks.append(("en_voice_exists", en.is_file()))
    checks.append(("hi_voice_exists", hi.is_file()))
    checks.append(("short_only", pkg.parent.name == "Short"))

    if topic.is_file():
        t = json.loads(topic.read_text(encoding="utf-8"))
        scenes = t.get("script_scenes") or []
        checks.append(("master_has_visual_prompt", bool(scenes and scenes[0].get("visual_prompt"))))
        checks.append(("master_has_character", bool(scenes and scenes[0].get("character_details"))))
        vos = " ".join(str(s.get("voiceover_script") or "") for s in scenes)
        checks.append(
            (
                "hook_salam_cta_or_quiz",
                any(
                    x in vos
                    for x in (
                        "সালাম",
                        "আসসালাম",
                        "আল্লাহ হাফেজ",
                        "সাবস্ক্রাইব",
                        "কমেন্ট",
                        "লাইক",
                        "গাইজ",
                    )
                ),
            )
        )

    if en.is_file():
        e = json.loads(en.read_text(encoding="utf-8"))
        checks.append(("en_visuals_shared_flag", e.get("visuals_shared") is True))
        vs = e.get("voice_scenes") or e.get("script_scenes") or []
        shot = vs[0] if vs else {}
        checks.append(("en_no_visual_prompt", "visual_prompt" not in shot))
        checks.append(("en_no_camera", "camera_angle" not in shot))
        checks.append(("en_has_voice", bool(shot.get("voiceover_script"))))
        checks.append(("en_has_subtitle", bool(shot.get("subtitle_text") or shot.get("voiceover_script"))))

    if visual.is_file():
        v = json.loads(visual.read_text(encoding="utf-8"))
        rs = v.get("render_scenes") or []
        types = {s.get("render_type") for s in rs}
        checks.append(("visual_has_image_or_video", bool(types & {"IMAGE", "VIDEO"})))

    arch = result.get("complete_json_archive") or {}
    arch_dir = Path(arch.get("archive_dir") or "")
    checks.append(("archive_dir_exists", arch_dir.is_dir()))
    checks.append(("archive_has_manifest", (arch_dir / "MANIFEST.json").is_file() if arch_dir.is_dir() else False))
    if arch_dir.is_dir():
        jsons = list(arch_dir.glob("*.json"))
        checks.append(("archive_json_count_ge_3", len(jsons) >= 3))
        print("\nARCHIVE FILES:")
        for p in sorted(arch_dir.iterdir()):
            print(" -", p.name)

    print("\nVERIFICATION:")
    ok_all = True
    for name, passed in checks:
        mark = "PASS" if passed else "FAIL"
        if not passed:
            ok_all = False
        print(f"  [{mark}] {name}")

    print("\nSESSION KEYS:", json.dumps(session_key_report(), ensure_ascii=False, indent=2))
    return 0 if result.get("ok") and ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
