"""Render provenance (BUILD-04D)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.render_request import RenderRequestSpec


def provenance_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "render_provenance"


def provenance_path(work_dir: Path, fingerprint: str) -> Path:
    return provenance_dir(work_dir) / f"{fingerprint[:24]}.json"


def save_render_provenance(
    work_dir: Path,
    *,
    spec: RenderRequestSpec,
    fingerprint: str,
    output_path: str,
    output_hash: str,
    validation_result: str = "ok",
    generation_id: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    record = {
        "job_id": spec.job_id,
        "fingerprint": fingerprint,
        "entity_id": spec.entity_id,
        "manifest": spec.manifest.normalized(),
        "provider": spec.provider,
        "model": spec.model,
        "output_path": output_path,
        "output_hash": output_hash,
        "validation_result": validation_result,
        "generation_id": generation_id or "",
        "saved_at": time.time(),
        "metadata": dict(extra or {}),
    }
    out = provenance_path(work_dir, fingerprint)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, out)
    return out


def load_render_provenance(work_dir: Path, fingerprint: str) -> Optional[dict[str, Any]]:
    p = provenance_path(work_dir, fingerprint)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
