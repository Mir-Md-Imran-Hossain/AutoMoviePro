"""Multimodal status aggregation for publishability (AMP-004 Phase-02).

Persists per-beat IndustrialValidationReport into work_dir and aggregates
for evaluate_publishability. Does NOT create a second quality score system.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

MULTIMODAL_DIR = "multimodal_gates"
MULTIMODAL_GATE_FILE = "MULTIMODAL_QUALITY_GATE.json"

# Status vocabulary shared with publishability AND
STATUS_PASS = "PASS"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_PARTIAL = "PARTIAL"
STATUS_ABSENT = "ABSENT"


def multimodal_gates_dir(work_dir: Path) -> Path:
    return Path(work_dir) / MULTIMODAL_DIR


def persist_multimodal_report(
    work_dir: Path,
    report: Any,
    *,
    scene_key: str = "",
) -> Path:
    """Write one scene multimodal report and refresh job aggregate."""
    work_dir = Path(work_dir)
    d = multimodal_gates_dir(work_dir)
    d.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    key = scene_key or f"{payload.get('scene_id', 'scene')}_{payload.get('dialogue_id', 'dlg')}"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(key))[:120]
    path = d / f"{safe}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    aggregate_and_persist(work_dir)
    return path


def _status_from_payload(data: dict[str, Any]) -> str:
    raw = str(data.get("final_status") or data.get("status") or STATUS_UNKNOWN).upper()
    if raw in (STATUS_BLOCKED, "SEMANTIC_BLOCKED"):
        return STATUS_BLOCKED
    if raw in (STATUS_PASS, "VERIFIED", "SEMANTIC_PASS"):
        return STATUS_PASS
    if raw == STATUS_PARTIAL:
        return STATUS_PARTIAL
    if raw == STATUS_UNKNOWN:
        return STATUS_UNKNOWN
    if data.get("blocked") is True:
        return STATUS_BLOCKED
    return STATUS_UNKNOWN


def load_scene_multimodal_reports(work_dir: Path) -> list[dict[str, Any]]:
    d = multimodal_gates_dir(work_dir)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("multimodal gate read failed %s: %s", p, exc)
    return out


def aggregate_multimodal_status(work_dir: Path) -> dict[str, Any]:
    """
    Aggregate per-scene multimodal gates into a single status for publishability.
    BLOCKED wins. Else UNKNOWN (mandatory). Else PARTIAL. Else PASS. Else ABSENT.
    """
    reports = load_scene_multimodal_reports(work_dir)
    gate_path = Path(work_dir) / MULTIMODAL_GATE_FILE
    if not reports and gate_path.is_file():
        try:
            existing = json.loads(gate_path.read_text(encoding="utf-8"))
            if existing.get("status"):
                return existing
        except Exception:
            pass
    if not reports:
        return {
            "status": STATUS_ABSENT,
            "mandatory_unknown": False,
            "scene_count": 0,
            "blocked_scenes": [],
            "unknown_scenes": [],
            "reason": "no_multimodal_evidence",
        }

    statuses = [_status_from_payload(r) for r in reports]
    blocked = [r for r, s in zip(reports, statuses) if s == STATUS_BLOCKED]
    unknown = [r for r, s in zip(reports, statuses) if s == STATUS_UNKNOWN]
    partial = [r for r, s in zip(reports, statuses) if s == STATUS_PARTIAL]

    if blocked:
        status = STATUS_BLOCKED
        reason = "multimodal_blocked"
    elif unknown:
        status = STATUS_UNKNOWN
        reason = "multimodal_unknown_mandatory"
    elif partial:
        status = STATUS_PARTIAL
        reason = "multimodal_partial"
    else:
        status = STATUS_PASS
        reason = "multimodal_pass"

    return {
        "status": status,
        "mandatory_unknown": status == STATUS_UNKNOWN,
        "scene_count": len(reports),
        "blocked_scenes": [
            {"scene_id": r.get("scene_id"), "dialogue_id": r.get("dialogue_id")} for r in blocked
        ],
        "unknown_scenes": [
            {"scene_id": r.get("scene_id"), "dialogue_id": r.get("dialogue_id")} for r in unknown
        ],
        "partial_count": len(partial),
        "reason": reason,
        "reports": [
            {
                "scene_id": r.get("scene_id"),
                "dialogue_id": r.get("dialogue_id"),
                "final_status": _status_from_payload(r),
                "intent_fingerprint": r.get("intent_fingerprint"),
            }
            for r in reports
        ],
    }


def aggregate_and_persist(work_dir: Path) -> dict[str, Any]:
    agg = aggregate_multimodal_status(work_dir)
    path = Path(work_dir) / MULTIMODAL_GATE_FILE
    path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    return agg


def load_multimodal_gate(work_dir: Path) -> Optional[dict[str, Any]]:
    path = Path(work_dir) / MULTIMODAL_GATE_FILE
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    # Rebuild from scene files if present
    if multimodal_gates_dir(work_dir).is_dir():
        return aggregate_and_persist(work_dir)
    return None


def assert_production_semantic_bypass_forbidden(
    metadata: Optional[dict[str, Any]],
    *,
    production: bool,
    allow_test_only: bool = False,
) -> None:
    """
    Production must not silently skip semantic/multimodal validation.
    TEST_ONLY / DEV_ONLY may set metadata['semantic_bypass_class'] accordingly.
    """
    meta = metadata or {}
    if not meta.get("skip_semantic_validation"):
        return
    bypass_class = str(meta.get("semantic_bypass_class") or "").upper()
    if allow_test_only and bypass_class in ("TEST_ONLY", "DEV_ONLY", "OFFLINE_TEST_ONLY"):
        return
    if production:
        raise PermissionError(
            "skip_semantic_validation forbidden in production "
            "(require semantic_bypass_class=TEST_ONLY|DEV_ONLY for non-prod harness)"
        )
