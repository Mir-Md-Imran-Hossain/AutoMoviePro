"""Artifact gate aggregation + persistence + retry cost protection (AMP-004 Phase-04)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.artifact_verification.contracts import ArtifactObservation, ObservationStatus

logger = logging.getLogger(__name__)

ARTIFACT_GATE_FILE = "ARTIFACT_GATE.json"
OBSERVATIONS_DIR = "artifact_observations"
VERIFY_CYCLE_FILE = "ARTIFACT_VERIFY_CYCLES.json"

# Cost protection — no uncontrolled regeneration loop
MAX_VERIFY_REPAIR_CYCLES = 3


def observations_dir(work_dir: Path) -> Path:
    return Path(work_dir) / OBSERVATIONS_DIR


def persist_observation(work_dir: Path, obs: ArtifactObservation) -> Path:
    work_dir = Path(work_dir)
    d = observations_dir(work_dir)
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in obs.artifact_id)[:120]
    path = d / f"{safe}.json"
    path.write_text(json.dumps(obs.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_observations(work_dir: Path) -> list[dict[str, Any]]:
    d = observations_dir(work_dir)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("observation read failed %s: %s", p, exc)
    return out


def aggregate_artifact_gate(
    observations: list[ArtifactObservation | dict[str, Any]],
    *,
    job_id: str = "",
    final_verified: bool = False,
) -> dict[str, Any]:
    """
    Aggregate observations into ARTIFACT_GATE for publishability.

    status vocabulary: PASS | BLOCKED | UNKNOWN | PARTIAL
    - Any technical FAIL → BLOCKED
    - Missing final composite observation when required → UNKNOWN (unverified)
    - Technical PASS with nested semantic UNKNOWN → artifact status PASS
      (semantic honesty preserved in semantic_summary; not claimed as semantic PASS)
    """
    rows: list[dict[str, Any]] = []
    for o in observations:
        rows.append(o.to_dict() if isinstance(o, ArtifactObservation) else dict(o))

    fails = [r for r in rows if str(r.get("observation_status") or "").upper() == "FAIL"
             or str(r.get("technical_status") or "").upper() == "FAIL"]
    unknowns = [r for r in rows if str(r.get("observation_status") or "").upper() == "UNKNOWN"
                or str(r.get("technical_status") or "").upper() == "UNKNOWN"]
    composites = [r for r in rows if str(r.get("media_type") or "").upper() == "COMPOSITE"
                  or str(r.get("layer") or "") == "E"]

    semantic_fails = [
        r for r in rows if str(r.get("semantic_status") or "").upper() == "FAIL"
    ]
    semantic_unknowns = [
        r for r in rows if str(r.get("semantic_status") or "").upper() == "UNKNOWN"
    ]

    if fails or semantic_fails:
        status = "BLOCKED"
        reason = "artifact_technical_or_semantic_fail"
    elif not rows:
        status = "UNKNOWN"
        reason = "no_artifact_observations"
    elif not final_verified and not composites:
        status = "UNKNOWN"
        reason = "final_composite_unverified"
    elif unknowns and not any(str(r.get("technical_status") or "").upper() == "PASS" for r in rows):
        status = "UNKNOWN"
        reason = "artifact_observation_unknown"
    else:
        status = "PASS"
        reason = "artifact_technical_pass"

    return {
        "status": status,
        "verdict": status,
        "reason": reason,
        "job_id": job_id,
        "observation_count": len(rows),
        "failed_count": len(fails),
        "semantic_fail_count": len(semantic_fails),
        "semantic_unknown_count": len(semantic_unknowns),
        "final_verified": bool(final_verified or composites),
        "semantic_summary": {
            "unknown_is_not_pass": True,
            "technical_pass_implies_semantic_pass": False,
            "unknown_count": len(semantic_unknowns),
            "fail_count": len(semantic_fails),
        },
        "observations": [
            {
                "artifact_id": r.get("artifact_id"),
                "media_type": r.get("media_type"),
                "technical_status": r.get("technical_status"),
                "semantic_status": r.get("semantic_status"),
                "observation_status": r.get("observation_status"),
                "path": r.get("path"),
                "issues": r.get("issues") or [],
            }
            for r in rows
        ],
    }


def persist_artifact_gate(work_dir: Path, gate: dict[str, Any]) -> Path:
    work_dir = Path(work_dir)
    path = work_dir / ARTIFACT_GATE_FILE
    path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_artifact_gate(work_dir: Path) -> Optional[dict[str, Any]]:
    path = Path(work_dir) / ARTIFACT_GATE_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_verify_cycles(work_dir: Path) -> dict[str, Any]:
    path = Path(work_dir) / VERIFY_CYCLE_FILE
    if not path.is_file():
        return {"cycles": 0, "max_cycles": MAX_VERIFY_REPAIR_CYCLES, "history": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"cycles": 0, "max_cycles": MAX_VERIFY_REPAIR_CYCLES, "history": []}


def record_verify_cycle(work_dir: Path, *, outcome: str, repair_scope: str = "") -> dict[str, Any]:
    """Increment verify→repair→re-verify cycle; refuse unbounded loops."""
    data = read_verify_cycles(work_dir)
    cycles = int(data.get("cycles") or 0) + 1
    history = list(data.get("history") or [])
    history.append({"cycle": cycles, "outcome": outcome, "repair_scope": repair_scope})
    data = {
        "cycles": cycles,
        "max_cycles": MAX_VERIFY_REPAIR_CYCLES,
        "history": history[-20:],
        "exhausted": cycles >= MAX_VERIFY_REPAIR_CYCLES,
    }
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    (Path(work_dir) / VERIFY_CYCLE_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def allow_another_repair_cycle(work_dir: Path) -> bool:
    data = read_verify_cycles(work_dir)
    return int(data.get("cycles") or 0) < int(data.get("max_cycles") or MAX_VERIFY_REPAIR_CYCLES)
