"""Minimal filesystem / thread lock helpers for BUILD-03 idempotency (H1).

NOT a second lock manager / framework — thin adapters used by existing stores.
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


_REGISTRY_LOCK = threading.Lock()
_THREAD_LOCKS: dict[str, threading.Lock] = {}


def normalize_lock_key(path: Path | str) -> str:
    """Stable lock identity across Windows resolve() variants (\\\\?\\ prefix)."""
    resolved = str(Path(path).resolve())
    if resolved.startswith("\\\\?\\"):
        resolved = resolved[4:]
    elif resolved.startswith("//?/"):
        resolved = resolved[4:]
    if os.name == "nt":
        resolved = resolved.replace("/", "\\").lower()
    return resolved


def thread_lock_for(path: Path | str) -> threading.Lock:
    key = normalize_lock_key(path)
    with _REGISTRY_LOCK:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


class _ProcessFileLock:
    """Advisory exclusive lock on a sibling .lock file (process-safe)."""

    def __init__(self, target: Path):
        self.target = Path(target)
        self.lock_path = self.target.with_suffix(self.target.suffix + ".lock")
        self._fh: Optional[object] = None

    def acquire(self, *, timeout_sec: float = 60.0) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + timeout_sec
        while True:
            fh = open(self.lock_path, "a+b")
            try:
                if os.name == "nt":
                    import msvcrt

                    fh.seek(0)
                    if fh.read(1) == b"":
                        fh.write(b"\0")
                        fh.flush()
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fh = fh
                return
            except (OSError, BlockingIOError):
                try:
                    fh.close()
                except Exception:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"process lock timeout: {self.lock_path}")
                time.sleep(0.01)

    def release(self) -> None:
        fh = self._fh
        self._fh = None
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass


@contextmanager
def exclusive_path_lock(path: Path | str, *, timeout_sec: float = 60.0) -> Iterator[None]:
    """Thread lock + process advisory lock for one critical section."""
    target = Path(path)
    tlock = thread_lock_for(target)
    plock = _ProcessFileLock(target)
    with tlock:
        plock.acquire(timeout_sec=timeout_sec)
        try:
            yield
        finally:
            plock.release()
