"""Anti-misuse guard for media generation API calls.

Ensures:
  - at most ONE paid create per (provider, fingerprint) while claim is live
  - no model×key combinatorial fan-out
  - circuit-break after hard failures (auth/403/credits)
  - claims/circuits persist atomically (survive process restart)
  - failed creates can release_claim so legitimate retries work
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

_lock = threading.RLock()
# key -> claimed_at epoch
_created: Dict[str, float] = {}
_circuit_open_until: Dict[str, float] = {}
_shot_providers_tried: Dict[str, Set[str]] = {}
_loaded = False
_load_path: Optional[str] = None


def _claim_ttl_sec() -> float:
    raw = (os.environ.get("AMP_MEDIA_GUARD_CLAIM_TTL_SEC") or "").strip()
    if raw:
        try:
            return max(60.0, float(raw))
        except ValueError:
            pass
    return 7 * 24 * 3600.0  # 7 days


def _state_path() -> Path:
    raw = (os.environ.get("AMP_MEDIA_GUARD_STATE") or "").strip()
    if raw:
        return Path(raw)
    try:
        from app.config import software_env_paths

        roots = software_env_paths()
        if roots:
            base = Path(roots[0]).parent
            return base / "_quota_state" / "media_call_guard.json"
    except Exception:
        pass
    return Path.cwd() / "_quota_state" / "media_call_guard.json"


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def reset_runtime_state(*, reload: bool = False) -> None:
    """Test / ops helper — clears in-memory guard (optionally force disk reload)."""
    global _loaded, _load_path
    with _lock:
        _created.clear()
        _circuit_open_until.clear()
        _shot_providers_tried.clear()
        _loaded = False
        _load_path = None
        if reload:
            _ensure_loaded()


def _ensure_loaded() -> None:
    global _loaded, _load_path
    path = _state_path()
    path_s = str(path.resolve()) if path else ""
    # Reload if env path changed (tests)
    if _loaded and _load_path == path_s:
        return
    _created.clear()
    _circuit_open_until.clear()
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            now = time.time()
            ttl = _claim_ttl_sec()
            created = data.get("created") or {}
            if isinstance(created, list):
                # Legacy list form
                for k in created:
                    _created[str(k)] = now
            elif isinstance(created, dict):
                for k, ts in created.items():
                    try:
                        t = float(ts)
                    except (TypeError, ValueError):
                        t = now
                    if (now - t) <= ttl:
                        _created[str(k)] = t
            for prov, until in (data.get("circuits") or {}).items():
                try:
                    u = float(until)
                except (TypeError, ValueError):
                    continue
                if u > now:
                    _circuit_open_until[str(prov)] = u
    except Exception as exc:
        logger.warning("media guard load failed: %s", exc)
    _loaded = True
    _load_path = path_s


def _persist() -> None:
    path = _state_path()
    try:
        now = time.time()
        ttl = _claim_ttl_sec()
        # Drop expired claims
        alive = {k: v for k, v in _created.items() if (now - float(v)) <= ttl}
        circuits = {k: v for k, v in _circuit_open_until.items() if v > now}
        # Bound size (keep newest)
        if len(alive) > 5000:
            items = sorted(alive.items(), key=lambda kv: kv[1])[-5000:]
            alive = dict(items)
        payload = {
            "updated_at": now,
            "created": alive,
            "circuits": circuits,
            "claim_ttl_sec": ttl,
        }
        _atomic_write(path, payload)
        _created.clear()
        _created.update(alive)
        _circuit_open_until.clear()
        _circuit_open_until.update(circuits)
    except Exception as exc:
        logger.warning("media guard persist failed: %s", exc)


def _fp(*parts: str) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:20]


def begin_shot(shot_key: str) -> None:
    with _lock:
        _ensure_loaded()
        _shot_providers_tried[shot_key] = set()


def provider_already_tried(shot_key: str, provider: str) -> bool:
    with _lock:
        return provider in (_shot_providers_tried.get(shot_key) or set())


def mark_provider_tried(shot_key: str, provider: str) -> None:
    with _lock:
        _shot_providers_tried.setdefault(shot_key, set()).add(provider)


def claim_create(provider: str, fingerprint: str) -> bool:
    """Return True if this create is allowed (first claim wins)."""
    key = f"{provider}:{fingerprint}"
    with _lock:
        _ensure_loaded()
        until = _circuit_open_until.get(provider, 0.0)
        if until > time.time():
            logger.warning(
                "media guard: circuit open for %s (%.0fs left) — skip create",
                provider,
                until - time.time(),
            )
            return False
        now = time.time()
        ttl = _claim_ttl_sec()
        prev = _created.get(key)
        if prev is not None and (now - float(prev)) <= ttl:
            logger.warning("media guard: duplicate create blocked %s", key)
            return False
        _created[key] = now
        _persist()
        return True


def release_claim(provider: str, fingerprint: str, *, reason: str = "") -> None:
    """Allow retry after a failed create (does not burn fingerprint forever)."""
    key = f"{provider}:{fingerprint}"
    with _lock:
        _ensure_loaded()
        if key in _created:
            _created.pop(key, None)
            _persist()
            logger.info("media guard: claim released %s (%s)", key, reason[:80])


def open_circuit(provider: str, seconds: float = 900.0, reason: str = "") -> None:
    with _lock:
        _ensure_loaded()
        _circuit_open_until[provider] = max(
            _circuit_open_until.get(provider, 0.0), time.time() + seconds
        )
        _persist()
    logger.warning(
        "media guard: circuit OPEN %s for %.0fs (%s)", provider, seconds, reason[:120]
    )


def is_circuit_open(provider: str) -> bool:
    with _lock:
        _ensure_loaded()
        return _circuit_open_until.get(provider, 0.0) > time.time()


def prompt_fingerprint(prompt: str, *, aspect: str = "", duration: float = 0.0) -> str:
    return _fp(prompt[:400], aspect, f"{float(duration):.1f}")
