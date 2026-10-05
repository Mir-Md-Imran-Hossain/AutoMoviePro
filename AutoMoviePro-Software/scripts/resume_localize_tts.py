"""Resume: localize any missing langs on existing package, then full TTS (BN+5)."""

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

    from pipeline.custom_pipeline.localization import localize_to_languages
    from pipeline.custom_pipeline.package_archive import archive_complete_json_package
    from pipeline.custom_pipeline.package_layout import LANG_AUDIO_CODES
    from pipeline.custom_pipeline.session_keys import session_key_report, start_session
    from pipeline.custom_pipeline.topic_research import pick_primary_title
    from pipeline.custom_pipeline.tts_client import tts_call_gap_seconds
    from pipeline.custom_pipeline.tts_synthesize import synthesize_package_tts
    from pipeline.custom_pipeline.quota_rotate import HARD_CAP, ROTATE_AT

    short = ROOT / "Output" / "Short"
    pkgs = [p for p in short.iterdir() if p.is_dir()]
    if not pkgs:
        print("ERROR: no Short package")
        return 1
    pkg = pkgs[0]
    src = pkg / "File" / "topic_script.json"
    payload = json.loads(src.read_text(encoding="utf-8"))
    title = pick_primary_title(payload)

    print("=== RESUME LOCALIZE + TTS ===")
    print("package:", pkg.name)
    print(f"ROTATE_AT={ROTATE_AT} HARD_CAP={HARD_CAP} TTS_GAP={tts_call_gap_seconds()}")

    start_session()
    needed = ["English", "Hindi", "Tamil", "Malayalam", "Urdu"]
    missing = []
    for lang, code in (
        ("English", "EN"),
        ("Hindi", "HI"),
        ("Tamil", "TL"),
        ("Malayalam", "ML"),
        ("Urdu", "UR"),
    ):
        if not (pkg / "File" / f"localized_voice_{code}.json").is_file():
            missing.append(lang)
    print("missing localize:", missing or "(none)")

    loc = {"ok": True, "results": {}, "errors": {}}
    if missing:
        loc = localize_to_languages(
            src,
            languages=missing,
            package_root=pkg,
            video_type="short",
            save=True,
        )
        print("localize ok:", loc.get("ok"), "errors:", loc.get("errors"))

    # Full TTS for all languages including Bangla
    tts = synthesize_package_tts(
        pkg,
        languages=needed,
        include_bangla=True,
    )
    print("tts ok:", tts.get("ok"), "errors:", tts.get("errors"))

    arch = archive_complete_json_package(
        package_root=pkg, video_type="short", title=title
    )

    keys = session_key_report()
    loc_keys = keys.get("localize_by_lang") or {}
    tts_keys = keys.get("tts_by_lang") or {}
    loc_vals = [v.get("key") for v in loc_keys.values() if isinstance(v, dict)]
    tts_vals = [v.get("key") for v in tts_keys.values() if isinstance(v, dict)]

    checks = []
    checks.append(("folder_parens", "_(" in pkg.name and pkg.name.endswith(")")))
    checks.append(("no_letter_underscores", "_ত_ম_র_" not in pkg.name))
    for code in LANG_AUDIO_CODES:
        checks.append((f"dir_Audio_{code}", (pkg / "Audio" / code).is_dir()))
    for code in ("EN", "HI", "TL", "ML", "UR"):
        checks.append(
            (
                f"voice_{code}",
                (pkg / "File" / f"localized_voice_{code}.json").is_file()
                or any((pkg / "File").glob(f"Voice_*_{code}_*.json")),
            )
        )
    for code in LANG_AUDIO_CODES:
        shots = list((pkg / "Audio" / code).glob("S*.m4a"))
        full = list((pkg / "Audio" / code).glob("narration_full_*.m4a"))
        checks.append((f"tts_{code}_shots", len(shots) >= 1))
        checks.append((f"tts_{code}_full", len(full) >= 1))
    checks.append(("unique_localize", len(loc_vals) == len(set(loc_vals))))
    checks.append(("unique_tts", len(tts_vals) == len(set(tts_vals))))

    print("\nlocalize_by_lang:", json.dumps(loc_keys, ensure_ascii=False, indent=2))
    print("tts_by_lang:", json.dumps(tts_keys, ensure_ascii=False, indent=2))
    print("\nVERIFICATION:")
    ok = True
    for name, passed in checks:
        if not passed:
            ok = False
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")

    summary = {
        "ok": ok and bool(tts.get("ok")),
        "package": str(pkg),
        "folder": pkg.name,
        "file_dir": arch.get("file_dir"),
        "tts_gap_sec": tts_call_gap_seconds(),
        "rotate_at": ROTATE_AT,
        "hard_cap": HARD_CAP,
    }
    print("\nSUMMARY:", json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
