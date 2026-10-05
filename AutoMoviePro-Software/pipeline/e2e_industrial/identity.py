"""Identity propagation checks across E2E fixture artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def verify_identity_trace(work_dir: Path, *, job_id: str) -> dict[str, Any]:
    work_dir = Path(work_dir)
    issues: list[str] = []
    scene_ids: list[str] = []
    dialogue_ids: list[str] = []
    fingerprints: list[str] = []

    fixture = work_dir / "E2E_FIXTURE.json"
    if fixture.is_file():
        meta = json.loads(fixture.read_text(encoding="utf-8"))
        if str(meta.get("job_id") or "") != job_id:
            issues.append("fixture_job_id_mismatch")
        scene_ids.extend(meta.get("scene_ids") or [])
        dialogue_ids.extend(meta.get("dialogue_ids") or [])
    else:
        issues.append("missing_e2e_fixture_meta")

    for p in sorted(work_dir.glob("scene_*.identity.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if str(data.get("job_id") or "") != job_id:
            issues.append(f"identity_job_mismatch:{p.name}")
        sid = str(data.get("scene_id") or "")
        did = str(data.get("dialogue_id") or "")
        fp = str(data.get("asset_fingerprint") or "")
        if not sid:
            issues.append(f"missing_scene_id:{p.name}")
        if not did:
            issues.append(f"missing_dialogue_id:{p.name}")
        if not fp:
            issues.append(f"missing_asset_fingerprint:{p.name}")
        if sid in scene_ids[:0]:
            pass
        fingerprints.append(fp)

    if len(set(scene_ids)) != len(scene_ids):
        issues.append("duplicate_scene_id")
    if len(set(dialogue_ids)) != len(dialogue_ids):
        issues.append("duplicate_dialogue_id")
    if fingerprints and len(set(fingerprints)) != len(fingerprints):
        issues.append("duplicate_asset_fingerprint_cross_scene")

    # Render contract project binding
    for p in (work_dir / "render_contracts").glob("*.json") if (work_dir / "render_contracts").is_dir() else []:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if raw.get("project_id") and raw.get("project_id") != job_id:
                issues.append("render_contract_wrong_project")
        except Exception:
            issues.append(f"render_contract_unreadable:{p.name}")

    status = "BLOCK" if issues else "PASS"
    return {
        "status": status,
        "issues": issues,
        "job_id": job_id,
        "scene_ids": scene_ids,
        "dialogue_ids": dialogue_ids,
        "fingerprint_count": len(fingerprints),
        "method": "DETERMINISTIC",
    }
