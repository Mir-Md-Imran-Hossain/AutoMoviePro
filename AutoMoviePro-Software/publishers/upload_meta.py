"""
Normalize upload metadata from a job row / UPLOAD_PACKAGE folder.
Used by YouTube + Facebook browser/API uploaders.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_tags(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        vals = [str(x).strip() for x in raw]
    else:
        text = str(raw).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    vals = [str(x).strip() for x in data]
                else:
                    vals = [p.strip() for p in text.split(",")]
            except Exception:
                vals = [p.strip() for p in text.split(",")]
        else:
            vals = [p.strip() for p in re.split(r"[,|\n]+", text)]
    out: List[str] = []
    seen = set()
    for v in vals:
        t = v.strip().lstrip("#")
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t[:40])
        if len(out) >= 25:
            break
    return out


def find_thumbnail(job: Dict[str, Any]) -> Optional[Path]:
    candidates: List[Path] = []
    for key in ("thumbnail", "thumbnail_path", "thumb_path"):
        raw = job.get(key)
        if raw:
            candidates.append(Path(str(raw)))
    local = Path(str(job.get("local_path") or ""))
    if local.parent.exists():
        work = local.parent
        candidates.extend(
            [
                work / "thumbnail.jpg",
                work / "thumbnail.png",
                work / "UPLOAD_PACKAGE",
            ]
        )
        pkg = work / "UPLOAD_PACKAGE"
        if pkg.is_dir():
            for child in sorted(pkg.glob("*/thumbnail.jpg"), reverse=True):
                candidates.append(child)
            for child in sorted(pkg.glob("*/thumbnail.png"), reverse=True):
                candidates.append(child)
    for c in candidates:
        if c.is_file():
            return c
        if c.is_dir():
            for name in ("thumbnail.jpg", "thumbnail.png"):
                p = c / name
                if p.is_file():
                    return p
    return None


def build_facebook_caption(title: str, description: str, tags: List[str]) -> str:
    parts: List[str] = []
    t = (title or "").strip()
    d = (description or "").strip()
    if t:
        parts.append(t)
    if d:
        parts.append(d)
    hashes = []
    for tag in tags[:12]:
        clean = re.sub(r"[^\w]+", "", tag, flags=re.UNICODE)
        if clean:
            hashes.append("#" + clean[:32])
    if hashes:
        parts.append(" ".join(hashes))
    return "\n\n".join(parts).strip()[:2000]


def youtube_video_id(url: str) -> Optional[str]:
    u = (url or "").strip()
    if not u or u.startswith("dry-run://"):
        return None
    m = re.search(r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{6,})", u)
    if m:
        return m.group(1)
    m = re.search(r"/video/([A-Za-z0-9_-]{6,})", u)
    return m.group(1) if m else None


def normalize_job_meta(job: Dict[str, Any]) -> Dict[str, Any]:
    title = str(job.get("title") or Path(str(job.get("local_path") or "video")).stem)[:100]
    description = str(job.get("description") or "")[:4800]
    tags = parse_tags(job.get("tags"))
    thumb = find_thumbnail(job)
    return {
        "title": title,
        "description": description,
        "tags": tags,
        "thumbnail": str(thumb) if thumb else None,
        "facebook_caption": build_facebook_caption(title, description, tags),
    }


def match_upload_window(now_hhmm: str, target_hhmm: str, window_minutes: int = 1) -> bool:
    """True if now is within ±window of target (handles exact minute + slight drift)."""
    try:
        nh, nm = [int(x) for x in (now_hhmm or "00:00")[:5].split(":")]
        th, tm = [int(x) for x in (target_hhmm or "00:00")[:5].split(":")]
    except Exception:
        return False
    now_m = nh * 60 + nm
    tgt_m = th * 60 + tm
    diff = abs(now_m - tgt_m)
    # wrap midnight
    diff = min(diff, 1440 - diff)
    return diff <= max(0, int(window_minutes))
