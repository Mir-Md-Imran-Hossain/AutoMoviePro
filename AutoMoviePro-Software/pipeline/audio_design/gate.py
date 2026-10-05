"""AUDIO_DESIGN_GATE persistence + retry budget (AMP-004 Phase-05)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

AUDIO_DESIGN_GATE_FILE = "AUDIO_DESIGN_GATE.json"
AUDIO_PLANS_DIR = "audio_plans"
MAX_AUDIO_REPAIR_CYCLES = 3
CYCLE_FILE = "AUDIO_DESIGN_VERIFY_CYCLES.json"


def persist_audio_plan(work_dir: Path, plan_dict: dict[str, Any], *, key: str = "") -> Path:
    d = Path(work_dir) / AUDIO_PLANS_DIR
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (key or plan_dict.get("dialogue_id") or "plan"))[:100]
    path = d / f"{safe}.json"
    path.write_text(json.dumps(plan_dict, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def persist_audio_design_gate(work_dir: Path, gate: dict[str, Any]) -> Path:
    path = Path(work_dir) / AUDIO_DESIGN_GATE_FILE
    path.write_text(json.dumps(gate, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_audio_design_gate(work_dir: Path) -> Optional[dict[str, Any]]:
    path = Path(work_dir) / AUDIO_DESIGN_GATE_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def allow_audio_repair_cycle(work_dir: Path) -> bool:
    path = Path(work_dir) / CYCLE_FILE
    if not path.is_file():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("cycles") or 0) < MAX_AUDIO_REPAIR_CYCLES
    except Exception:
        return True


def record_audio_repair_cycle(work_dir: Path, *, outcome: str, scope: str = "") -> dict[str, Any]:
    path = Path(work_dir) / CYCLE_FILE
    data = {"cycles": 0, "history": []}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    cycles = int(data.get("cycles") or 0) + 1
    history = list(data.get("history") or [])
    history.append({"cycle": cycles, "outcome": outcome, "scope": scope})
    out = {
        "cycles": cycles,
        "max_cycles": MAX_AUDIO_REPAIR_CYCLES,
        "history": history[-20:],
        "exhausted": cycles >= MAX_AUDIO_REPAIR_CYCLES,
    }
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
