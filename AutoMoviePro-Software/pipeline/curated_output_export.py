"""Export finished work_dir → Output/{Short|Long}/{NN}_{Title}/{Lang}/…

Copies (does not move) runtime assets into the canonical curated layout with
title-based unique filenames. Safe to re-run (overwrites same destinations).

Also migrates legacy flat packages (Audio Clip / Video Clip / …) into the
per-language tree.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from pipeline.lang_config import LANG_FOLDERS, folder_for_lang
from pipeline.output_layout import (
    CURATED_OUTPUT_ROOT,
    PackagePaths,
    build_video_identity,
    ensure_package_dirs,
    write_json,
)

logger = logging.getLogger(__name__)

_LANG_NAMES = tuple(LANG_FOLDERS.values())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _copy(src: Path, dest: Path) -> Optional[Path]:
    if not src or not Path(src).is_file():
        return None
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() != Path(src).resolve():
        shutil.copy2(src, dest)
    return dest


def _discover_scene_indexes(work: Path) -> List[int]:
    idxs: set[int] = set()
    for p in work.glob("scene_*.mp4"):
        m = re.match(r"scene_(\d+)", p.stem)
        if m:
            idxs.add(int(m.group(1)))
    for p in work.glob("SCENE_LOCAL/*"):
        if p.is_dir() and p.name.isdigit():
            idxs.add(int(p.name))
    return sorted(idxs)


def _scene_video(work: Path, idx: int) -> Optional[Path]:
    hits = sorted(work.glob(f"scene_{idx:02d}_*.mp4"))
    hits = [h for h in hits if h.is_file() and h.stat().st_size > 5000]
    return hits[0] if hits else None


def _scene_audio(work: Path, idx: int) -> Optional[Path]:
    for cand in (
        work / f"narration_{idx:02d}.m4a",
        work / f"narration_{idx:02d}.mp3",
        work / f"narration_{idx:02d}.wav",
    ):
        if cand.is_file() and cand.stat().st_size > 500:
            return cand
    for p in work.glob(f"scene_{idx:02d}_*.m4a"):
        if p.is_file():
            return p
    return None


def _extract_still(video: Path, dest: Path) -> Optional[Path]:
    try:
        from pipeline.compose import ffmpeg_bin
        import subprocess

        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            ffmpeg_bin(),
            "-y",
            "-ss",
            "0.4",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if dest.is_file() and dest.stat().st_size > 800:
            return dest
        logger.debug("still extract failed rc=%s %s", r.returncode, (r.stderr or "")[-200:])
    except Exception as exc:
        logger.debug("still extract error: %s", exc)
    return None


def _detect_lang_in_name(name: str) -> str:
    for ln in _LANG_NAMES:
        if f"_{ln}." in name or name.endswith(f"_{ln}") or f"_{ln}_" in name:
            return ln
    return "English"


def _copy_script_shared(work: Path, paths: PackagePaths, title: str) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    mapping = [
        ("director_plan.json", "Creative_Plan.json"),
        ("DURATION_CONTRACT.json", "Duration_Contract.json"),
        ("trs_handoff.json", "TRS_Handoff.json"),
        ("english_master.srt", "Subtitles_English_Master.srt"),
        ("LOCALIZE_RESULT.json", "Localize_Result.json"),
    ]
    for src_name, dest_name in mapping:
        src = work / src_name
        if not src.is_file():
            continue
        dest = paths.shared / f"{paths.identity.video_uid}_{dest_name}"
        if _copy(src, dest):
            files.append({"path": str(dest.relative_to(paths.root)).replace("\\", "/"), "role": "shared_script"})
    topic_path = paths.shared / f"{paths.identity.video_uid}_Topic.txt"
    topic_path.write_text((title or paths.identity.title).strip() + "\n", encoding="utf-8")
    files.append({"path": str(topic_path.relative_to(paths.root)).replace("\\", "/"), "role": "topic"})
    try:
        plan = json.loads((work / "director_plan.json").read_text(encoding="utf-8"))
        scenes = plan.get("scenes") or []
        dialogue = []
        for i, sc in enumerate(scenes):
            if not isinstance(sc, dict):
                continue
            dialogue.append(
                {
                    "scene_index": i,
                    "shot": f"S{i+1:02d}",
                    "asset_uid": paths.identity.asset_uid(role="Asset", scene=i, lang="en"),
                    "narration": sc.get("narration") or sc.get("dialogue") or "",
                    "element": sc.get("element") or "",
                    "dialogue_id": sc.get("dialogue_id") or f"beat-{i+1}",
                }
            )
        dlg = paths.shared / f"{paths.identity.video_uid}_Dialogue_Plan.json"
        write_json(dlg, dialogue)
        files.append({"path": str(dlg.relative_to(paths.root)).replace("\\", "/"), "role": "dialogue_plan"})
        lines = [f"Scene {i+1:02d}: {d.get('narration')}" for i, d in enumerate(dialogue) if d.get("narration")]
        script = paths.shared / f"{paths.identity.video_uid}_Script_English.txt"
        script.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
        files.append({"path": str(script.relative_to(paths.root)).replace("\\", "/"), "role": "script"})
    except Exception as exc:
        logger.debug("dialogue plan export soft-fail: %s", exc)
    return files


def _export_language_pack(
    *,
    work: Path,
    paths: PackagePaths,
    lang_code: str,
    final_src: Optional[Path],
    scene_indexes: Sequence[int],
    inventory: List[Dict[str, Any]],
) -> None:
    lang_name = folder_for_lang(lang_code)
    if final_src and final_src.is_file():
        dest = paths.asset_path(lang=lang_code, role="final", ext=".mp4")
        if _copy(final_src, dest):
            inventory.append(
                {
                    "path": str(dest.relative_to(paths.root)).replace("\\", "/"),
                    "role": "final",
                    "language": lang_name,
                    "scene": None,
                    "shot": None,
                    "asset_uid": Path(dest).stem,
                    "bytes": dest.stat().st_size,
                    "sha256": _sha256(dest),
                    "canonical": True,
                }
            )

    for idx in scene_indexes:
        v_src: Optional[Path] = None
        a_src: Optional[Path] = None
        srt_src: Optional[Path] = None
        narr_txt: Optional[Path] = None
        if lang_code == "en":
            v_src = _scene_video(work, idx)
            a_src = _scene_audio(work, idx)
        else:
            loc = work / "SCENE_LOCAL" / f"{idx:02d}" / lang_code
            if loc.is_dir():
                for name in ("video.mp4", "clip.mp4"):
                    if (loc / name).is_file():
                        v_src = loc / name
                        break
                for name in ("narration.m4a", "audio.m4a", "narration.mp3"):
                    if (loc / name).is_file():
                        a_src = loc / name
                        break
                if (loc / "subtitles.srt").is_file():
                    srt_src = loc / "subtitles.srt"
                if (loc / "narration.txt").is_file():
                    narr_txt = loc / "narration.txt"

        if v_src:
            dest = paths.asset_path(lang=lang_code, role="video_clip", ext=".mp4", scene=idx)
            if _copy(v_src, dest):
                inventory.append(
                    {
                        "path": str(dest.relative_to(paths.root)).replace("\\", "/"),
                        "role": "video_clip",
                        "language": lang_name,
                        "scene": f"{idx+1:02d}",
                        "shot": f"S{idx+1:02d}",
                        "asset_uid": dest.stem,
                        "bytes": dest.stat().st_size,
                        "sha256": _sha256(dest),
                        "canonical": True,
                    }
                )
            img = paths.asset_path(lang=lang_code, role="image", ext=".jpg", scene=idx)
            if _extract_still(v_src, img):
                inventory.append(
                    {
                        "path": str(img.relative_to(paths.root)).replace("\\", "/"),
                        "role": "image",
                        "language": lang_name,
                        "scene": f"{idx+1:02d}",
                        "shot": f"S{idx+1:02d}",
                        "asset_uid": img.stem,
                        "bytes": img.stat().st_size,
                        "sha256": _sha256(img),
                        "canonical": True,
                    }
                )

        if a_src:
            ext = a_src.suffix or ".m4a"
            dest = paths.asset_path(lang=lang_code, role="audio_clip", ext=ext, scene=idx)
            if _copy(a_src, dest):
                inventory.append(
                    {
                        "path": str(dest.relative_to(paths.root)).replace("\\", "/"),
                        "role": "audio_clip",
                        "language": lang_name,
                        "scene": f"{idx+1:02d}",
                        "shot": f"S{idx+1:02d}",
                        "asset_uid": dest.stem,
                        "bytes": dest.stat().st_size,
                        "sha256": _sha256(dest),
                        "canonical": True,
                    }
                )

        if narr_txt:
            dest = paths.asset_path(lang=lang_code, role="script", ext=".txt", scene=idx, suffix_tag="_Narration")
            if _copy(narr_txt, dest):
                inventory.append(
                    {
                        "path": str(dest.relative_to(paths.root)).replace("\\", "/"),
                        "role": "narration_text",
                        "language": lang_name,
                        "scene": f"{idx+1:02d}",
                        "shot": f"S{idx+1:02d}",
                        "asset_uid": dest.stem,
                        "bytes": dest.stat().st_size,
                        "sha256": _sha256(dest),
                        "canonical": True,
                    }
                )

        if srt_src and lang_code != "en":
            dest = paths.asset_path(lang=lang_code, role="subtitle", ext=".srt", suffix_tag="_Subtitles")
            if not dest.is_file() and _copy(srt_src, dest):
                inventory.append(
                    {
                        "path": str(dest.relative_to(paths.root)).replace("\\", "/"),
                        "role": "subtitle",
                        "language": lang_name,
                        "scene": None,
                        "shot": None,
                        "asset_uid": dest.stem,
                        "bytes": dest.stat().st_size,
                        "sha256": _sha256(dest),
                        "canonical": True,
                    }
                )

    loc_root = work / "LOCALIZED" / lang_name
    if loc_root.is_dir():
        for cand in list(loc_root.glob("*.mp4")) + list(loc_root.glob("**/video.mp4")):
            if cand.is_file() and cand.stat().st_size > 8000:
                dest = paths.asset_path(lang=lang_code, role="final", ext=".mp4")
                if _copy(cand, dest):
                    inventory.append(
                        {
                            "path": str(dest.relative_to(paths.root)).replace("\\", "/"),
                            "role": "final",
                            "language": lang_name,
                            "scene": None,
                            "shot": None,
                            "asset_uid": dest.stem,
                            "bytes": dest.stat().st_size,
                            "sha256": _sha256(dest),
                            "canonical": True,
                        }
                    )
                break


def export_curated_package(
    work_dir: Path | str,
    *,
    title: str,
    video_type: str = "short",
    final_path: Optional[Path] = None,
    job_id: Any = None,
    languages: Optional[Sequence[str]] = None,
    series: Optional[str] = None,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build Output/{Short|Long}/{NN}_{Title}/{Lang}/… package from a work dir."""
    work = Path(work_dir)
    if not work.is_dir():
        return {"ok": False, "error": "work_dir_missing", "work_dir": str(work)}

    title_s = (title or "").strip() or work.name
    identity = build_video_identity(
        title=title_s,
        video_type=video_type,
        series=series,
        root=root or CURATED_OUTPUT_ROOT,
    )
    langs = [str(x).lower()[:2] for x in (languages or ["en"]) if x]
    if "en" not in langs:
        langs = ["en", *langs]
    paths = ensure_package_dirs(identity, languages=langs)

    inventory: List[Dict[str, Any]] = []
    shared_files = _copy_script_shared(work, paths, title_s)
    inventory.extend(
        {
            **f,
            "language": "Shared",
            "scene": None,
            "shot": None,
            "asset_uid": Path(f["path"]).stem,
            "bytes": (paths.root / f["path"]).stat().st_size if (paths.root / f["path"]).is_file() else 0,
            "sha256": _sha256(paths.root / f["path"]) if (paths.root / f["path"]).is_file() else "",
            "canonical": True,
        }
        for f in shared_files
    )

    scene_indexes = _discover_scene_indexes(work)
    final = Path(final_path) if final_path else (work / f"final_{identity.video_type}.mp4")
    if not final.is_file():
        finals = list(work.glob("final_*.mp4"))
        final = finals[0] if finals else final

    for code in langs:
        _export_language_pack(
            work=work,
            paths=paths,
            lang_code=code,
            final_src=final if code == "en" else None,
            scene_indexes=scene_indexes,
            inventory=inventory,
        )

    en_srt = work / "english_master.srt"
    if en_srt.is_file():
        dest = paths.asset_path(lang="en", role="subtitle", ext=".srt", suffix_tag="_Subtitles")
        if _copy(en_srt, dest):
            inventory.append(
                {
                    "path": str(dest.relative_to(paths.root)).replace("\\", "/"),
                    "role": "subtitle",
                    "language": "English",
                    "scene": None,
                    "shot": None,
                    "asset_uid": dest.stem,
                    "bytes": dest.stat().st_size,
                    "sha256": _sha256(dest),
                    "canonical": True,
                }
            )

    meta = {
        "video_number": identity.series,
        "kind": identity.kind,
        "clean_title": identity.title,
        "title_slug": identity.title_slug,
        "video_uid": identity.video_uid,
        "title_hash": identity.title_hash,
        "folder": identity.folder_name,
        "package_root": identity.package_root,
        "source_job_id": job_id,
        "source_work_dir": str(work.resolve()),
        "languages": [folder_for_lang(c) for c in langs],
        "scene_count": len(scene_indexes),
        "naming": {
            "pattern_shot": "{video_uid}_S{NN}_{Language}.{ext}",
            "pattern_final": "{video_uid}_Final_{Language}.mp4",
            "example_image": f"{identity.video_uid}_S01_English.jpg",
            "note": "Filename alone encodes series, kind, title slug, shot, language",
        },
        "organized_at": datetime.now(timezone.utc).isoformat(),
        "note": "Curated copy from production work_dir; runtime originals remain in place",
    }
    write_json(paths.meta / "Package_Metadata.json", meta)
    write_json(
        paths.meta / "LINEAGE_INVENTORY.json",
        {
            "package": identity.folder_name,
            "video_uid": identity.video_uid,
            "kind": identity.kind,
            "source_job_id": job_id,
            "files": inventory,
        },
    )
    write_json(
        paths.meta / "ASSET_ID_MAP.json",
        {
            "video_uid": identity.video_uid,
            "title_hash": identity.title_hash,
            "shots": {
                f"S{i+1:02d}": {
                    "scene_index_0based": i,
                    "asset_uid_en": identity.asset_uid(role="Asset", scene=i, lang="en"),
                }
                for i in scene_indexes
            },
        },
    )
    write_json(paths.shared / f"{identity.video_uid}_Package_Metadata.json", meta)

    logger.info("Curated package ready: %s (%s assets)", paths.root, len(inventory))
    return {
        "ok": True,
        "package_root": str(paths.root),
        "video_uid": identity.video_uid,
        "folder": identity.folder_name,
        "identity": identity.to_dict(),
        "asset_count": len(inventory),
        "languages": [folder_for_lang(c) for c in langs],
    }


