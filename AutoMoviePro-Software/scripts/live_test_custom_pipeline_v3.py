"""Live test v3: all 5 localize langs + title-based JSON names + dedupe."""

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
    from pipeline.custom_pipeline.duplicate_guard import find_duplicate, load_history
    from pipeline.custom_pipeline.package_archive import titled_json_name

    # Sanity: naming scheme
    sample = titled_json_name("Script", "2", "মাত্র ৩ সেকেন্ডে AI তোমার ভয়েস চুরি করে! 😱")
    assert sample.startswith("Script_002_(") and sample.endswith(").json"), sample
    print("Naming OK:", sample)

    print("\n=== LIVE TEST: short pipeline — ALL 5 languages ===")
    result = run_short_pipeline(
        niche="AI Tech Facts",
        audience="তরুণ প্রজন্ম",
        # languages omitted → English, Hindi, Tamil, Malayalam, Urdu
    )

    arch = result.get("complete_json_archive") or {}
    arch_dir = Path(arch.get("archive_dir") or "")
    voices = (result.get("outputs") or {}).get("localized_voices") or {}
    dedupe = result.get("dedupe") or {}

    print(
        json.dumps(
            {
                "ok": result.get("ok"),
                "video_type": result.get("video_type"),
                "package_root": result.get("package_root"),
                "localized_langs": list(voices.keys()),
                "dedupe": dedupe,
                "archive_dir": arch.get("archive_dir"),
                "archive_files": [f.get("filename") for f in (arch.get("files") or [])],
                "session_keys": result.get("session_keys"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    checks = []
    expected = {"English", "Hindi", "Tamil", "Malayalam", "Urdu"}
    checks.append(("all_5_languages", set(voices.keys()) >= expected))
    checks.append(("archive_exists", arch_dir.is_dir()))

    if arch_dir.is_dir():
        names = [p.name for p in arch_dir.iterdir() if p.suffix == ".json"]
        print("\nARCHIVE FILES:")
        for n in sorted(names):
            print(" -", n)
        checks.append(("has_Script_NNN", any(n.startswith("Script_") for n in names)))
        checks.append(("has_Visual_NNN", any(n.startswith("Visual_") for n in names)))
        checks.append(("has_Voice_en", any(n.startswith("Voice_") and "_en_" in n for n in names)))
        checks.append(("has_Voice_hi", any(n.startswith("Voice_") and "_hi_" in n for n in names)))
        checks.append(("has_Voice_ta", any(n.startswith("Voice_") and "_ta_" in n for n in names)))
        checks.append(("has_Voice_ml", any(n.startswith("Voice_") and "_ml_" in n for n in names)))
        checks.append(("has_Voice_ur", any(n.startswith("Voice_") and "_ur_" in n for n in names)))
        checks.append(("title_in_parens", any("_(" in n and n.endswith(").json") for n in names)))

    # Dedupe system present
    checks.append(("dedupe_attempts_recorded", bool(dedupe.get("attempts"))))

    # Voice-only localization still holds
    pkg = Path(result.get("package_root") or "")
    en = pkg / "English" / "Script" / "localized_voice.json"
    if en.is_file():
        e = json.loads(en.read_text(encoding="utf-8"))
        shot = (e.get("voice_scenes") or [{}])[0]
        checks.append(("en_no_visual_prompt", "visual_prompt" not in shot))
        checks.append(("en_visuals_shared", e.get("visuals_shared") is True))

    print("\nVERIFICATION:")
    ok_all = True
    for name, passed in checks:
        if not passed:
            ok_all = False
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")

    print("\nSESSION:", json.dumps(session_key_report(), ensure_ascii=False, indent=2))
    return 0 if result.get("ok") and ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
