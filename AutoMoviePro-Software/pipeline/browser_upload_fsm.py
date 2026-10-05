"""Browser upload state machine (T010 foundation) — click ≠ success."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Set


UPLOAD_STATES: Set[str] = {
    "STARTING",
    "SESSION_READY",
    "AUTHENTICATED",
    "NAVIGATING",
    "PAGE_READY",
    "FILE_SELECTED",
    "PROCESSING",
    "DETAILS",
    "METADATA_FILLED",
    "CHECKS",
    "PUBLISH",
    "PUBLISHED",
    "VERIFIED",
    "CAPTCHA_REQUIRED",
    "FAILED",
    "CANCELLED",
}

ALLOWED: Dict[str, Set[str]] = {
    "STARTING": {"SESSION_READY", "FAILED", "CANCELLED"},
    "SESSION_READY": {"AUTHENTICATED", "FAILED", "CANCELLED"},
    "AUTHENTICATED": {"NAVIGATING", "FAILED", "CANCELLED"},
    "NAVIGATING": {"PAGE_READY", "FAILED", "CANCELLED"},
    "PAGE_READY": {"FILE_SELECTED", "FAILED", "CANCELLED"},
    "FILE_SELECTED": {"PROCESSING", "FAILED", "CANCELLED"},
    "PROCESSING": {"DETAILS", "PROCESSING", "FAILED", "CANCELLED"},
    "DETAILS": {"METADATA_FILLED", "FAILED", "CANCELLED"},
    "METADATA_FILLED": {"CHECKS", "FAILED", "CANCELLED"},
    "CHECKS": {"PUBLISH", "FAILED", "CANCELLED"},
    "PUBLISH": {"PUBLISHED", "CAPTCHA_REQUIRED", "FAILED", "CANCELLED"},
    "PUBLISHED": {"VERIFIED", "FAILED"},
    "VERIFIED": set(),
    "CAPTCHA_REQUIRED": {"PUBLISH", "CANCELLED"},  # after human unlock — one incident
    "FAILED": {"STARTING", "CANCELLED"},
    "CANCELLED": set(),
}


class InvalidBrowserTransition(ValueError):
    pass


@dataclass
class BrowserUploadFSM:
    platform: str = "youtube"
    state: str = "STARTING"
    history: List[Dict[str, Any]] = field(default_factory=list)
    captcha_incident_open: bool = False
    dry_run: bool = False

    def transition(self, to_state: str, *, reason: str = "", verified: bool = False) -> str:
        to_state = (to_state or "").upper()
        cur = (self.state or "").upper()
        if to_state == cur:
            return cur
        if to_state not in ALLOWED.get(cur, set()):
            raise InvalidBrowserTransition(f"invalid_browser_transition:{cur}->{to_state}")
        # Publish requires verification markers in real path; dry_run may simulate
        if to_state == "PUBLISHED" and not self.dry_run and not verified:
            raise InvalidBrowserTransition("publish_without_verification")
        if to_state == "CAPTCHA_REQUIRED":
            if self.captcha_incident_open:
                raise InvalidBrowserTransition("duplicate_captcha_incident")
            self.captcha_incident_open = True
        if to_state == "PUBLISH" and self.captcha_incident_open:
            self.captcha_incident_open = False
        self.history.append(
            {
                "from": cur,
                "to": to_state,
                "reason": reason,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.state = to_state
        return self.state
