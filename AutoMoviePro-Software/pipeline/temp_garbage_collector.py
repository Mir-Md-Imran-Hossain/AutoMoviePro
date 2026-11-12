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
    "subs_concat.txt",
    "concat_*.txt",
    "*_clip_*.mp4",
    "raw_*.tmp",
    "*_intermediate.mp4",
    "*.tmp",
)


def purge_customer_work_intermediates(
    work_dir: Path | str,
    *,
    keep_finals: bool = True,
    max_age_hours: Optional[float] = None,
) -> Dict[str, int]:
    """
    Safely purge intermediate scratch files from a customer job work directory once composition is done.
    Preserves: final deliverables (*final*.mp4, *Final*.mp4), thumbnails (*.jpg/png), subtitle (*.srt/vtt), metadata (*.json).
    Removes: individual scene slices (scene_*.mp4), audio stems, concat txts, temp fragments.
    """
    work = Path(work_dir)
    if not work.exists() or not work.is_dir():
        return {"deleted_files": 0, "freed_bytes": 0}

    now = time.time()
    max_age_sec = (max_age_hours * 3600.0) if max_age_hours is not None else None

    # Check if a final video exists
    has_final = False
    for p in work.iterdir():
        if p.is_file() and ("final" in p.name.lower() or "c06e_curated" in p.name.lower()) and p.suffix.lower() == ".mp4":
            has_final = True
            break

    # If keep_finals is true, but no final exists and age is within threshold, skip purging to avoid deleting in-progress work
    if keep_finals and not has_final and max_age_sec is not None:
        try:
            mtime = work.stat().st_mtime
            if (now - mtime) < max_age_sec:
                return {"deleted_files": 0, "freed_bytes": 0}
        except Exception:
            pass

    deleted_count = 0
    freed_bytes = 0

    # 1. Clean explicit intermediate patterns
    for pat in INTERMEDIATE_PATTERNS:
        for f in work.rglob(pat):
            if f.is_file():
                try:
                    freed_bytes += f.stat().st_size
                    f.unlink(missing_ok=True)
                    deleted_count += 1
                except Exception:
                    pass

    # 2. Clean scene slice videos (scene_*.mp4) if final video is present or if directory is old
    if has_final or (max_age_sec is not None and (now - work.stat().st_mtime) > max_age_sec):
        for f in list(work.glob("scene_*.mp4")) + list(work.glob("agnes_*.mp4")):
            if f.is_file() and "final" not in f.name.lower():
                try:
                    freed_bytes += f.stat().st_size
                    f.unlink(missing_ok=True)
                    deleted_count += 1
                except Exception:
                    pass

        # Also purge intermediate audio stems (.wav) if final exists
        for f in list(work.glob("scene_*.wav")) + list(work.glob("voiceover_*.wav")) + list(work.glob("narration_*.wav")):
            if f.is_file():
                try:
                    freed_bytes += f.stat().st_size
                    f.unlink(missing_ok=True)
                    deleted_count += 1
                except Exception:
                    pass

    # 3. Clean temporary subdirectories (_tmp_*, SCENE_LOCAL if empty)
    for child in work.iterdir():
        if child.is_dir() and any(child.name.startswith(p) for p in TEMP_DIR_PREFIXES):
            try:
                for subfile in child.rglob("*"):
                    if subfile.is_file():
                        freed_bytes += subfile.stat().st_size
                        subfile.unlink(missing_ok=True)
                        deleted_count += 1
                shutil.rmtree(str(child), ignore_errors=True)
            except Exception:
                pass

    if deleted_count > 0:
        logger.info(
            "Purged %d intermediate files (%.2f MB freed) from work directory: %s",
            deleted_count,
            freed_bytes / (1024 * 1024),
            work.name,
        )

    return {"deleted_files": deleted_count, "freed_bytes": freed_bytes}


def clean_temp_artifacts(
    root_dir: Optional[Path] = None,
    *,
    max_age_hours: float = 24.0,
    force_all_temp: bool = False,
) -> Dict[str, int]:
    """
    Scan root_dir (Output, data/customer_generation_work, data/work_dirs) and purge stale temp files.
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

    # 2. Clean scratch files in Output directory
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

    # 3. Clean customer generation work directories (data/customer_generation_work & data/work_dirs)
    work_roots = [
        root_dir / "data" / "customer_generation_work",
        root_dir / "data" / "work_dirs",
    ]
    for wroot in work_roots:
        if not wroot.exists():
            continue
        for customer_dir in wroot.iterdir():
            if not customer_dir.is_dir():
                continue
            for job_dir in customer_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                try:
                    res = purge_customer_work_intermediates(
                        job_dir,
                        keep_finals=True,
                        max_age_hours=None if force_all_temp else max_age_hours,
                    )
                    deleted_count += res.get("deleted_files", 0)
                    freed_bytes += res.get("freed_bytes", 0)
                except Exception as exc:
                    logger.debug("Skip job dir %s: %s", job_dir.name, exc)

    if deleted_count > 0:
        mb_freed = freed_bytes / (1024 * 1024)
        logger.info(
            "Garbage collection completed: purged %d temp files (%.2f MB freed)",
            deleted_count,
            mb_freed,
        )

    return {"deleted_files": deleted_count, "freed_bytes": freed_bytes}


def auto_garbage_collect() -> Dict[str, int]:
    """Lightweight hook to run at the start or end of video jobs."""
    try:
        return clean_temp_artifacts(max_age_hours=24.0)
    except Exception as exc:
        logger.debug("auto_garbage_collect error: %s", exc)
        return {"deleted_files": 0, "freed_bytes": 0}