def _legacy_dest_for_file(
    *,
    root: Path,
    identity,
    paths: PackagePaths,
    src: Path,
    parent_role: str,
) -> tuple[Path, str, Optional[str], Optional[str]]:
    """Return (dest, role, language_or_Shared, shot)."""
    name = src.name
    lower = name.lower()
    lang = _detect_lang_in_name(name)
    scene_m = re.search(r"Scene_(\d{2})", name, re.I)
    scene_1 = int(scene_m.group(1)) if scene_m else None
    shot = f"S{scene_1:02d}" if scene_1 else None
    scene_0 = (scene_1 - 1) if scene_1 is not None else None

    if parent_role == "final" or re.search(r"_Final_", name, re.I):
        dest = paths.asset_path(lang=lang, role="final", ext=src.suffix)
        return dest, "final", lang, None

    if parent_role in ("video_clip", "audio_clip", "image") and scene_0 is not None:
        dest = paths.asset_path(lang=lang, role=parent_role, ext=src.suffix, scene=scene_0)
        return dest, parent_role, lang, shot

    if "thumbnail" in lower:
        dest = paths.role_dir(lang, "image") / f"{identity.video_uid}_Thumbnail_{lang}{src.suffix}"
        return dest, "image", lang, None

    # Scripts / meta
    if "lineage_inventory" in lower or "package_metadata" in lower:
        dest = root / "_meta" / name
        return dest, "meta", "Shared", None
    if lower.startswith(f"{identity.series}_{identity.kind.lower()}_meta".lower()) or "_meta_" in lower:
        dest = root / "_meta" / f"{identity.video_uid}_{name.split('_', 2)[-1]}"
        # Keep readable meta name
        dest = root / "_meta" / name.replace(
            f"{identity.series}_{identity.kind}_", f"{identity.video_uid}_", 1
        )
        return dest, "meta", "Shared", None

    shared_map = {
        "topic": f"{identity.video_uid}_Topic.txt",
        "dialogue_plan": f"{identity.video_uid}_Dialogue_Plan.json",
        "creative_plan": f"{identity.video_uid}_Creative_Plan.json",
        "visual_beat_plan": f"{identity.video_uid}_Visual_Beat_Plan.json",
        "original_script": f"{identity.video_uid}_Original_Script.txt",
    }
    for key, dest_name in shared_map.items():
        if key in lower.replace("-", "_"):
            return root / "Shared" / dest_name, "shared", "Shared", None

    if "subtitle" in lower:
        dest = paths.role_dir(lang, "script") / f"{identity.video_uid}_Subtitles_{lang}{src.suffix}"
        return dest, "subtitle", lang, None
    if re.search(r"_script_", lower) or lower.endswith(f"_script_{lang.lower()}{src.suffix.lower()}"):
        dest = paths.role_dir(lang, "script") / f"{identity.video_uid}_Script_{lang}{src.suffix}"
        return dest, "script", lang, None
    if "production_manifest" in lower or "localize" in lower:
        # Strip legacy `{NN}_{Kind}_` prefix when present
        rest = name
        legacy_prefix = f"{identity.series}_{identity.kind}_"
        if name.startswith(legacy_prefix):
            rest = name[len(legacy_prefix) :]
        return root / "Shared" / f"{identity.video_uid}_{rest}", "shared", "Shared", None

    # Default: Shared with video_uid prefix
    return root / "Shared" / f"{identity.video_uid}_{name}", "shared", "Shared", None


