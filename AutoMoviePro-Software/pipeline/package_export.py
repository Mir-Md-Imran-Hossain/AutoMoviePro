from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def export_upload_package(
    *,
    dest_root: Path,
    channel_name: str,
    gadget: Dict[str, Any],
    video_type: str,
    video_path: Path,
    title: str,
    description: str,
    tags: List[str],
    thumbnail_path: Optional[Path] = None,
    extra: Optional[Dict[str, Any]] = None,
    subtitle_paths: Optional[List[Path]] = None,
) -> Path:
    """
    Create an upload-ready folder:
      video.mp4, title.txt, description.txt, tags.txt, thumbnail.jpg,
      subtitles (sidecar .srt), meta.json
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_g = "".join(c if c.isalnum() or c in "-_ " else "" for c in (gadget.get("name") or "gadget"))
    safe_g = safe_g.strip().replace(" ", "_")[:60] or "gadget"
    folder = dest_root / f"{video_type}_{safe_g}_{stamp}"
    folder.mkdir(parents=True, exist_ok=True)

    final_video = folder / "video.mp4"
    if video_path.exists():
        shutil.copy2(video_path, final_video)
    else:
        raise FileNotFoundError(f"video missing: {video_path}")

    (folder / "title.txt").write_text(title.strip() + "\n", encoding="utf-8")
    (folder / "description.txt").write_text(description.strip() + "\n", encoding="utf-8")
    tags_line = ", ".join(tags) if isinstance(tags, list) else str(tags)
    (folder / "tags.txt").write_text(tags_line.strip() + "\n", encoding="utf-8")

    thumb_out = folder / "thumbnail.jpg"
    if thumbnail_path and thumbnail_path.exists():
        # normalize extension
        if thumbnail_path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}:
            try:
                from PIL import Image

                Image.open(thumbnail_path).convert("RGB").save(thumb_out, quality=92)
            except Exception:
                shutil.copy2(thumbnail_path, folder / f"thumbnail{thumbnail_path.suffix}")
        else:
            shutil.copy2(thumbnail_path, thumb_out)

    subtitle_files: List[str] = []
    for sp in subtitle_paths or []:
        src = Path(sp)
        if not src.is_file():
            continue
        dest = folder / src.name
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
        subtitle_files.append(dest.name)

    # Auto-pick common workdir sidecars if caller did not pass explicit list
    if not subtitle_files:
        for cand in (
            video_path.parent / "english_master.srt",
            video_path.parent / "master.srt",
            video_path.with_suffix(".srt"),
        ):
            if cand.is_file():
                dest = folder / cand.name
                shutil.copy2(cand, dest)
                subtitle_files.append(dest.name)

    meta = {
        "channel": channel_name,
        "gadget": gadget,
        "video_type": video_type,
        "title": title,
        "description": description,
        "tags": tags,
        "video_file": final_video.name,
        "subtitle_files": subtitle_files,
        "created_at": datetime.now().isoformat(),
        "upload_ready": True,
        "extra": extra or {},
    }
    try:
        from app.release_identity import RELEASE_VERSION, get_release_identity

        ident = get_release_identity(include_media=False)
        meta["release_version"] = RELEASE_VERSION
        meta["build_id"] = ident.get("build_id")
    except Exception:
        pass
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    readme_lines = [
        "Upload-ready package",
        "1) video.mp4",
        "2) title.txt",
        "3) description.txt",
        "4) tags.txt",
        "5) thumbnail.jpg",
        "6) subtitle sidecar (.srt) when available",
        "Upload step will be tested separately.",
        "",
    ]
    if subtitle_files:
        readme_lines.append("Subtitles: " + ", ".join(subtitle_files))
    (folder / "README_UPLOAD.txt").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    return folder
