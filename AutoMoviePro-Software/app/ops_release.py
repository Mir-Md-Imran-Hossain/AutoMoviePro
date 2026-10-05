"""Release manifest generation and validation (H5) — uses release_identity only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.config import ROOT
from app.release_identity import RELEASE_VERSION, get_release_identity


MANIFEST_DIR = ROOT / "release"
MANIFEST_NAME = "manifest.json"

FORBIDDEN_MANIFEST_KEYS = {
    "password",
    "api_key",
    "apikey",
    "token",
    "secret",
    "authorization",
    "bearer",
    "credentials",
}


def default_manifest_path() -> Path:
    return MANIFEST_DIR / MANIFEST_NAME


def build_release_manifest(*, build_id: Optional[str] = None) -> dict[str, Any]:
    identity = get_release_identity(build_id=build_id, include_media=True)
    return {
        "schema": "amp004_h5_release_manifest_v1",
        "app_name": identity.get("app_name"),
        "release_version": identity.get("release_version"),
        "build_id": identity.get("build_id"),
        "build_timestamp": identity.get("build_timestamp"),
        "supported_os": ["windows"],
        "supported_deployment_mode": "windows_local_source_venv",
        "pyinstaller_status": "PARTIAL_NOT_CERTIFIED",
        "docker_linux_status": "UNSUPPORTED_NOT_CERTIFIED",
        "python_version_requirement": ">=3.11",
        "python_runtime": identity.get("python_version"),
        "platform": identity.get("platform"),
        "dependency_authority": "requirements.txt (pinned) + requirements-dev.txt",
        "dependency_reproducibility": "PARTIAL",
        "ffmpeg_available": identity.get("ffmpeg_available"),
        "ffprobe_available": identity.get("ffprobe_available"),
        "ffmpeg_source": identity.get("ffmpeg_source"),
        "ffprobe_source": identity.get("ffprobe_source"),
        "ffmpeg_version": identity.get("ffmpeg_version"),
        "ffprobe_version": identity.get("ffprobe_version"),
        "package_type": "source_tree",
        "checkpoint": "AMP004-H5-RELEASE-OPERATIONAL-READINESS",
        "certification_status": "H5",
    }


def _contains_forbidden(obj: Any, path: str = "") -> list[str]:
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if any(f in lk for f in FORBIDDEN_MANIFEST_KEYS):
                bad.append(path + "/" + str(k))
            bad.extend(_contains_forbidden(v, path + "/" + str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad.extend(_contains_forbidden(v, f"{path}[{i}]"))
    return bad


def validate_release_manifest(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"ok": False, "reason": "not_object"}
    if data.get("schema") != "amp004_h5_release_manifest_v1":
        return {"ok": False, "reason": "bad_schema"}
    if data.get("release_version") != RELEASE_VERSION:
        return {"ok": False, "reason": "version_mismatch_vs_authority"}
    required = ("app_name", "release_version", "build_id", "supported_deployment_mode")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return {"ok": False, "reason": "missing:" + ",".join(missing)}
    forbidden = _contains_forbidden(data)
    if forbidden:
        return {"ok": False, "reason": "forbidden_keys", "keys": forbidden[:20]}
    if data.get("docker_linux_status") not in (
        "UNSUPPORTED_NOT_CERTIFIED",
        "UNSUPPORTED",
        "NOT_CERTIFIED",
    ):
        # honesty gate — do not allow false PASS for docker
        if str(data.get("docker_linux_status") or "").upper() in {"SUPPORTED", "PASS"}:
            return {"ok": False, "reason": "false_docker_support"}
    return {"ok": True}


def write_release_manifest(path: Optional[Path] = None) -> dict[str, Any]:
    dest = Path(path) if path else default_manifest_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = build_release_manifest()
    check = validate_release_manifest(data)
    if not check.get("ok"):
        return {"ok": False, "reason": check.get("reason"), "path": str(dest)}
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(dest), "release_version": data.get("release_version")}


def inventory_release_package(root: Optional[Path] = None) -> dict[str, Any]:
    """Inspect supported source release tree for include/exclude safety."""
    base = Path(root) if root else ROOT
    required_present = {
        "app": (base / "app").is_dir(),
        "pipeline": (base / "pipeline").is_dir(),
        "requirements.txt": (base / "requirements.txt").is_file(),
        "START.bat": (base / "START.bat").is_file(),
        ".env.example": (base / ".env.example").is_file(),
        "release_identity": (base / "app" / "release_identity.py").is_file(),
    }
    forbidden_in_release = {
        ".env_committed": (base / ".env").is_file(),  # may exist locally — flag only
    }
    ffmpeg_tree = False
    for dist in base.glob("ffmpeg-*"):
        if not dist.is_dir():
            continue
        if any(dist.rglob("ffmpeg.exe")) or any(dist.rglob("ffmpeg")):
            ffmpeg_tree = True
            break
    tools = base / "tools" / "ffmpeg"
    if tools.is_dir() and (any(tools.rglob("ffmpeg.exe")) or any(tools.rglob("ffmpeg"))):
        ffmpeg_tree = True
    return {
        "ok": all(required_present.values()) and ffmpeg_tree,
        "required": required_present,
        "ffmpeg_bundled_tree": bool(ffmpeg_tree),
        "local_env_present": bool(forbidden_in_release[".env_committed"]),
        "note": ".env may exist locally; must not ship in distribution archives",
        "pyinstaller_status": "PARTIAL_NOT_CERTIFIED",
        "docker_linux_status": "UNSUPPORTED_NOT_CERTIFIED",
    }
