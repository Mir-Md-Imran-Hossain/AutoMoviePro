"""RENDERING_INTEGRITY_GATE persistence + repair cycle budget."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

RENDERING_INTEGRITY_GATE_FILE = "RENDERING_INTEGRITY_GATE.json"
RENDER_CONTRACTS_DIR = "render_contracts"
MAX_RENDER_INTEGRITY_REPAIR_CYCLES = 3
CYCLE_FILE = "RENDERING_INTEGRITY_VERIFY_CYCLES.json"


def persist_render_contract(work_dir: Path, contract_dict: dict[str, Any], *, key: str = "contract") -> Path:
    d = Path(work_dir) / RENDER_CONTRACTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:80]
    path = d / f"{safe}.json"
    path.write_text(json.dumps(contract_dict, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def persist_rendering_integrity_gate(work_dir: Path, gate: dict[str, Any]) -> Path:
    path = Path(work_dir) / RENDERING_INTEGRITY_GATE_FILE
    path.write_text(json.dumps(gate, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def load_rendering_integrity_gate(work_dir: Path) -> Optional[dict[str, Any]]:
    path = Path(work_dir) / RENDERING_INTEGRITY_GATE_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def allow_render_integrity_repair_cycle(work_dir: Path) -> bool:
    path = Path(work_dir) / CYCLE_FILE
    if not path.is_file():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("cycles") or 0) < MAX_RENDER_INTEGRITY_REPAIR_CYCLES
    except Exception:
        return True


def record_render_integrity_repair_cycle(work_dir: Path, *, outcome: str, scope: str = "") -> dict[str, Any]:
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
        "max_cycles": MAX_RENDER_INTEGRITY_REPAIR_CYCLES,
        "history": history[-20:],
        "exhausted": cycles >= MAX_RENDER_INTEGRITY_REPAIR_CYCLES,
    }
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