def migrate_legacy_package(
    package_dir: Path | str,
    *,
    dry_run: bool = False,
    remove_legacy_dirs: bool = True,
) -> Dict[str, Any]:
    """Convert flat role dirs into per-language folders with title-based IDs."""
    root = Path(package_dir)
    if not root.is_dir():
        return {"ok": False, "error": "missing_package", "path": str(root)}
    if (root / "English").is_dir() and (root / "_meta").is_dir():
        return {"ok": True, "skipped": True, "reason": "already_migrated", "path": str(root)}

    m_folder = re.match(r"^(\d{2,})_(.+)$", root.name)
    if not m_folder:
        return {"ok": False, "error": "bad_folder_name", "path": str(root)}
    series, slug = m_folder.group(1), m_folder.group(2)
    parent_kind = root.parent.name
    kind = "Short" if parent_kind.lower() == "short" else "Long"
    video_type = "short" if kind == "Short" else "long"
    title = slug.replace("_", " ")
    identity = build_video_identity(
        title=title,
        video_type=video_type,
        series=series,
        existing_folder=root.name,
        root=root.parent.parent,
    )
    identity.package_root = str(root.resolve())
    identity.folder_name = root.name
    identity.title_slug = slug
    identity.kind = kind
    identity.video_uid = f"{series}_{kind}_{slug}"
    identity.series = series

    paths = PackagePaths(identity=identity, root=root, shared=root / "Shared", meta=root / "_meta")
    langs_found: set[str] = set()
    moves: List[Dict[str, str]] = []
    inventory: List[Dict[str, Any]] = []

    role_dirs = {
        "Audio Clip": "audio_clip",
        "Audio_Clip": "audio_clip",
        "Video Clip": "video_clip",
        "Video_Clip": "video_clip",
        "Final": "final",
        "Image": "image",
        "Script": "script",
    }

    for dname, parent_role in role_dirs.items():
        src_dir = root / dname
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.iterdir()):
            if not src.is_file():
                continue
            dest, role, lang_or_shared, shot = _legacy_dest_for_file(
                root=root,
                identity=identity,
                paths=paths,
                src=src,
                parent_role=parent_role,
            )
            if lang_or_shared and lang_or_shared != "Shared":
                langs_found.add(lang_or_shared)
            moves.append({"from": src.name, "to": str(Path(dest).relative_to(root)).replace("\\", "/"), "role": role})
            if not dry_run:
                _copy(src, dest)
            inventory.append(
                {
                    "path": str(Path(dest).relative_to(root)).replace("\\", "/") if not dry_run else moves[-1]["to"],
                    "role": role,
                    "language": lang_or_shared,
                    "shot": shot,
                    "asset_uid": Path(dest).stem,
                    "legacy": src.name,
                    "canonical": True,
                }
            )

    if not dry_run:
        lang_codes = []
        for ln in sorted(langs_found) or ["English"]:
            code = next((k for k, v in LANG_FOLDERS.items() if v == ln), "en")
            lang_codes.append(code)
        ensure_package_dirs(identity, languages=lang_codes or ["en"])
        (root / "Shared").mkdir(parents=True, exist_ok=True)
        (root / "_meta").mkdir(parents=True, exist_ok=True)
        meta = {
            "video_number": series,
            "kind": kind,
            "clean_title": title,
            "title_slug": slug,
            "video_uid": identity.video_uid,
            "title_hash": identity.title_hash,
            "folder": root.name,
            "package_root": str(root.resolve()),
            "migrated_from": "legacy_flat_role_dirs",
            "languages": sorted(langs_found) or ["English"],
            "naming": {
                "pattern_shot": "{video_uid}_S{NN}_{Language}.{ext}",
                "pattern_final": "{video_uid}_Final_{Language}.mp4",
                "example_image": f"{identity.video_uid}_S01_English.jpg",
            },
            "organized_at": datetime.now(timezone.utc).isoformat(),
            "moved_count": len(moves),
        }
        write_json(root / "_meta" / "Package_Metadata.json", meta)
        write_json(
            root / "_meta" / "LINEAGE_INVENTORY.json",
            {"package": root.name, "video_uid": identity.video_uid, "files": inventory},
        )
        write_json(
            root / "_meta" / "ASSET_ID_MAP.json",
            {
                "video_uid": identity.video_uid,
                "shots": {
                    e["shot"]: {"asset_uid": e.get("asset_uid"), "language": e.get("language")}
                    for e in inventory
                    if e.get("shot")
                },
            },
        )
        if remove_legacy_dirs:
            for dname in role_dirs:
                d = root / dname
                if d.is_dir():
                    try:
                        shutil.rmtree(d)
                    except Exception as exc:
                        logger.warning("legacy dir remove soft-fail %s: %s", d, exc)

    return {
        "ok": True,
        "path": str(root),
        "video_uid": identity.video_uid,
        "moves": len(moves),
        "languages": sorted(langs_found),
        "dry_run": dry_run,
        "sample_moves": moves[:8],
    }


def migrate_all_curated_packages(
    *,
    root: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Migrate every Short/Long package under Output/ to per-language layout."""
    base = Path(root or CURATED_OUTPUT_ROOT)
    results: List[Dict[str, Any]] = []
    for kind in ("Short", "Long"):
        kind_dir = base / kind
        if not kind_dir.is_dir():
            continue
        for pkg in sorted(kind_dir.iterdir()):
            if not pkg.is_dir():
                continue
            if not re.match(r"^\d{2,}_", pkg.name):
                continue
            results.append(migrate_legacy_package(pkg, dry_run=dry_run))
    ok_n = sum(1 for r in results if r.get("ok"))
    return {"ok": ok_n == len(results), "packages": len(results), "results": results}
