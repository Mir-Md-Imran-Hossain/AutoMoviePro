"""Quality provenance persistence (BUILD-04F)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from pipeline.quality.contracts import CreativeQualityResult


def provenance_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "quality_provenance"


def provenance_path(work_dir: Path, fingerprint: str) -> Path:
    return provenance_dir(work_dir) / f"{fingerprint[:24]}.json"


def save_quality_provenance(
    work_dir: Path,
    *,
    result: CreativeQualityResult,
    fingerprint: str,
    repair_revision: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    record = {
        "fingerprint": fingerprint,
        "artifact_fingerprint": result.artifact_fingerprint,
        "subject_id": result.subject_id,
        "stage": result.stage,
        "verdict": result.verdict.value,
        "score": result.score,
        "evaluator_version": result.evaluator_version,
        "rule_version": result.rule_version,
        "issue_ids": [i.issue_id for i in result.issues],
        "repair_scope": result.repair_scope.value if result.repair_scope else "",
        "repair_revision": repair_revision or result.revision_id,
        "saved_at": time.time(),
        "result": result.to_dict(),
        "metadata": dict(extra or {}),
    }
    out = provenance_path(work_dir, fingerprint)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out)
    return out


def load_quality_provenance(work_dir: Path, fingerprint: str) -> Optional[dict[str, Any]]:
    p = provenance_path(work_dir, fingerprint)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
