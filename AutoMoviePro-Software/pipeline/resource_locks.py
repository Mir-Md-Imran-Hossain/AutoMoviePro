"""File-backed resource locks (protocol §93–94) — not in-memory booleans."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import DATA_DIR

LOCK_ROOT = Path(DATA_DIR) / "locks"


class LockError(RuntimeError):
    pass


def _path(resource: str, key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{resource}_{key}")
    return LOCK_ROOT / f"{safe}.lock.json"


def acquire(
    resource: str,
    key: str,
    *,
    owner: str,
    ttl_sec: float = 600.0,
    block: bool = False,
    wait_sec: float = 30.0,
) -> Dict[str, Any]:
    """
    resources: browser | channel | generation | upload | database | provider
    """
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    path = _path(resource, key)
    deadline = time.time() + (wait_sec if block else 0)
    while True:
        now = time.time()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                exp = float(data.get("expires_at") or 0)
                if exp > now and str(data.get("owner") or "") != owner:
                    if block and now < deadline:
                        time.sleep(0.25)
                        continue
                    raise LockError(f"lock_held:{resource}:{key}:owner={data.get('owner')}")
            except LockError:
                raise
            except Exception:
                pass
        payload = {
            "resource": resource,
            "key": key,
            "owner": owner,
            "acquired_at": now,
            "expires_at": now + float(ttl_sec),
            "pid": os.getpid(),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return payload


def release(resource: str, key: str, *, owner: str) -> bool:
    path = _path(resource, key)
    if not path.exists():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if str(data.get("owner") or "") not in ("", owner):
            return False
        path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def is_held(resource: str, key: str) -> bool:
    path = _path(resource, key)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return float(data.get("expires_at") or 0) > time.time()
    except Exception:
        return False
