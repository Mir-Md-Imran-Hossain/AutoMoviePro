"""Ensure package File/ has titled Script/Visual/Voice JSON (new layout).

Folder name format: 001_(Topic Name) — Bangla kept intact, no per-letter underscores.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.custom_pipeline.package_layout import (
    lang_code_for,
    open_package,
    sanitize_topic_title,
    titled_json_name,
    write_file_json,
)
from pipeline.output_layout import write_json

# Re-export for callers / tests
sanitize_title_for_filename = sanitize_topic_title


def archive_complete_json_package(
    *,
    package_root: Path | str,
    video_type: str = "short",
    title: Optional[str] = None,
    archive_root: Optional[Path] = None,  # unused — File/ is canonical
    extra_files: Optional[Dict[str, Path]] = None,
    video_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize / copy JSON into package File/ with title-based names."""
    pkg = Path(package_root)
    if not pkg.is_dir():
        raise FileNotFoundError(f"package_root not found: {pkg}")

    paths = open_package(pkg)
    title_s = (title or "").strip() or paths.title
    title_s = sanitize_topic_title(title_s)
    num = (video_number or "").strip() or paths.number
    if num.isdigit():
        num = f"{int(num):03d}"

    copied: List[Dict[str, str]] = []

    def _ensure(src: Path, out_name: str, label: str) -> None:
        if not src.is_file():
            return
        target = paths.file_dir / out_name
        if src.resolve() != target.resolve():
            shutil.copy2(src, target)
        copied.append(
            {
                "label": label,
                "filename": out_name,
                "path": str(target),
                "source": str(src),
            }
        )

    file_dir = paths.file_dir
    # Script
    script_alias = file_dir / "topic_script.json"
    script_named = titled_json_name("Script", num, title_s)
    if script_alias.is_file():
        _ensure(script_alias, script_named, "script")
    else:
        for p in sorted(file_dir.glob("Script_*.json")):
            _ensure(p, script_named, "script")
            break

    # Visual
    visual_alias = file_dir / "visual_render_plan.json"
    visual_named = titled_json_name("Visual", num, title_s)
    if visual_alias.is_file():
        _ensure(visual_alias, visual_named, "visual")
    else:
        for p in sorted(file_dir.glob("Visual_*.json")):
            _ensure(p, visual_named, "visual")
            break

    # Voices
    for p in sorted(file_dir.glob("localized_voice_*.json")):
        code = p.stem.replace("localized_voice_", "").upper()
        _ensure(p, titled_json_name("Voice", num, title_s, lang=code), f"voice_{code}")

    if extra_files:
        for label, path in extra_files.items():
            src = Path(path)
            if label.lower().startswith("voice_"):
                lang = label.split("_", 1)[-1]
                _ensure(
                    src,
                    titled_json_name("Voice", num, title_s, lang=lang_code_for(lang)),
                    label,
                )
            elif label.lower() == "script":
                _ensure(src, titled_json_name("Script", num, title_s), label)
            elif label.lower() == "visual":
                _ensure(src, titled_json_name("Visual", num, title_s), label)

    manifest = {
        "video_number": num,
        "title": title_s,
        "folder_name": paths.folder_name,
        "video_type": paths.video_type,
        "package_root": str(paths.root.resolve()),
        "file_dir": str(file_dir.resolve()),
        "naming_scheme": "001_(Topic Name)/File/Script|Visual|Voice_NNN_[LANG]_(Title).json",
        "layout": {
            "Audio": ["BN", "EN", "HI", "UR", "TL", "ML"],
            "Image": [],
            "File": "all JSON",
            "Video": {"Video Clips": [], "Final Video": ["BN", "EN", "HI", "UR", "TL", "ML"]},
        },
        "files": copied,
    }
    write_json(file_dir / "MANIFEST.json", manifest)
    return manifest
