"""Per-job spend ledger + hard cap for custom pipeline media/TTS calls."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Relative cost units (not dollars) — tune via env
DEFAULT_COSTS = {
    "topic": 2.0,
    "visual": 2.0,
    "localize": 1.0,
    "tts": 3.0,
    "image": 1.0,
    "video": 8.0,
    "stock": 0.2,
    "kenburns": 0.1,
}


class BudgetExceeded(Exception):
    def __init__(self, spent: float, cap: float, message: str = ""):
        self.spent = spent
        self.cap = cap
        super().__init__(message or f"Job budget exceeded: spent={spent} cap={cap}")


def budget_cap_units() -> Optional[float]:
    raw = (os.environ.get("AMP_JOB_BUDGET_UNITS") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def cost_for(kind: str) -> float:
    env_key = f"AMP_COST_{kind.upper()}"
    raw = (os.environ.get(env_key) or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return float(DEFAULT_COSTS.get(kind, 1.0))


def record_spend(
    state: Dict[str, Any],
    *,
    kind: str,
    provider: str = "",
    units: Optional[float] = None,
    note: str = "",
) -> float:
    budget = state.setdefault("budget", {"spent_units": 0.0, "cap_units": None, "entries": []})
    if budget.get("cap_units") is None:
        budget["cap_units"] = budget_cap_units()
    amt = float(units if units is not None else cost_for(kind))
    budget["spent_units"] = float(budget.get("spent_units") or 0.0) + amt
    entries = list(budget.get("entries") or [])
    entries.append(
        {
            "ts": time.time(),
            "kind": kind,
            "provider": provider,
            "units": amt,
            "note": note[:160],
        }
    )
    budget["entries"] = entries[-300:]
    return float(budget["spent_units"])


def ensure_budget(state: Dict[str, Any], *, kind: str = "", upcoming: float = 0.0) -> None:
    budget = state.setdefault("budget", {"spent_units": 0.0, "cap_units": None, "entries": []})
    cap = budget.get("cap_units")
    if cap is None:
        cap = budget_cap_units()
        budget["cap_units"] = cap
    if cap is None:
        return
    spent = float(budget.get("spent_units") or 0.0)
    need = upcoming if upcoming > 0 else (cost_for(kind) if kind else 0.0)
    if spent + need > float(cap):
        raise BudgetExceeded(spent, float(cap), f"Cannot afford {kind or 'next'} call")
