"""Subtitle generation runtime — BUILD-04E."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.generation_cache import GenerationCache
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import hash_artifact, hash_text
from pipeline.idempotency.mock_subtitle_provider import MockSubtitleProvider, get_mock_subtitle_provider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.subtitle_provenance import load_subtitle_provenance, save_subtitle_provenance
from pipeline.idempotency.subtitle_request import SubtitleRequestSpec, compute_subtitle_fingerprint
from pipeline.idempotency.subtitle_validation import (
    validate_cue_timestamps,
    validate_subtitle_asset,
    validate_subtitle_bindings,
)

logger = logging.getLogger(__name__)

ProviderFn = Callable[[], dict[str, Any]]


@dataclass
class SubtitleGenerationResult:
    success: bool
    path: Optional[Path] = None
    action: str = ""
    fingerprint: str = ""
    srt_hash: str = ""
    generation_id: str = ""
    provider_invocations: int = 0
    metrics: dict[str, int] = field(default_factory=dict)
    state: IdempotencyState = IdempotencyState.NOT_STARTED


def execute_subtitle_request(
    work_dir: Path,
    spec: SubtitleRequestSpec,
    out_path: Path,
    *,
    provider_fn: Optional[ProviderFn] = None,
    mock_provider: Optional[MockSubtitleProvider] = None,
    use_mock: bool = False,
    skip_generation: bool = False,
    skip_reference: str = "",
) -> SubtitleGenerationResult:
    from pipeline.idempotency.mock_guard import assert_no_mock_in_production
    assert_no_mock_in_production(use_mock=use_mock, stage="subtitle")

    work_dir = Path(work_dir)
    out_path = Path(out_path)
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    temp_path = out_path.with_suffix(".tmp.srt")
    fingerprint = compute_subtitle_fingerprint(spec)
    executor = IdempotentExecutor(work_dir)
    cache = GenerationCache(work_dir)
    legacy_key = f"subtitle:{fingerprint[:32]}"
    inv_counter = {"n": 0}

    spec_meta = {
        "scene_id": spec.scene_id,
        "dialogue_id": spec.dialogue_id,
        "segment_id": spec.segment_id,
        "language": spec.language,
        "text_hash": hash_text(spec.localized_text.strip())[:32],
        "scene_duration_sec": spec.scene_duration_sec,
        "leading_gap_sec": spec.leading_gap_sec,
        "trailing_gap_sec": spec.trailing_gap_sec,
        "timing_model": spec.timing_model,
    }

    if skip_generation and skip_reference:
        ref = Path(skip_reference)
        ok, _ = validate_subtitle_asset(
            str(ref),
            spec_meta=spec_meta,
            expected_text_hash=spec_meta["text_hash"],
            audio_duration_sec=spec.audio_duration_sec,
        )
        if ok:
            save_subtitle_provenance(
                work_dir,
                spec=spec,
                fingerprint=fingerprint,
                srt_path=str(ref),
                srt_hash=hash_artifact(str(ref)),
            )
            return SubtitleGenerationResult(
                success=True,
                path=ref,
                action="embedded_reuse",
                fingerprint=fingerprint,
                srt_hash=hash_artifact(str(ref)),
                provider_invocations=0,
            )

    existing = executor.store.get(fingerprint)
    if existing and existing.request_state == IdempotencyState.SUCCEEDED and existing.result_reference:
        ok, reason = validate_subtitle_asset(
            existing.result_reference,
            spec_meta=spec_meta,
            expected_text_hash=spec_meta["text_hash"],
            audio_duration_sec=spec.audio_duration_sec,
        )
        if not ok:
            existing.request_state = IdempotencyState.FAILED_RETRYABLE
            existing.metadata["invalid_reuse"] = reason
            executor.store.put(existing)

    def _run_provider() -> dict[str, Any]:
        if provider_fn is not None:
            inv_counter["n"] += 1
            return provider_fn()
        if use_mock:
            mp = mock_provider or get_mock_subtitle_provider()
            inv_counter["n"] += 1
            return mp.generate(
                text=spec.localized_text,
                audio_duration_sec=spec.audio_duration_sec,
                scene_id=spec.scene_id,
                dialogue_id=spec.dialogue_id,
                segment_id=spec.segment_id,
                language=spec.language,
            )
        raise ValueError("provider_fn or use_mock required")

    def _execute() -> dict[str, Any]:
        req = cache.request_create(legacy_key, artifact=out_path)
        if req["action"] == "reuse" and Path(str(req.get("artifact") or "")).is_file():
            return {"artifact": str(req["artifact"]), "generation_id": "", "from_cache": True}
        out = _run_provider()
        if out.get("cues"):
            ok, reason = validate_cue_timestamps(out["cues"])
            if not ok:
                raise ValueError(f"provider_cue_validation:{reason}")
            ok, reason = validate_subtitle_bindings(
                out["cues"],
                expected_scene_id=spec.scene_id,
                expected_dialogue_id=spec.dialogue_id,
                expected_language=spec.language,
                expected_segment_id=spec.segment_id,
            )
            if not ok:
                raise ValueError(f"provider_cue_validation:{reason}")
        srt_body = str(out.get("srt") or "")
        if not srt_body and out.get("cues"):
            from pipeline.idempotency.subtitle_engine import cues_to_srt_file

            srt_body = cues_to_srt_file(out["cues"])
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(srt_body, encoding="utf-8")
        meta_path.write_text(json.dumps({**spec_meta, "fingerprint": fingerprint}, indent=2), encoding="utf-8")
        os.replace(str(temp_path), str(out_path))
        cache.commit(legacy_key, out_path)
        gen_id = ""
        if use_mock and mock_provider:
            gen_id = mock_provider.last_generation_id
        elif use_mock:
            gen_id = get_mock_subtitle_provider().last_generation_id
        return {"artifact": str(out_path), "generation_id": gen_id, "from_cache": False, "cues": out.get("cues")}

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        art = str(out.get("artifact") or "")
        return validate_subtitle_asset(
            art,
            spec_meta=spec_meta,
            expected_text_hash=spec_meta["text_hash"],
            audio_duration_sec=spec.audio_duration_sec,
        )

    def _persist(out: dict[str, Any]) -> str:
        art = str(out.get("artifact") or "")
        srt_hash = hash_artifact(art) if Path(art).is_file() else ""
        save_subtitle_provenance(
            work_dir,
            spec=spec,
            fingerprint=fingerprint,
            srt_path=art,
            srt_hash=srt_hash,
            generation_id=str(out.get("generation_id") or ""),
        )
        return art

    result = executor.execute(
        job_id=spec.job_id,
        stage="subtitle",
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
        provider_calls = get_mock_subtitle_provider().invocation_count
    else:
        provider_calls = inv_counter["n"]
    if result.action == "reuse":
        provider_calls = min(provider_calls, inv_counter["n"])

    path = Path(result.result_reference) if result.result_reference else None
    prov = load_subtitle_provenance(work_dir, fingerprint)
    gen_id = str(prov.get("generation_id") or "") if prov else ""

    return SubtitleGenerationResult(
        success=result.action in ("execute", "reuse", "embedded_reuse"),
        path=path if path and path.is_file() else None,
        action=result.action,
        fingerprint=fingerprint,
        srt_hash=result.result_hash,
        generation_id=gen_id,
        provider_invocations=provider_calls if result.action == "execute" else 0,
        metrics=result.metrics,
        state=result.state,
    )
