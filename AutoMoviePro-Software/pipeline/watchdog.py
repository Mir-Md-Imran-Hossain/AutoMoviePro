"""Watchdog heartbeat — detect HANG when deadline passes without beat."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class Watchdog:
    def __init__(
        self,
        name: str,
        *,
        deadline_sec: float = 300.0,
        work_dir: Optional[Path] = None,
    ):
        self.name = name
        self.deadline_sec = float(deadline_sec)
        self.work_dir = Path(work_dir) if work_dir else None
        self.started_at = time.time()
        self.last_heartbeat = self.started_at
        self.attempt = 0
        self.state = "RUNNING"
        self._persist()

    def _path(self) -> Optional[Path]:
        if not self.work_dir:
            return None
        return self.work_dir / f"WATCHDOG_{self.name}.json"

    def _persist(self) -> None:
        p = self._path()
        if not p:
            return
        try:
            p.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        except Exception:
            pass

    def heartbeat(self, *, state: str = "") -> None:
        self.last_heartbeat = time.time()
        if state:
            self.state = state
        self._persist()

    def check(self) -> Dict[str, Any]:
        now = time.time()
        silent = now - self.last_heartbeat
        hung = silent > self.deadline_sec
        if hung:
            self.state = "HANG_DETECTED"
        return {
            "name": self.name,
            "hung": hung,
            "silent_sec": round(silent, 1),
            "deadline_sec": self.deadline_sec,
            "state": self.state,
            "attempt": self.attempt,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "deadline_sec": self.deadline_sec,
            "attempt": self.attempt,
            "state": self.state,
        }
