"""Operational backup / restore for Windows local deployment (H5).

Backs up persistent app state. Does NOT include .env secrets by default.
Does NOT invent automatic rollback — restore is operator-invoked.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import DATA_DIR, ROOT
from app.release_identity import RELEASE_VERSION, get_release_identity


BACKUP_ROOT_NAME = "backups"


def backup_root() -> Path:
    return ROOT / BACKUP_ROOT_NAME


def create_app_backup(
    *,
    dest_dir: Optional[Path] = None,
    include_env: bool = False,
    label: str = "manual",
) -> dict[str, Any]:
    """
    Create a zip backup of data/ (+ optional .env).

    Returns safe metadata only (paths relative, no secret values).
    """
    root = Path(dest_dir) if dest_dir else backup_root()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"amp_backup_{RELEASE_VERSION}_{label}_{stamp}.zip"
    zip_path = root / name

    identity = get_release_identity(include_media=False)
    manifest = {
        "kind": "amp_app_backup",
        "created_at": stamp,
        "release_version": identity.get("release_version"),
        "build_id": identity.get("build_id"),
        "include_env": bool(include_env),
        "includes": ["data/"],
        "excludes_default": [".env", "output/", "venv/", "customer_media"],
    }
    if include_env:
        manifest["includes"] = list(manifest["includes"]) + [".env"]

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BACKUP_MANIFEST.json", json.dumps(manifest, indent=2))
        data = Path(DATA_DIR)
        if data.is_dir():
            for p in data.rglob("*"):
                if p.is_file():
                    # skip obvious secret key files inside data if any
                    if p.name.lower() in {".secret.key", "secret.key"}:
                        continue
                    arc = Path("data") / p.relative_to(data)
                    zf.write(p, arcname=str(arc).replace("\\", "/"))
        if include_env:
            env = ROOT / ".env"
            if env.is_file():
                zf.write(env, arcname=".env")

    return {
        "ok": True,
        "backup_file": str(zip_path.name),
        "backup_dir": str(root),
        "include_env": bool(include_env),
        "bytes": zip_path.stat().st_size if zip_path.is_file() else 0,
        "release_version": identity.get("release_version"),
    }


def validate_backup_archive(zip_path: Path) -> dict[str, Any]:
    p = Path(zip_path)
    if not p.is_file():
        return {"ok": False, "reason": "missing_archive"}
    try:
        with zipfile.ZipFile(p, "r") as zf:
            names = zf.namelist()
            if "BACKUP_MANIFEST.json" not in names:
                return {"ok": False, "reason": "missing_manifest"}
            raw = zf.read("BACKUP_MANIFEST.json")
            meta = json.loads(raw.decode("utf-8"))
            if meta.get("kind") != "amp_app_backup":
                return {"ok": False, "reason": "invalid_kind"}
            return {"ok": True, "files": len(names), "manifest": meta}
    except Exception as exc:
        return {"ok": False, "reason": f"corrupt:{type(exc).__name__}"}


def restore_app_backup(
    zip_path: Path,
    *,
    dest_data: Optional[Path] = None,
    restore_env: bool = False,
) -> dict[str, Any]:
    """
    Restore data/ from a validated backup zip into dest_data (default DATA_DIR).
    Never prints secret contents. restore_env defaults False.
    """
    check = validate_backup_archive(zip_path)
    if not check.get("ok"):
        return {"ok": False, "reason": check.get("reason")}

    target = Path(dest_data) if dest_data else Path(DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    restored = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            if name.startswith("data/"):
                rel = name[len("data/") :]
                out = target / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored += 1
            elif restore_env and name == ".env":
                out = ROOT / ".env"
                with zf.open(info) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored += 1
    return {"ok": True, "restored_files": restored, "data_dir": str(target)}
