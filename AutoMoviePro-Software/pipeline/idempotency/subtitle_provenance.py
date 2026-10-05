"""Subtitle provenance (BUILD-04E)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.subtitle_request import SubtitleRequestSpec


def provenance_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "subtitle_provenance"


def provenance_path(work_dir: Path, fingerprint: str) -> Path:
    return provenance_dir(work_dir) / f"{fingerprint[:24]}.json"


def save_subtitle_provenance(
    work_dir: Path,
    *,
    spec: SubtitleRequestSpec,
    fingerprint: str,
    srt_path: str,
    srt_hash: str,
    generation_id: str = "",
    validation_result: str = "ok",
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    record = {
        "job_id": spec.job_id,
        "fingerprint": fingerprint,
        "entity_id": spec.entity_id,
        "scene_id": spec.scene_id,
        "dialogue_id": spec.dialogue_id,
        "segment_id": spec.segment_id,
        "language": spec.language,
        "audio_fingerprint": spec.audio_fingerprint,
        "audio_duration_sec": spec.audio_duration_sec,
        "timing_model": spec.timing_model,
        "provider": spec.provider,
        "model": spec.model,
        "srt_path": srt_path,
        "srt_hash": srt_hash,
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


def load_subtitle_provenance(work_dir: Path, fingerprint: str) -> Optional[dict[str, Any]]:
    p = provenance_path(work_dir, fingerprint)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
