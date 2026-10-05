"""Full custom-pipeline live test: topic → visual → 5-lang localize → TTS all langs.

Uses new Output layout:
  Output/Short/001_(Topic Name)/{Audio,Image,File,Video}/...
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from pipeline.custom_pipeline import run_short_pipeline, session_key_report
    from pipeline.custom_pipeline.package_layout import LANG_AUDIO_CODES
    from pipeline.custom_pipeline.tts_client import tts_call_gap_seconds
    from pipeline.custom_pipeline.quota_rotate import HARD_CAP, ROTATE_AT

    print("=== FULL CUSTOM PIPELINE LIVE TEST ===")
    print(f"ROTATE_AT={ROTATE_AT} HARD_CAP={HARD_CAP} TTS_GAP_SEC={tts_call_gap_seconds()}")

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=str, default="", help="Path to package to resume")
    args, _ = parser.parse_known_args()
    resume_pkg = Path(args.resume) if args.resume else None

    result = run_short_pipeline(
        niche="AI Tech Facts",
        audience="তরুণ প্রজন্ম",
        include_bangla_tts=True,
        resume_package=resume_pkg,
    )

    pkg = Path(result.get("package_root") or "")
    keys = result.get("session_keys") or {}
    loc = keys.get("localize_by_lang") or {}
    tts = keys.get("tts_by_lang") or {}

    print("\nPACKAGE:", pkg)
    print("FOLDER NAME:", pkg.name if pkg else None)
    print("ok:", result.get("ok"))
    print("localize keys:", json.dumps(loc, ensure_ascii=False, indent=2))
    print("tts keys:", json.dumps(tts, ensure_ascii=False, indent=2))

    checks = []
    checks.append(("package_exists", pkg.is_dir()))
    checks.append(("folder_has_parens", pkg.name.startswith(("001_(", "002_(")) or "_(" in pkg.name))
    checks.append(("no_letter_underscores", "_ত_ম_র_" not in pkg.name and "_ক_ম_" not in pkg.name))
    checks.append(("has_Audio", (pkg / "Audio").is_dir()))
    checks.append(("has_File", (pkg / "File").is_dir()))
    checks.append(("has_Image", (pkg / "Image").is_dir()))
    checks.append(("has_Video", (pkg / "Video").is_dir()))
    checks.append(("has_Video_Clips", (pkg / "Video" / "Video Clips").is_dir()))
    checks.append(("has_Final_Video", (pkg / "Video" / "Final Video").is_dir()))

    for code in LANG_AUDIO_CODES:
        checks.append((f"Audio_{code}", (pkg / "Audio" / code).is_dir()))

    # Unique keys per language
    loc_vals = [v.get("key") for v in loc.values() if isinstance(v, dict)]
    checks.append(("unique_localize_keys", len(loc_vals) == len(set(loc_vals)) and len(loc_vals) >= 5))
    tts_vals = [v.get("key") for v in tts.values() if isinstance(v, dict)]
    checks.append(("unique_tts_keys", len(tts_vals) == len(set(tts_vals)) and len(tts_vals) >= 5))

    file_dir = pkg / "File"
    if file_dir.is_dir():
        names = [p.name for p in file_dir.glob("*.json")]
        print("\nFILE JSON:")
        for n in sorted(names):
            print(" -", n)
        checks.append(("has_Script_titled", any(n.startswith("Script_") and "_(" in n for n in names)))
        checks.append(("has_Visual_titled", any(n.startswith("Visual_") and "_(" in n for n in names)))
        for code in ("EN", "HI", "TL", "ML", "UR"):
            checks.append(
                (
                    f"has_Voice_{code}",
                    any(n.startswith("Voice_") and f"_{code}_" in n for n in names),
                )
            )

    # Audio outputs
    for lang, code in (
        ("Bangla", "BN"),
        ("English", "EN"),
        ("Hindi", "HI"),
        ("Tamil", "TL"),
        ("Malayalam", "ML"),
        ("Urdu", "UR"),
    ):
        audio = pkg / "Audio" / code
        full = list(audio.glob("narration_full_*.m4a")) if audio.is_dir() else []
        shots = list(audio.glob("S*_*.m4a")) if audio.is_dir() else []
        checks.append((f"tts_{code}_shots", len(shots) >= 1))
        checks.append((f"tts_{code}_full", len(full) >= 1))

    # Video Clips check
    clips_dir = pkg / "Video" / "Video Clips"
    clips = list(clips_dir.glob("*.mp4")) if clips_dir.is_dir() else []
    print(f"\nVIDEO CLIPS GENERATED: {len(clips)}")
    for c in sorted(clips):
        print(f" - {c.name} ({c.stat().st_size} bytes)")
    checks.append(("has_video_clips_generated", len(clips) >= 1))

    # Visual Plan check (Google Pro active -> 100% VIDEO)
    visual_files = list(file_dir.glob("Visual_*.json")) if file_dir.is_dir() else []
    if visual_files:
        try:
            v_data = json.loads(visual_files[0].read_text(encoding="utf-8"))
            v_scenes = v_data.get("render_scenes") or []
            v_types = [s.get("render_type") for s in v_scenes]
            print(f"VISUAL PLAN RENDER TYPES: {v_types}")
            checks.append(("all_shots_are_video", all(t == "VIDEO" for t in v_types)))
        except Exception as e:
            print("Visual plan read error:", e)

    # Final Video outputs check (6 languages: BN, EN, HI, TL, ML, UR)
    final_dir = pkg / "Video" / "Final Video"
    print("\nFINAL LOCALIZED VIDEOS:")
    for code in ("BN", "EN", "HI", "TL", "ML", "UR"):
        f_mp4 = final_dir / code / f"final_{code}.mp4"
        exists = f_mp4.is_file() and f_mp4.stat().st_size > 10000
        size_str = f"{f_mp4.stat().st_size} bytes" if exists else "NOT FOUND"
        print(f" - {code}: {size_str}")
        checks.append((f"final_video_{code}", exists))

    print("\nVERIFICATION:")
    ok_all = True
    for name, passed in checks:
        if not passed:
            ok_all = False
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")

    print("\nSESSION:", json.dumps(session_key_report(), ensure_ascii=False, indent=2))
    summary = {
        "ok": bool(result.get("ok") and ok_all),
        "package_root": str(pkg),
        "folder_name": pkg.name if pkg else None,
        "localize_langs": list(loc.keys()),
        "tts_langs": list(tts.keys()),
        "tts_gap_sec": tts_call_gap_seconds(),
        "rotate_at": ROTATE_AT,
        "hard_cap": HARD_CAP,
    }
    print("\nSUMMARY:", json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
