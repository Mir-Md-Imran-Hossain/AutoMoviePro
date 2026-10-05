"""
Automatic Temporary Files and Intermediate Artifact Garbage Collector.

Safely purges intermediate scratch files (.mp4 fragments, .wav audio stems,
.still.png previews, .json caches) older than max_age_hours to prevent disk full issues.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Temporary scratch prefixes & extensions to scan
TEMP_DIR_PREFIXES = ("_tmp_", "tmp_", ".tmp_")
INTERMEDIATE_PATTERNS = (
    "*_silent.mp4",
    "*_temp.mp4",
    "*.still.png",
    "_tmp_*.png",
    "_tmp_*.wav",
    "intro_concat.txt",
    "*_clip_*.mp4",
)


def clean_temp_artifacts(
    root_dir: Optional[Path] = None,
    *,
    max_age_hours: float = 24.0,
    force_all_temp: bool = False,
) -> Dict[str, int]:
    """
    Scan root_dir (defaulting to project Output / work directories) and purge stale temp files.
    """
    if root_dir is None:
        root_dir = Path(__file__).resolve().parents[1]

    root_dir = Path(root_dir)
    if not root_dir.exists():
        return {"deleted_files": 0, "freed_bytes": 0}

    now = time.time()
    max_age_sec = max_age_hours * 3600.0
    deleted_count = 0
    freed_bytes = 0

    # 1. Clean temporary directories like _tmp_stills, _tmp_*
    for child in root_dir.iterdir():
        if child.is_dir() and any(child.name.startswith(p) for p in TEMP_DIR_PREFIXES):
            try:
                mtime = child.stat().st_mtime
                if force_all_temp or (now - mtime) > max_age_sec:
                    for f in child.rglob("*"):
                        if f.is_file():
                            try:
                                freed_bytes += f.stat().st_size
                                f.unlink(missing_ok=True)
                                deleted_count += 1
                            except Exception:
                                pass
                    try:
                        shutil.rmtree(str(child), ignore_errors=True)
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("Skip temp dir %s: %s", child.name, exc)

    # 2. Clean scratch files in Output / work directories
    output_dir = root_dir / "Output"
    if output_dir.exists():
        for pat in INTERMEDIATE_PATTERNS:
            for f in output_dir.rglob(pat):
                if f.is_file():
                    try:
                        mtime = f.stat().st_mtime
                        if force_all_temp or (now - mtime) > max_age_sec:
                            freed_bytes += f.stat().st_size
                            f.unlink(missing_ok=True)
                            deleted_count += 1
                    except Exception:
                        pass

    if deleted_count > 0:
        mb_freed = freed_bytes / (1024 * 1024)
        logger.info(
            "Garbage collection completed: purged %d temp files (%.2f MB freed)",
            deleted_count,
            mb_freed,
        )

    return {"deleted_files": deleted_count, "freed_bytes": freed_bytes}


def auto_garbage_collect() -> None:
    """Lightweight hook to run at the start or end of video jobs."""
    try:
        clean_temp_artifacts(max_age_hours=24.0)
    except Exception as exc:
        logger.debug("auto_garbage_collect error: %s", exc)
