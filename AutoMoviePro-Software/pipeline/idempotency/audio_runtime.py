"""Audio/TTS generation runtime — BUILD-04B integration layer."""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.generation_cache import GenerationCache
from pipeline.idempotency.audio_provenance import (
    asset_id_from_fingerprint,
    load_audio_provenance,
    save_audio_provenance,
)
from pipeline.idempotency.audio_request import AudioRequestSpec, compute_audio_fingerprint
from pipeline.idempotency.audio_validation import probe_duration_sec, validate_audio_asset
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import hash_artifact
from pipeline.idempotency.mock_audio_provider import MockAudioProvider, get_mock_audio_provider
from pipeline.idempotency.states import IdempotencyState

logger = logging.getLogger(__name__)

ProviderFn = Callable[[], Path]


@dataclass
class AudioGenerationResult:
    success: bool
    path: Optional[Path] = None
    action: str = ""
    fingerprint: str = ""
    asset_id: str = ""
    asset_hash: str = ""
    generation_id: str = ""
    duration_sec: Optional[float] = None
    provider_invocations: int = 0
    metrics: dict[str, int] = field(default_factory=dict)
    state: IdempotencyState = IdempotencyState.NOT_STARTED


def _legacy_audio_key(spec: AudioRequestSpec) -> str:
    raw = "|".join(
        [
            str(spec.scene_id),
            spec.dialogue_id,
            spec.language,
            spec.provider,
            spec.model,
            spec.voice_id,
            spec.emotion,
            str(spec.speaking_speed),
            spec.dialogue_text.strip()[:500],
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def execute_audio_request(
    work_dir: Path,
    spec: AudioRequestSpec,
    out_path: Path,
    *,
    provider_fn: Optional[ProviderFn] = None,
    mock_provider: Optional[MockAudioProvider] = None,
    use_mock: bool = False,
    skip_generation: bool = False,
    skip_reference: str = "",
) -> AudioGenerationResult:
    """fingerprint → idempotency → TTS → validate → provenance → checkpoint"""
    from pipeline.idempotency.mock_guard import assert_no_mock_in_production
    assert_no_mock_in_production(use_mock=use_mock, stage="audio")

    work_dir = Path(work_dir)
    out_path = Path(out_path)
    fingerprint = compute_audio_fingerprint(spec)
    asset_id = asset_id_from_fingerprint(fingerprint, spec.scene_id)
    executor = IdempotentExecutor(work_dir)
    cache = GenerationCache(work_dir)
    legacy_key = f"audio:{_legacy_audio_key(spec)}"
    inv_counter = {"n": 0}

    if skip_generation and skip_reference:
        ref = Path(skip_reference)
        if ref.is_file() and validate_audio_asset(str(ref))[0]:
            save_audio_provenance(
                work_dir,
                spec=spec,
                fingerprint=fingerprint,
                asset_path=str(ref),
                asset_hash=hash_artifact(str(ref)),
                extra={"skipped_tts": True, "reason": "embedded_audio"},
            )
            return AudioGenerationResult(
                success=True,
                path=ref,
                action="embedded_reuse",
                fingerprint=fingerprint,
                asset_id=asset_id,
                asset_hash=hash_artifact(str(ref)),
                provider_invocations=0,
            )

    def _run_provider() -> Path:
        if provider_fn is not None:
            inv_counter["n"] += 1
            return Path(provider_fn())
        if use_mock:
            mp = mock_provider or get_mock_audio_provider()
            return mp.synthesize(out_path=out_path, text=spec.dialogue_text)
        raise ValueError("provider_fn or use_mock required")

    def _execute() -> dict[str, Any]:
        req = cache.request_create(legacy_key, artifact=out_path)
        if req["action"] == "reuse" and Path(str(req.get("artifact") or "")).is_file():
            return {"artifact": str(req["artifact"]), "generation_id": "", "from_cache": True}
        art = _run_provider()
        cache.commit(legacy_key, art)
        gen_id = ""
        if use_mock and mock_provider:
            gen_id = mock_provider.last_generation_id
        elif use_mock:
            gen_id = get_mock_audio_provider().last_generation_id
        return {"artifact": str(art), "generation_id": gen_id, "from_cache": False}

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        return validate_audio_asset(str(out.get("artifact") or ""))

    def _persist(out: dict[str, Any]) -> str:
        art = str(out.get("artifact") or "")
        asset_hash = hash_artifact(art) if Path(art).is_file() else ""
        dur = probe_duration_sec(art)
        save_audio_provenance(
            work_dir,
            spec=spec,
            fingerprint=fingerprint,
            asset_path=art,
            asset_hash=asset_hash,
            generation_id=str(out.get("generation_id") or ""),
            duration_sec=dur,
            extra={"asset_id": asset_id, "legacy_key": legacy_key},
        )
        return art

    result = executor.execute(
        job_id=spec.job_id,
        stage="audio",
        entity_id=spec.entity_id,
        inputs=spec.normalized_inputs(),
        provider=spec.provider,
        model=spec.model,
        execute_fn=_execute,
        validate_fn=_validate,
        persist_fn=_persist,
    )

    if use_mock and mock_provider:
        provider_calls = mock_provider.invocation_count
    elif use_mock:
        provider_calls = get_mock_audio_provider().invocation_count
    else:
        provider_calls = inv_counter["n"]
    if result.action == "reuse":
        provider_calls = min(provider_calls, inv_counter["n"])

    path = Path(result.result_reference) if result.result_reference else None
    dur = probe_duration_sec(str(path)) if path and path.is_file() else None
    prov = load_audio_provenance(work_dir, fingerprint)
    gen_id = str((prov.get("provenance") or {}).get("generation_id") or "") if prov else ""

    return AudioGenerationResult(
        success=result.action in ("execute", "reuse", "embedded_reuse"),
        path=path if path and path.is_file() else None,
        action=result.action,
        fingerprint=fingerprint,
        asset_id=asset_id,
        asset_hash=result.result_hash,
        generation_id=gen_id,
        duration_sec=dur,
        provider_invocations=provider_calls if result.action == "execute" else 0,
        metrics=result.metrics,
        state=result.state,
    )
