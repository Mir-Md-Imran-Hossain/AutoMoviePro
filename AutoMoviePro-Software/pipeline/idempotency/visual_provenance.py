"""Visual generation provenance persistence (BUILD-04A)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from domain.enums import AssetType
from domain.media import MediaAsset, Provenance, VisualAsset
from pipeline.idempotency.fingerprint import hash_artifact
from pipeline.idempotency.visual_request import VisualRequestSpec


def provenance_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "visual_provenance"


def provenance_path(work_dir: Path, fingerprint: str) -> Path:
    return provenance_dir(work_dir) / f"{fingerprint[:24]}.json"


def save_visual_provenance(
    work_dir: Path,
    *,
    spec: VisualRequestSpec,
    fingerprint: str,
    asset_path: str,
    asset_hash: str,
    generation_id: str = "",
    requested_seed: Optional[int] = None,
    actual_seed: Optional[int] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    prov = Provenance(
        job_id=spec.job_id,
        provider=spec.provider,
        model=spec.model,
        prompt_hash=spec.prompt_hash,
        input_hash=fingerprint,
        generation_id=generation_id or "",
        seed=str(actual_seed if actual_seed is not None else (requested_seed or "")),
        metadata={
            "scene_id": spec.scene_id,
            "canonical_scene_id": spec.canonical_scene_id,
            "dialogue_id": spec.dialogue_id,
            "script_id": spec.script_id,
            "segment_id": spec.segment_id,
            "part_index": spec.part_index,
            "revision_id": spec.revision_id,
            "visual_plan_id": spec.visual_plan_id,
            "entity_id": spec.entity_id,
            "generation_mode": spec.generation_mode.value,
            "requested_seed": requested_seed,
            "actual_seed": actual_seed,
            "reference_asset_id": spec.reference_asset_id,
            "reference_asset_hash": spec.reference_asset_hash,
            "saved_at": time.time(),
            **(extra or {}),
        },
    )
    asset = VisualAsset(
        asset_type=AssetType.VIDEO,
        scene_id=str(spec.scene_id),
        source="generated",
        file_path=asset_path,
        file_hash=asset_hash,
        provenance=prov,
        metadata={"entity_id": spec.entity_id},
    )
    out = provenance_path(work_dir, fingerprint)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(asset.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, out)
    return out


def load_visual_provenance(work_dir: Path, fingerprint: str) -> Optional[dict[str, Any]]:
    p = provenance_path(work_dir, fingerprint)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def asset_id_from_fingerprint(fingerprint: str, scene_id: int) -> str:
    return f"visual-{scene_id:02d}-{fingerprint[:16]}"
