"""Comment + Message formal state machines (protocol §85–91)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Set


COMMENT_ALLOWED: Dict[str, Set[str]] = {
    "RECEIVED": {"CLASSIFIED", "SPAM_DROP"},
    "CLASSIFIED": {"FACT_LOOKUP", "DRAFT", "ESCALATE"},
    "FACT_LOOKUP": {"DRAFT", "ESCALATE"},
    "DRAFT": {"VALIDATE"},
    "VALIDATE": {"SEND", "DRAFT"},
    "SEND": {"VERIFY", "FAILED"},
    "VERIFY": {"VERIFIED", "FAILED"},
    "VERIFIED": set(),
    "SPAM_DROP": set(),
    "ESCALATE": set(),
    "FAILED": {"DRAFT", "RECEIVED"},
}

MESSAGE_ALLOWED: Dict[str, Set[str]] = {
    "RECEIVED": {"CLASSIFIED"},
    "CLASSIFIED": {"NEEDS_REPLY", "ESCALATE", "IGNORE"},
    "NEEDS_REPLY": {"DRAFTED"},
    "DRAFTED": {"VALIDATED"},
    "VALIDATED": {"SENT", "DRAFTED"},
    "SENT": {"VERIFIED", "FAILED"},
    "VERIFIED": set(),
    "ESCALATE": set(),
    "IGNORE": set(),
    "FAILED": {"NEEDS_REPLY"},
}


class InvalidCommTransition(ValueError):
    pass


@dataclass
class CommentFSM:
    comment_id: str = ""
    state: str = "RECEIVED"
    history: List[Dict[str, Any]] = field(default_factory=list)
    category: str = "UNKNOWN"

    def transition(self, to_state: str, *, reason: str = "") -> str:
        to_state = to_state.upper()
        cur = self.state.upper()
        if to_state == cur:
            return cur
        if to_state not in COMMENT_ALLOWED.get(cur, set()):
            raise InvalidCommTransition(f"comment:{cur}->{to_state}")
        self.history.append({"from": cur, "to": to_state, "reason": reason, "at": datetime.now(timezone.utc).isoformat()})
        self.state = to_state
        return self.state


@dataclass
class MessageFSM:
    message_id: str = ""
    state: str = "RECEIVED"
    history: List[Dict[str, Any]] = field(default_factory=list)
    sensitive: bool = False

    def transition(self, to_state: str, *, reason: str = "") -> str:
        to_state = to_state.upper()
        cur = self.state.upper()
        if to_state == cur:
            return cur
        if self.sensitive and to_state in ("SENT", "DRAFTED") and to_state != "ESCALATE":
            # force escalate path for payment/legal/medical
            if to_state != "ESCALATE" and "ESCALATE" in MESSAGE_ALLOWED.get(cur, set()):
                raise InvalidCommTransition("sensitive_must_escalate")
        if to_state not in MESSAGE_ALLOWED.get(cur, set()):
            raise InvalidCommTransition(f"message:{cur}->{to_state}")
        self.history.append({"from": cur, "to": to_state, "reason": reason, "at": datetime.now(timezone.utc).isoformat()})
        self.state = to_state
        return self.state


def is_sensitive_message(text: str) -> bool:
    low = (text or "").lower()
    return any(
        x in low
        for x in (
            "refund",
            "payment",
            "lawyer",
            "legal",
            "medical",
            "suicide",
            "bank transfer",
            "otp",
        )
    )
