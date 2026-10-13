"""Render/assembly runtime — BUILD-04D integration layer."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.generation_cache import GenerationCache
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import hash_artifact
from pipeline.idempotency.mock_render_provider import MockRenderProvider, get_mock_render_provider
from pipeline.idempotency.render_provenance import load_render_provenance, save_render_provenance
from pipeline.idempotency.render_request import RenderRequestSpec, compute_render_fingerprint
from pipeline.idempotency.render_validation import validate_render_output
from pipeline.idempotency.states import IdempotencyState

logger = logging.getLogger(__name__)

ProviderFn = Callable[[Path], Path]


@dataclass
class RenderGenerationResult:
    success: bool
    path: Optional[Path] = None
    action: str = ""
    fingerprint: str = ""
    output_hash: str = ""
    generation_id: str = ""
    provider_invocations: int = 0
    metrics: dict[str, int] = field(default_factory=dict)
    state: IdempotencyState = IdempotencyState.NOT_STARTED


def execute_render_request(
    work_dir: Path,
    spec: RenderRequestSpec,
    out_path: Path,
    *,
    provider_fn: Optional[ProviderFn] = None,
    mock_provider: Optional[MockRenderProvider] = None,
    use_mock: bool = False,
    skip_generation: bool = False,
    skip_reference: str = "",
) -> RenderGenerationResult:
    """manifest → fingerprint → idempotency → render → validate → atomic promote → provenance → checkpoint"""
    from pipeline.idempotency.mock_guard import assert_no_mock_in_production
    assert_no_mock_in_production(use_mock=use_mock, stage="render")

    work_dir = Path(work_dir)
    out_path = Path(out_path)
    temp_path = out_path.with_name(out_path.stem + ".tmp" + out_path.suffix)
    fingerprint = compute_render_fingerprint(spec)
    executor = IdempotentExecutor(work_dir)
    cache = GenerationCache(work_dir)
    legacy_key = f"render:{fingerprint[:32]}"
    inv_counter = {"n": 0}
    cfg = spec.manifest.normalized().get("output_config") or {}

    if skip_generation and skip_reference:
        ref = Path(skip_reference)
        ok, _ = validate_render_output(
            str(ref),
            expected_size=str(cfg.get("size") or ""),
            require_audio=True,
            require_video=True,
        )
        if ok:
            save_render_provenance(
                work_dir,
                spec=spec,
                fingerprint=fingerprint,
                output_path=str(ref),
                output_hash=hash_artifact(str(ref)),
                extra={"skipped_render": True},
            )
            return RenderGenerationResult(
                success=True,
                path=ref,
                action="embedded_reuse",
                fingerprint=fingerprint,
                output_hash=hash_artifact(str(ref)),
                provider_invocations=0,
            )

    existing = executor.store.get(fingerprint)
    if existing and existing.request_state == IdempotencyState.SUCCEEDED and existing.result_reference:
        ok, reason = validate_render_output(
            existing.result_reference,
            expected_size=str(cfg.get("size") or ""),
            require_audio=True,
            require_video=True,
        )
        if not ok:
            existing.request_state = IdempotencyState.FAILED_RETRYABLE
            existing.metadata["invalid_reuse"] = reason
            executor.store.put(existing)

    def _run_provider(tmp: Path) -> Path:
        if provider_fn is not None:
            inv_counter["n"] += 1
            return Path(provider_fn(tmp))
        if use_mock:
            mp = mock_provider or get_mock_render_provider()
            inv_counter["n"] += 1
            return mp.render(out_path=tmp)
        raise ValueError("provider_fn or use_mock required")

    def _execute() -> dict[str, Any]:
        req = cache.request_create(legacy_key, artifact=out_path)
        if req["action"] == "reuse" and Path(str(req.get("artifact") or "")).is_file():
            art = str(req["artifact"])
            return {"artifact": art, "generation_id": "", "from_cache": True}
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        art_path = _run_provider(temp_path)
        if not art_path.is_file():
            raise RuntimeError("render produced no output")
        expected_dur = sum(
            float(s.get("duration_sec") or 0)
            for s in (spec.manifest.normalized().get("scenes") or [])
        )
        ok_pre, reason_pre = validate_render_output(
            str(art_path),
            expected_size=str(cfg.get("size") or ""),
            expected_duration_sec=expected_dur if expected_dur > 0 else None,
            require_audio=True,
            require_video=True,
        )
        if not ok_pre:
            try:
                art_path.unlink()
            except Exception:
                pass
            raise RuntimeError(f"invalid render output: {reason_pre}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(art_path), str(out_path))
        if temp_path.exists() and temp_path != out_path:
            try:
                temp_path.unlink()
            except Exception:
                pass
        cache.commit(legacy_key, out_path)
        gen_id = ""
        if use_mock and mock_provider:
            gen_id = mock_provider.last_generation_id
        elif use_mock:
            gen_id = get_mock_render_provider().last_generation_id
        return {"artifact": str(out_path), "generation_id": gen_id, "from_cache": False}

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        art = str(out.get("artifact") or "")
        expected_dur = sum(
            float(s.get("duration_sec") or 0)
            for s in (spec.manifest.normalized().get("scenes") or [])
        )
        return validate_render_output(
            art,
            expected_size=str(cfg.get("size") or ""),
            expected_duration_sec=expected_dur if expected_dur > 0 else None,
            require_audio=True,
            require_video=True,
        )

    def _persist(out: dict[str, Any]) -> str:
        art = str(out.get("artifact") or "")
        out_hash = hash_artifact(art) if Path(art).is_file() else ""
        save_render_provenance(
            work_dir,
            spec=spec,
            fingerprint=fingerprint,
            output_path=art,
            output_hash=out_hash,
            generation_id=str(out.get("generation_id") or ""),
            extra={"legacy_key": legacy_key},
        )
        return art

    result = executor.execute(
        job_id=spec.job_id,
        stage="render",
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
        provider_calls = get_mock_render_provider().invocation_count
    else:
        provider_calls = inv_counter["n"]
    if result.action == "reuse":
        provider_calls = min(provider_calls, inv_counter["n"])

    path = Path(result.result_reference) if result.result_reference else None
    prov = load_render_provenance(work_dir, fingerprint)
    gen_id = str(prov.get("generation_id") or "") if prov else ""

    return RenderGenerationResult(
        success=result.action in ("execute", "reuse", "embedded_reuse"),
        path=path if path and path.is_file() else None,
        action=result.action,
        fingerprint=fingerprint,
        output_hash=result.result_hash,
        generation_id=gen_id,
        provider_invocations=provider_calls if result.action == "execute" else 0,
        metrics=result.metrics,
        state=result.state,
    )
