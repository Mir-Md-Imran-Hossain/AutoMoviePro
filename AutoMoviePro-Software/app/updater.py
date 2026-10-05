"""
Safe in-place updater.

- Checks website /api/update-check.php
- Downloads new installer to a temp folder (never into data/)
- Verifies sha256 when provided
- Launches installer then exits app
- Does NOT touch data/, .env, local.db, session_vault — those live under DATA_DIR
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import DATA_DIR, settings
from app.version import APP_VERSION

logger = logging.getLogger(__name__)

STATE_PATH = DATA_DIR / "update_state.json"
_lock = threading.Lock()
_last_check: Dict[str, Any] = {}


def _load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(st: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def current_version() -> str:
    return APP_VERSION


def last_check_result() -> Dict[str, Any]:
    with _lock:
        return dict(_last_check) if _last_check else _load_state().get("last_payload") or {}


def check_for_update(token: str = "", api_base: str = "") -> Dict[str, Any]:
    """Poll website; store result for UI + enforcement."""
    global _last_check
    from app.api_client import LicenseClient

    base = (api_base or settings.api_base_url or "").rstrip("/")
    client = LicenseClient(base_url=base, token=token or None)
    try:
        payload = client.check_update(APP_VERSION)
    except Exception as exc:
        payload = {
            "ok": False,
            "error": str(exc)[:200],
            "client_version": APP_VERSION,
            "update_available": False,
        }
    payload = dict(payload or {})
    payload.setdefault("client_version", APP_VERSION)
    payload["checked_at"] = datetime.now(timezone.utc).isoformat()

    st = _load_state()
    st["last_payload"] = payload
    if payload.get("update_available") and payload.get("force_update"):
        # Remember first time we saw this forced version (for local countdown)
        key = str(payload.get("latest_version") or "")
        seen = st.get("forced_seen") or {}
        if key and key not in seen:
            seen[key] = payload.get("force_deadline_utc") or datetime.now(timezone.utc).isoformat()
            st["forced_seen"] = seen
    _save_state(st)
    with _lock:
        _last_check = payload
    return payload


def update_blocks_generation() -> bool:
    """True when forced update deadline has passed."""
    p = last_check_result()
    if not p.get("update_available") or not p.get("force_update"):
        return False
    if p.get("past_deadline"):
        return True
    deadline = str(p.get("force_deadline_utc") or "")
    if not deadline:
        return False
    try:
        # handle Z
        ds = deadline.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ds)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= dt
    except Exception:
        return False


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_and_apply_update(*, token: str = "", api_base: str = "") -> Dict[str, Any]:
    """
    Download installer and launch it. Caller should exit the app afterwards.
    Preserves DATA_DIR entirely (login, channels, sessions).
    """
    import httpx

    payload = check_for_update(token=token, api_base=api_base)
    if not payload.get("ok") and payload.get("error"):
        return {"ok": False, "error": payload.get("error")}
    if not payload.get("update_available"):
        return {"ok": False, "error": "already_up_to_date", "payload": payload}

    url = str(payload.get("download_url") or "").strip()
    if not url:
        return {"ok": False, "error": "missing_download_url"}

    expect_sha = (payload.get("sha256") or "").strip().lower()
    dest_dir = Path(tempfile.gettempdir()) / "AutoMovieProUpdates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"AutoMoviePro-Setup-{payload.get('latest_version')}.exe"

    try:
        from pipeline.live_activity import log as live_log

        live_log("lab", f"Downloading update {payload.get('latest_version')}…", force_new=True)
    except Exception:
        pass

    with httpx.Client(timeout=600.0, follow_redirects=True) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with dest.open("wb") as out:
                for chunk in r.iter_bytes():
                    out.write(chunk)

    if dest.stat().st_size < 10000:
        return {"ok": False, "error": "download_too_small"}

    if expect_sha:
        got = _sha256_file(dest).lower()
        if got != expect_sha:
            try:
                dest.unlink()
            except OSError:
                pass
            return {"ok": False, "error": f"sha256_mismatch:{got[:12]}"}

    # Launch installer; Inno/NSIS should upgrade files without wiping AppData/DATA_DIR
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(
                [str(dest)],
                cwd=str(dest_dir),
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        else:
            subprocess.Popen([str(dest)], cwd=str(dest_dir), start_new_session=True)
    except Exception as exc:
        return {"ok": False, "error": f"launch_failed:{exc}"}

    st = _load_state()
    st["last_apply"] = {
        "version": payload.get("latest_version"),
        "at": datetime.now(timezone.utc).isoformat(),
        "installer": str(dest),
    }
    _save_state(st)
    return {
        "ok": True,
        "launched": True,
        "installer": str(dest),
        "latest_version": payload.get("latest_version"),
        "preserves_data": True,
        "preserves_login": True,
        "exit_recommended": True,
    }
