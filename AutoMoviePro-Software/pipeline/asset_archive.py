"""
Archive orchestrator: decouple → compress → Drive upload (rotated) → mark migration_ready.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def archive_finished_clip(
    *,
    asset_id: str,
    source_video: Path,
    source_audio: Optional[Path] = None,
    script: str = "",
    visual_tags: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    lang_code: str = "en",
    channel_id: int = 0,
    user_login: str = "",
    niche: str = "",
    element: str = "",
    upload_drive: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from pipeline.asset_compress import build_compressed_bundle
    from pipeline.asset_vault import package_decoupled_asset
    from pipeline.google_drive_rotation import ensure_drive_tables, upload_asset_bundle

    ensure_drive_tables()
    manifest = package_decoupled_asset(
        asset_id=asset_id,
        source_video=Path(source_video),
        source_audio=Path(source_audio) if source_audio else None,
        script=script,
        visual_tags=visual_tags,
        keywords=keywords,
        lang_code=lang_code,
        channel_id=channel_id,
        user_login=user_login,
        niche=niche,
        element=element,
        extra=extra,
    )
    compressed = build_compressed_bundle(manifest, crf=30)
    drive: Dict[str, Any] = {"ok": False, "skipped": True}
    if upload_drive:
        drive = upload_asset_bundle(
            asset_id=manifest["asset_id"],
            audio=Path(compressed["audio"]),
            video=Path(compressed["video"]),
            metadata=Path(manifest["metadata"]),
            local_vault_dir=manifest["vault_dir"],
            poster=str(compressed.get("poster") or ""),
        )
        # stamp metadata
        try:
            meta_path = Path(manifest["metadata"])
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["migration_ready"] = bool(drive.get("migration_ready"))
            meta["drive"] = {k: drive.get(k) for k in ("drive_email", "remote_audio_id", "remote_video_id", "remote_meta_id") if drive.get(k)}
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    result = {
        "ok": True,
        "asset_id": manifest["asset_id"],
        "vault": manifest,
        "compressed": compressed,
        "drive": drive,
        "migration_ready": bool(drive.get("migration_ready")),
    }
    Path(manifest["vault_dir"], "archive_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def archive_localized_tree(
    localize_dir: Path,
    *,
    base_id: str,
    channel_id: int = 0,
    niche: str = "",
    upload_drive: bool = True,
) -> List[Dict[str, Any]]:
    """Package each language folder under LOCALIZED/ into decoupled assets."""
    from pipeline.lang_config import LANG_FOLDERS, TARGET_LANG_CODES

    out: List[Dict[str, Any]] = []
    root = Path(localize_dir)
    if not root.exists():
        return out
    for code in TARGET_LANG_CODES:
        folder = root / LANG_FOLDERS.get(code, code)
        video = folder / "video.mp4"
        if not video.exists():
            continue
        audio = folder / "narration.m4a"
        if not audio.exists():
            audio = folder / "narration.mp3"
        script = ""
        narr = folder / "narration.txt"
        if narr.exists():
            script = narr.read_text(encoding="utf-8")
        tags: List[str] = []
        meta_p = folder / "meta.json"
        if meta_p.exists():
            try:
                tags = list((json.loads(meta_p.read_text(encoding="utf-8")) or {}).get("keywords") or [])
            except Exception:
                pass
        try:
            row = archive_finished_clip(
                asset_id=f"{base_id}_{code}",
                source_video=video,
                source_audio=audio if audio.exists() else None,
                script=script,
                visual_tags=tags,
                keywords=tags,
                lang_code=code,
                channel_id=channel_id,
                niche=niche,
                upload_drive=upload_drive,
            )
            out.append(row)
        except Exception as exc:
            logger.warning("archive lang %s failed: %s", code, exc)
            out.append({"ok": False, "lang": code, "error": str(exc)[:200]})
    return out


def try_local_server_sync() -> Dict[str, Any]:
    """
    Cron-friendly: if AMP_LOCAL_ASSET_ROOT is set and reachable, copy migration_ready
    assets there and mark migrated_local.
    """
    import os
    import shutil

    from pipeline.google_drive_rotation import list_migration_ready, mark_migrated_local

    root = (os.environ.get("AMP_LOCAL_ASSET_ROOT") or "").strip()
    if not root:
        return {"ok": True, "skipped": True, "reason": "AMP_LOCAL_ASSET_ROOT unset"}
    dest_root = Path(root)
    try:
        dest_root.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return {"ok": False, "error": f"local_root_unreachable: {exc}"}

    moved = 0
    for row in list_migration_ready(50):
        vault = Path(row.get("local_vault_dir") or "")
        if not vault.exists():
            continue
        target = dest_root / vault.name
        try:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(vault, target)
            mark_migrated_local(row["asset_id"], str(target))
            moved += 1
        except Exception as exc:
            logger.warning("local sync %s: %s", row.get("asset_id"), exc)
    return {"ok": True, "moved": moved, "dest": str(dest_root)}
