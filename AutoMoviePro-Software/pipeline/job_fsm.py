"""Formal job state machine — invalid transitions rejected."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


STATES: Set[str] = {
    "CREATED",
    "PLANNING",
    "SCRIPTING",
    "GENERATING",
    "VERIFYING",
    "ASSEMBLING",
    "READY",
    "UPLOADING",
    "PUBLISHED",
    "VERIFIED",
    "FAILED",
    "BLOCKED",
    "CANCELLED",
}

ALLOWED: Dict[str, Set[str]] = {
    "CREATED": {"PLANNING", "CANCELLED"},
    "PLANNING": {"SCRIPTING", "FAILED", "BLOCKED", "CANCELLED"},
    "SCRIPTING": {"GENERATING", "FAILED", "CANCELLED"},
    "GENERATING": {"VERIFYING", "FAILED", "BLOCKED", "CANCELLED"},
    "VERIFYING": {"ASSEMBLING", "GENERATING", "FAILED", "CANCELLED"},
    "ASSEMBLING": {"READY", "FAILED", "CANCELLED"},
    "READY": {"UPLOADING", "FAILED", "CANCELLED"},
    "UPLOADING": {"PUBLISHED", "FAILED", "BLOCKED", "CANCELLED"},
    "PUBLISHED": {"VERIFIED", "FAILED"},
    "VERIFIED": set(),
    "FAILED": {"PLANNING", "CANCELLED"},
    "BLOCKED": {"UPLOADING", "PLANNING", "CANCELLED"},
    "CANCELLED": set(),
}

# Map informal live_lab phases → formal states
PHASE_ALIASES = {
    "starting": "CREATED",
    "generate_short": "GENERATING",
    "generate_long": "GENERATING",
    "scene": "GENERATING",
    "localize": "ASSEMBLING",
    "package": "ASSEMBLING",
    "upload": "UPLOADING",
    "waiting_comments": "PUBLISHED",
    "comment_check": "VERIFIED",
    "failed": "FAILED",
    "cancelled": "CANCELLED",
    "complete": "VERIFIED",
    "ready": "READY",
}


class InvalidTransition(ValueError):
    pass


def normalize_state(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "CREATED"
    up = s.upper()
    if up in STATES:
        return up
    return PHASE_ALIASES.get(s.lower(), up if up in STATES else "CREATED")


@dataclass
class JobFSM:
    job_id: str = ""
    state: str = "CREATED"
    history: List[Dict[str, Any]] = field(default_factory=list)
    attempt: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def can_transition(self, to_state: str) -> bool:
        to_state = normalize_state(to_state)
        cur = normalize_state(self.state)
        return to_state in ALLOWED.get(cur, set())

    def transition(self, to_state: str, *, reason: str = "", force: bool = False) -> str:
        to_state = normalize_state(to_state)
        cur = normalize_state(self.state)
        if to_state == cur:
            return cur
        if not force and to_state not in ALLOWED.get(cur, set()):
            raise InvalidTransition(f"invalid_transition:{cur}->{to_state}")
        self.history.append(
            {
                "from": cur,
                "to": to_state,
                "reason": reason,
                "at": datetime.now(timezone.utc).isoformat(),
                "forced": bool(force),
            }
        )
        self.state = to_state
        if to_state in ("PLANNING", "GENERATING"):
            self.attempt += 1
        return self.state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "attempt": self.attempt,
            "history": list(self.history),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobFSM":
        fsm = cls(
            job_id=str(data.get("job_id") or ""),
            state=normalize_state(str(data.get("state") or "CREATED")),
            attempt=int(data.get("attempt") or 0),
            meta=dict(data.get("meta") or {}),
        )
        fsm.history = list(data.get("history") or [])
        return fsm


def assert_transition(from_state: str, to_state: str) -> Tuple[bool, str]:
    a, b = normalize_state(from_state), normalize_state(to_state)
    if a == b:
        return True, "noop"
    if b in ALLOWED.get(a, set()):
        return True, f"{a}->{b}"
    return False, f"invalid_transition:{a}->{b}"
