"""LOOP_DETECTED + STALLED detectors (protocol §06, §147)."""
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional


class LoopDetector:
    def __init__(self, *, window: int = 8, repeat_threshold: int = 3):
        self.window = window
        self.repeat_threshold = repeat_threshold
        self._events: Deque[str] = deque(maxlen=window)

    def observe(self, signature: str) -> Dict[str, Any]:
        sig = (signature or "").strip() or "unknown"
        self._events.append(sig)
        count = sum(1 for e in self._events if e == sig)
        # A→B→A→B pattern
        osc = False
        if len(self._events) >= 4:
            a, b = self._events[-2], self._events[-1]
            tail = list(self._events)[-4:]
            osc = tail == [tail[0], tail[1], tail[0], tail[1]] and tail[0] != tail[1]
        loop = count >= self.repeat_threshold or osc
        return {
            "signature": sig,
            "count_in_window": count,
            "oscillation": osc,
            "state": "LOOP_DETECTED" if loop else "OK",
            "loop_detected": loop,
        }


def classify_watchdog_state(check: Dict[str, Any]) -> str:
    """Map watchdog check → HANG_DETECTED | STALLED | OK."""
    if check.get("hung"):
        # No heartbeat past deadline
        silent = float(check.get("silent_sec") or 0)
        deadline = float(check.get("deadline_sec") or 1)
        if silent > deadline * 2:
            return "HANG_DETECTED"
        return "STALLED"
    return str(check.get("state") or "OK")
