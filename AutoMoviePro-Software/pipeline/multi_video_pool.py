"""
Industrial Multi-Platform AI Video Pool Manager
===============================================
Manages up to 5 customer Gmail accounts across 5 top-tier video generation platforms:
1. Dreamina (CapCut / ByteDance - Seedance)
2. Kling AI (klingai.com)
3. PixVerse (pixverse.ai)
4. Leonardo AI (leonardo.ai)
5. Muse AI (muse.ai)

Features:
- Total capacity: 25 isolated accounts (5 platforms × 5 accounts each)
- Human-like stealth browsing integration via pipeline/stealth_browser.py
- Automatic persistent cookie & session storage in data/browser_sessions/
- Automatic credit tracking, intelligent round-robin rotation & fallback
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SESSION_ROOT = Path("data/browser_sessions")
SESSION_ROOT.mkdir(parents=True, exist_ok=True)

SUPPORTED_PLATFORMS = ("dreamina", "kling", "pixverse", "leonardo", "muse")

DEFAULT_DAILY_CREDITS = {
    "dreamina": 120,   # ~15-20 clips across 5 accounts
    "kling": 66,       # ~12-15 clips across 5 accounts
    "pixverse": 60,    # ~10-12 clips across 5 accounts
    "leonardo": 150,   # ~30 motion clips across 5 accounts
    "muse": 50,        # ~10-15 clips across 5 accounts
}


def _provider_dir(platform: str) -> Path:
    p = SESSION_ROOT / platform.lower().strip()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _accounts_file(platform: str) -> Path:
    return _provider_dir(platform) / "accounts.json"


def list_platform_accounts(platform: str) -> List[Dict[str, Any]]:
    """List all configured accounts for a specific platform (up to 5)."""
    acc_file = _accounts_file(platform)
    if not acc_file.exists():
        return []
    try:
        return json.loads(acc_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read accounts for %s: %s", platform, exc)
        return []


def save_platform_accounts(platform: str, accounts: List[Dict[str, Any]]) -> None:
    """Save accounts for a specific platform."""
    acc_file = _accounts_file(platform)
    acc_file.write_text(json.dumps(accounts, indent=2, ensure_ascii=False), encoding="utf-8")


def register_account(platform: str, email: str, label: str = "") -> Dict[str, Any]:
    """Register or update an account in the platform's pool (max 5 accounts)."""
    plat = platform.lower().strip()
    if plat not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported platform {plat}. Supported: {SUPPORTED_PLATFORMS}")

    accounts = list_platform_accounts(plat)
    email_clean = email.strip().lower()

    for acc in accounts:
        if acc.get("email") == email_clean:
            acc["updated_at"] = time.time()
            if label:
                acc["label"] = label
            save_platform_accounts(plat, accounts)
            return acc

    if len(accounts) >= 5:
        accounts.sort(key=lambda x: x.get("updated_at", 0))
        removed = accounts.pop(0)
        logger.info("[%s] Pool full (5 accounts). Replacing oldest: %s", plat, removed.get("email"))

    session_filename = f"session_{email_clean.replace('@', '_').replace('.', '_')}.json"
    new_acc = {
        "id": f"{plat}_{len(accounts) + 1}",
        "platform": plat,
        "email": email_clean,
        "label": label or f"{plat.capitalize()} Account {len(accounts) + 1}",
        "status": "pending_auth",
        "created_at": time.time(),
        "updated_at": time.time(),
        "session_file": str(_provider_dir(plat) / session_filename),
        "credits_remaining": DEFAULT_DAILY_CREDITS.get(plat, 60),
        "total_generated": 0,
        "last_reset_day": time.strftime("%Y-%m-%d"),
    }
    accounts.append(new_acc)
    save_platform_accounts(plat, accounts)
    return new_acc


def get_active_account(platform: str) -> Optional[Dict[str, Any]]:
    """Retrieve the next ready account with credits for the given platform."""
    plat = platform.lower().strip()
    accounts = list_platform_accounts(plat)
    today = time.strftime("%Y-%m-%d")

    # Refresh daily credits if new day
    changed = False
    for a in accounts:
        if a.get("last_reset_day") != today:
            a["credits_remaining"] = DEFAULT_DAILY_CREDITS.get(plat, 60)
            a["last_reset_day"] = today
            changed = True
    if changed:
        save_platform_accounts(plat, accounts)

    valid = [
        a for a in accounts
        if a.get("status") == "active"
        and a.get("credits_remaining", 0) > 0
        and Path(a.get("session_file", "")).exists()
    ]
    if not valid:
        return None

    # Rotate account with lowest total_generated
    valid.sort(key=lambda x: x.get("total_generated", 0))
    return valid[0]


def record_successful_generation(platform: str, email: str, credit_cost: int = 10) -> None:
    """Record that an account generated a clip, decrementing credits."""
    plat = platform.lower().strip()
    accounts = list_platform_accounts(plat)
    for a in accounts:
        if a.get("email") == email.strip().lower():
            a["total_generated"] = a.get("total_generated", 0) + 1
            a["credits_remaining"] = max(0, a.get("credits_remaining", 50) - credit_cost)
            a["updated_at"] = time.time()
            break
    save_platform_accounts(plat, accounts)


def get_pool_status_summary() -> Dict[str, Any]:
    """Return a comprehensive summary of all 5 platforms and their accounts."""
    summary: Dict[str, Any] = {}
    total_active_accounts = 0
    total_credits = 0

    for plat in SUPPORTED_PLATFORMS:
        accs = list_platform_accounts(plat)
        active = [a for a in accs if a.get("status") == "active" and Path(a.get("session_file", "")).exists()]
        credits = sum(a.get("credits_remaining", 0) for a in active)
        summary[plat] = {
            "total_accounts": len(accs),
            "active_accounts": len(active),
            "total_credits_remaining": credits,
            "accounts": [
                {
                    "email": a.get("email"),
                    "status": a.get("status"),
                    "credits": a.get("credits_remaining"),
                    "generated": a.get("total_generated"),
                }
                for a in accs
            ],
        }
        total_active_accounts += len(active)
        total_credits += credits

    summary["meta"] = {
        "total_active_accounts": total_active_accounts,
        "total_credits_available": total_credits,
        "estimated_daily_clips": int(total_credits / 10),
    }
    return summary
