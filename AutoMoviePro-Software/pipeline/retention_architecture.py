"""Short/long-form retention architecture metadata + role assignment."""
from __future__ import annotations

from typing import Any, Dict, List


def retention_blueprint(video_type: str = "short") -> Dict[str, Any]:
    if (video_type or "").lower() == "long":
        return {
            "format": "long",
            "windows": [
                {"id": "open", "start_sec": 0, "end_sec": 5, "job": "pattern_interrupt"},
                {"id": "promise", "start_sec": 5, "end_sec": 15, "job": "curiosity_gap"},
                {"id": "payoff1", "start_sec": 15, "end_sec": 40, "job": "first_payoff"},
            ],
            "loop": ["question", "evidence", "payoff", "new_question"],
            "min_open_loops": 3,
            "min_loop_close_ratio": 0.8,
            "forbid_flat_streak": 2,
            "require_ending_close": True,
        }
    return {
        "format": "short",
        "windows": [
            {"id": "pattern_interrupt", "start_sec": 0, "end_sec": 2, "job": "Pattern Interrupt"},
            {"id": "curiosity_gap", "start_sec": 2, "end_sec": 5, "job": "Curiosity Gap"},
            {"id": "first_payoff", "start_sec": 5, "end_sec": 10, "job": "First Payoff"},
        ],
        "loop": ["question", "evidence", "payoff", "new_question"],
        "min_open_loops": 2,
        "min_loop_close_ratio": 0.7,
        "forbid_flat_streak": 2,
        "require_ending_close": True,
    }


def assign_retention_roles(scenes: List[Dict[str, Any]], *, video_type: str = "short") -> List[Dict[str, Any]]:
    bp = retention_blueprint(video_type)
    roles = ["pattern_interrupt", "curiosity_gap", "first_payoff"]
    loop = list(bp.get("loop") or [])
    out: List[Dict[str, Any]] = []
    n = len([s for s in (scenes or []) if isinstance(s, dict)])
    for i, sc in enumerate(scenes or []):
        if not isinstance(sc, dict):
            continue
        row = dict(sc)
        explicit = str(row.get("retention_role") or "").strip()
        if i < len(roles):
            role = explicit or roles[i]
            win = next((w for w in bp["windows"] if w["id"] == roles[i]), bp["windows"][0])
        elif i == n - 1 and n > 3:
            role = explicit or "ending"
            win = {"start_sec": None, "end_sec": None, "job": "close_main_loop"}
        else:
            role = explicit or loop[(i - len(roles)) % max(1, len(loop))]
            win = {"start_sec": None, "end_sec": None, "job": role}
        row["retention_role"] = role
        row["retention"] = {
            "role": role,
            "window_start_sec": win.get("start_sec"),
            "window_end_sec": win.get("end_sec"),
            "job": win.get("job") or role,
            "open_loop": str(row.get("open_loop") or "").strip() or None,
            "payoff_for": str(row.get("payoff_for") or "").strip() or None,
        }
        out.append(row)
    return out


def attach_retention_to_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    plan = dict(plan or {})
    vt = str(plan.get("video_type") or "short")
    bp = retention_blueprint(vt)
    # Keep blueprint out of top-level ScriptPlan validation; store under metadata.
    meta = dict(plan.get("metadata") or {})
    meta["retention_blueprint"] = bp
    plan["metadata"] = meta
    plan["scenes"] = assign_retention_roles(list(plan.get("scenes") or []), video_type=vt)
    # Mirror onto beats if present
    if plan.get("beats"):
        plan["beats"] = assign_retention_roles(list(plan.get("beats") or []), video_type=vt)
    return plan
