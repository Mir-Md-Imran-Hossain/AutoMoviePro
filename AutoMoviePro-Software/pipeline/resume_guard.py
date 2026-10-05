"""Resume safety: never reuse a clip built for a different beat.

Passed clips are kept. A beat is regenerated only when the agent already
failed it (AV_FAIL) or the clip is missing / for a different narration.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CANON_CLIP = re.compile(r"^scene_(\d{2})_([A-Za-z0-9]+)\.mp4$")


def clip_fingerprint(
    *,
    narration: str,
    visual_prompt: str = "",
    element: str = "",
    size: str = "",
) -> str:
    raw = "|".join(
        [
            (narration or "").strip(),
            (visual_prompt or "").strip()[:400],
            (element or "").strip().lower(),
            (size or "").strip(),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def resume_meta_path(work: Path, idx: int, element: str) -> Path:
    return Path(work) / f"scene_{idx:02d}_{element}_resume.json"


def write_resume_meta(
    work: Path,
    idx: int,
    element: str,
    *,
    fingerprint: str,
    extra: Dict[str, Any] | None = None,
) -> Path:
    path = resume_meta_path(work, idx, element)
    payload = {"fingerprint": fingerprint, "element": element, "idx": idx}
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def should_reuse_existing_clip(
    clip: Path,
    *,
    work: Path,
    idx: int,
    element: str,
    fingerprint: str,
    min_bytes: int = 20000,
) -> Tuple[bool, str]:
    """
    Return (ok, reason). Size-only resume is unsafe; fingerprint must match
    this beat's narration+prompt, then the caller still runs hard gates.
    """
    clip = Path(clip)
    if not clip.exists():
        return False, "missing"
    try:
        size = clip.stat().st_size
    except Exception:
        return False, "stat_failed"
    if size < min_bytes:
        return False, f"too_small:{size}"
    if scene_agent_failed(work, idx):
        return False, "agent_failed"
    meta = resume_meta_path(work, idx, element)
    if not meta.exists():
        return False, "no_resume_meta"
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return False, "meta_corrupt"
    stored = str(data.get("fingerprint") or "")
    if stored != fingerprint:
        return False, "fingerprint_mismatch"
    return True, "fingerprint_ok"


def scene_agent_failed(work: Path, idx: int) -> bool:
    return (Path(work) / f"scene_{idx:02d}_AV_FAIL.txt").exists()


def canonical_scene_clip(work: Path, idx: int, element: str) -> Path:
    return Path(work) / f"scene_{idx:02d}_{element}.mp4"


def count_canonical_scene_clips(work: Path) -> int:
    work = Path(work)
    if not work.is_dir():
        return 0
    return sum(1 for p in work.glob("scene_*.mp4") if _CANON_CLIP.match(p.name))


def list_accepted_scene_indexes(work: Path) -> List[int]:
    """Scenes that already shipped (canonical clip, no AV_FAIL)."""
    work = Path(work)
    found: List[int] = []
    for p in work.glob("scene_*.mp4"):
        m = _CANON_CLIP.match(p.name)
        if not m:
            continue
        idx = int(m.group(1))
        if scene_agent_failed(work, idx):
            continue
        if p.stat().st_size < 20000:
            continue
        found.append(idx)
    return sorted(set(found))


def _folder_stamp(name: str) -> Optional[datetime]:
    parts = (name or "").split("_")
    if len(parts) < 2:
        return None
    try:
        return datetime.strptime(f"{parts[-2]}_{parts[-1]}", "%Y%m%d_%H%M%S")
    except Exception:
        return None


def folder_is_fresh(name: str, *, max_age_hours: float = 18.0) -> bool:
    stamp = _folder_stamp(name)
    if stamp is None:
        return True
    return datetime.now() - stamp <= timedelta(hours=max_age_hours)


def find_completed_final(
    output_dir: Path,
    *,
    channel_id: Any,
    video_type: str,
    max_age_hours: float = 18.0,
) -> Optional[Path]:
    """Newest final_{type}.mp4 for this channel from a fresh job folder."""
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return None
    prefix = f"ch{channel_id}_{video_type}_"
    found: List[Tuple[float, Path]] = []
    for p in output_dir.iterdir():
        if not p.is_dir() or not p.name.startswith(prefix):
            continue
        if not folder_is_fresh(p.name, max_age_hours=max_age_hours):
            continue
        final = p / f"final_{video_type}.mp4"
        try:
            if final.exists() and final.stat().st_size > 50000:
                found.append((final.stat().st_mtime, final))
        except OSError:
            continue
    if not found:
        return None
    found.sort(key=lambda row: row[0], reverse=True)
    return found[0][1]


def find_resumable_work(
    output_dir: Path,
    *,
    channel_id: Any,
    video_type: str,
) -> Optional[Path]:
    """
    Latest incomplete job folder for this channel+type that still has
    reusable clips or a director plan. Finished finals are skipped so a
    new cycle starts clean. Stale folders (old dates) are ignored so a
    new topic cannot resume last week's leftover job.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return None
    prefix = f"ch{channel_id}_{video_type}_"
    scored: List[Tuple[int, float, Path]] = []
    for p in output_dir.iterdir():
        if not p.is_dir() or p.name.startswith("_"):
            continue
        if not p.name.startswith(prefix):
            continue
        # Never resume quarantined / failed folders (writing into *_FAILED_* burns cycles)
        uname = p.name.upper()
        if "FAILED" in uname or "QUARANTINE" in uname or uname.endswith("_BAD"):
            continue
        if not folder_is_fresh(p.name):
            continue
        if not (p / "director_plan.json").exists():
            continue
        final = p / f"final_{video_type}.mp4"
        try:
            if final.exists() and final.stat().st_size > 50000:
                continue
        except OSError:
            continue
        n = count_canonical_scene_clips(p)
        accepted = len(list_accepted_scene_indexes(p))
        score = accepted * 10 + n
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0.0
        scored.append((score, mtime, p))
    if not scored:
        return None
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best_score, _, best = scored[0]
    if best_score <= 0 and not (best / "director_plan.json").exists():
        return None
    logger.info("Resumable work selected %s (score=%s)", best.name, best_score)
    return best


def clear_scene_fail_marker(work: Path, idx: int) -> None:
    path = Path(work) / f"scene_{idx:02d}_AV_FAIL.txt"
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
