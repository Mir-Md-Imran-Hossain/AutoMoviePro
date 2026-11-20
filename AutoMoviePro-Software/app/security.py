"""
AutoMovie Pro - Security & Request Authentication Module
Implements S-03 hardening:
- Dynamic cryptographically secure per-run app token
- HttpOnly + SameSite=Strict session cookie for HTML5 media and downloads
- Host header and Origin validation
- Subprocess and companion widget token handoff
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

APP_TOKEN_ENV_VAR = "AUTO_MOVIE_APP_TOKEN"
COOKIE_NAME = "amp_session_token"
TOKEN_FILE = DATA_DIR / ".app_token"

_CACHED_TOKEN: Optional[str] = None

ALLOWED_HOSTS = {
    "127.0.0.1:8787",
    "localhost:8787",
    "127.0.0.1",
    "localhost",
    "testserver",
}

# Allow private network origins for mobile Wi-Fi preflight if explicitly routed
ALLOWED_ORIGIN_PATTERN = re.compile(
    r"^https?://(127\.0\.0\.1|localhost|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|testserver)(:\d+)?$",
    re.IGNORECASE,
)


def get_or_create_app_token() -> str:
    """Retrieve or generate per-session cryptographic authentication token."""
    global _CACHED_TOKEN
    if _CACHED_TOKEN:
        return _CACHED_TOKEN

    token = os.environ.get(APP_TOKEN_ENV_VAR, "").strip()
    if token:
        _CACHED_TOKEN = token
        return _CACHED_TOKEN

    try:
        if TOKEN_FILE.exists():
            saved = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if len(saved) >= 32:
                _CACHED_TOKEN = saved
                os.environ[APP_TOKEN_ENV_VAR] = _CACHED_TOKEN
                return _CACHED_TOKEN
    except Exception:
        pass

    token = secrets.token_hex(32)
    _CACHED_TOKEN = token
    os.environ[APP_TOKEN_ENV_VAR] = token

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token, encoding="utf-8")
        # Restrict permissions on Windows where supported
        if os.name == "nt":
            try:
                import subprocess
                subprocess.run(
                    ["icacls", str(TOKEN_FILE), "/inheritance:r", f"/grant:r", f"{os.getlogin()}:(R,W)"],
                    capture_output=True,
                    timeout=3,
                )
            except Exception:
                pass
        else:
            TOKEN_FILE.chmod(0o600)
    except Exception:
        pass

    return _CACHED_TOKEN


def verify_app_token(token: Optional[str]) -> bool:
    """Constant-time verification of app security token."""
    if not token or not isinstance(token, str):
        return False
    expected = get_or_create_app_token()
    return hmac.compare_digest(token.strip(), expected)


def is_allowed_host(host_header: Optional[str]) -> bool:
    """Validate incoming HTTP Host header against allowed local targets."""
    if not host_header:
        return False
    h = host_header.strip().lower()
    return h in ALLOWED_HOSTS


def is_allowed_origin(origin: Optional[str]) -> bool:
    """Validate incoming Origin or Referer header against authorized origins."""
    if not origin:
        return True
    o = origin.strip().lower()
    if o in ("null", "file://"):
        return True
    return bool(ALLOWED_ORIGIN_PATTERN.match(o))


def is_allowed_referer(referer: Optional[str]) -> bool:
    """Validate incoming Referer against authorized local origins."""
    if not referer:
        return True
    try:
        parsed = urlparse(referer)
        hostname = (parsed.hostname or "").lower()
        if hostname in ("127.0.0.1", "localhost", "testserver"):
            return True
        if hostname.startswith("192.168.") or hostname.startswith("10."):
            return True
        return False
    except Exception:
        return False
