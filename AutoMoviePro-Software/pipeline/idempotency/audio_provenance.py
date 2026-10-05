"""Audio generation provenance (BUILD-04B)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from domain.enums import AssetType
from domain.media import AudioAsset, Provenance
from pipeline.idempotency.audio_request import AudioRequestSpec


def provenance_dir(work_dir: Path) -> Path:
    return Path(work_dir) / "audio_provenance"


def provenance_path(work_dir: Path, fingerprint: str) -> Path:
    return provenance_dir(work_dir) / f"{fingerprint[:24]}.json"


def save_audio_provenance(
    work_dir: Path,
    *,
    spec: AudioRequestSpec,
    fingerprint: str,
    asset_path: str,
    asset_hash: str,
    generation_id: str = "",
    duration_sec: Optional[float] = None,
    extra: Optional[dict[str, Any]] = None,
) -> Path:
    prov = Provenance(
        job_id=spec.job_id,
        provider=spec.provider,
        model=spec.model,
        prompt_hash=spec.dialogue_hash,
        input_hash=fingerprint,
        generation_id=generation_id or "",
        seed=str(spec.speaking_speed),
        metadata={
            "scene_id": spec.scene_id,
            "dialogue_id": spec.dialogue_id,
            "audio_plan_id": spec.audio_plan_id,
            "language": spec.language,
            "voice_id": spec.voice_id,
            "voice_profile": spec.voice_profile,
            "emotion": spec.emotion,
            "speaking_speed": spec.speaking_speed,
            "duration_sec": duration_sec,
            "saved_at": time.time(),
            **(extra or {}),
        },
    )
    asset = AudioAsset(
        asset_type=AssetType.AUDIO,
        scene_id=str(spec.scene_id),
        source="generated",
        file_path=asset_path,
        file_hash=asset_hash,
        duration_sec=duration_sec,
        language=spec.language,
        provenance=prov,
        metadata={"entity_id": spec.entity_id, "dialogue_id": spec.dialogue_id},
    )
    out = provenance_path(work_dir, fingerprint)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(asset.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, out)
    return out


def load_audio_provenance(work_dir: Path, fingerprint: str) -> Optional[dict[str, Any]]:
    p = provenance_path(work_dir, fingerprint)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def asset_id_from_fingerprint(fingerprint: str, scene_id: int) -> str:
    return f"audio-{scene_id:02d}-{fingerprint[:16]}"
