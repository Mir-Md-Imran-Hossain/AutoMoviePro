"""Script generation provenance (BUILD-04C)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.script_request import ScriptRequestSpec


def provenance_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "script_provenance"


def provenance_path(work_dir: Path, fingerprint: str) -> Path:
    return provenance_dir(work_dir) / f"{fingerprint[:24]}.json"


def save_script_provenance(
    work_dir: Path,
    *,
    spec: ScriptRequestSpec,
    fingerprint: str,
    plan_path: str,
    plan_hash: str,
    generation_id: str = "",
    provider: str = "",
    model: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    record = {
        "job_id": spec.job_id,
        "fingerprint": fingerprint,
        "entity_id": spec.entity_id,
        "topic": spec.topic,
        "topic_identity": spec.topic_identity,
        "niche": spec.niche,
        "niche_id": spec.niche_id,
        "fact_pack_id": spec.fact_pack_id,
        "fact_pack_hash": spec.fact_pack_hash,
        "prompt_version": spec.prompt_version,
        "prompt_template_hash": spec.prompt_template_hash,
        "provider": provider or spec.provider,
        "model": model or spec.model,
        "generation_id": generation_id or "",
        "plan_path": plan_path,
        "plan_hash": plan_hash,
        "saved_at": time.time(),
        "metadata": {
            "video_type": spec.video_type,
            "max_seconds": spec.max_seconds,
            "language": spec.language,
            "revision_id": spec.revision_id,
            **(extra or {}),
        },
    }
    out = provenance_path(work_dir, fingerprint)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out)
    return out


def load_script_provenance(work_dir: Path, fingerprint: str) -> Optional[dict[str, Any]]:
    p = provenance_path(work_dir, fingerprint)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
