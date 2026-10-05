"""
Cross-cycle fault circuit breaker.

Stops burning API budget when the same hard failure signature repeats
across live-lab cycles (the gap that let cycles 6–24 burn keys before
a human noticed).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SOFTWARE_ROOT = Path(__file__).resolve().parents[1]
LAB_DIR = SOFTWARE_ROOT / "data" / "live_lab"
STATE_PATH = LAB_DIR / "circuit_state.json"

# Same family of faults → one signature bucket
_SIGNATURE_RULES: List[Tuple[str, re.Pattern[str]]] = [
    ("wrong_niche_template", re.compile(r"wrong_niche_template|gadget_elements_on_nongadget", re.I)),
    ("repeated_dialogue", re.compile(r"repeated_dialogue", re.I)),
    ("dead_air_ratio", re.compile(r"dead_air_ratio", re.I)),
    ("unbound_local", re.compile(r"cannot access local variable|UnboundLocalError", re.I)),
    ("speech_pace", re.compile(r"speech_pace_too_fast|last_word_integrity|speech_too_short", re.I)),
    ("critic_outage", re.compile(r"critic_outage|google_circuit_open", re.I)),
    ("agnes_quota", re.compile(r"agnes.*(429|quota|rate.?limit)", re.I)),
    ("master_unshippable", re.compile(r"master_unshippable", re.I)),
]


def fault_signature(error_text: str) -> str:
    text = (error_text or "").strip()
    if not text:
        return ""
    for name, pat in _SIGNATURE_RULES:
        if pat.search(text):
            return name
    # coarse fallback: first token after generate_*:
    m = re.search(r"generate_\w+:\s*([^:\s,]+)", text, re.I)
    if m:
        return m.group(1).lower()[:48]
    return re.sub(r"\s+", "_", text.lower())[:48]


def _load_state() -> Dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"streak_sig": "", "streak_count": 0, "safe_mode": False, "history": []}


def _save_state(st: Dict[str, Any]) -> None:
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def record_cycle_outcome(*, cycle: int, phase: str, error: str = "") -> Dict[str, Any]:
    """Call after each cycle ends. Arms safe_mode after 2 identical hard fails."""
    st = _load_state()
    sig = fault_signature(error) if phase == "failed" and error else ""
    hist: List[Dict[str, Any]] = list(st.get("history") or [])
    hist.append({"cycle": cycle, "phase": phase, "sig": sig, "error": (error or "")[:200]})
    st["history"] = hist[-20:]

    if sig and sig == st.get("streak_sig"):
        st["streak_count"] = int(st.get("streak_count") or 0) + 1
    elif sig:
        st["streak_sig"] = sig
        st["streak_count"] = 1
    else:
        # success / cancel clears streak
        st["streak_sig"] = ""
        st["streak_count"] = 0
        st["safe_mode"] = False

    # 2 identical fails → safe mode (image fallback, fewer Agnes calls)
    if int(st.get("streak_count") or 0) >= 2 and sig:
        st["safe_mode"] = True
        try:
            from pipeline.idempotency.metrics import UsageEvent, record_usage_event

            record_usage_event(
                LAB_DIR,
                UsageEvent(
                    operation="circuit_breaker",
                    provider="cycle_circuit",
                    model="N/A",
                    status_code_class="CIRCUIT_OPEN",
                    outcome="circuit_open",
                    detail=f"sig={sig}",
                ),
            )
        except Exception:
            pass
        st["safe_mode_reason"] = f"repeat_fault:{sig}x{st['streak_count']}"

    # 3 identical → hard stop new cycles until cleared
    if int(st.get("streak_count") or 0) >= 3 and sig:
        st["hard_stop"] = True
        st["hard_stop_reason"] = f"repeat_fault:{sig}x{st['streak_count']}"
    elif not sig:
        st["hard_stop"] = False
        st["hard_stop_reason"] = ""

    _save_state(st)
    return st


def preflight_for_cycle() -> Dict[str, Any]:
    """
    Returns:
      ok: False if hard_stop armed
      safe_mode: True → caller must disable Agnes / use image fallback
    """
    st = _load_state()
    if st.get("hard_stop"):
        return {
            "ok": False,
            "safe_mode": True,
            "blockers": [
                f"circuit_hard_stop:{st.get('hard_stop_reason') or st.get('streak_sig')}. "
                "Clear data/live_lab/circuit_state.json after fixing root cause."
            ],
            "state": st,
        }
    return {
        "ok": True,
        "safe_mode": bool(st.get("safe_mode")),
        "blockers": [],
        "state": st,
        "reason": st.get("safe_mode_reason") or "",
    }


def clear_circuit(*, keep_history: bool = True) -> None:
    st = _load_state()
    hist = st.get("history") if keep_history else []
    _save_state(
        {
            "streak_sig": "",
            "streak_count": 0,
            "safe_mode": False,
            "hard_stop": False,
            "hard_stop_reason": "",
            "history": hist or [],
            "cleared_manually": True,
        }
    )
