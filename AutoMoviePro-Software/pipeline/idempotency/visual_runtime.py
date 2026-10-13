"""Visual generation runtime — BUILD-04A integration layer."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.generation_cache import GenerationCache, make_generation_key
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import hash_artifact
from pipeline.idempotency.mock_visual_provider import MockVisualProvider, get_mock_provider
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.visual_provenance import (
    asset_id_from_fingerprint,
    load_visual_provenance,
    save_visual_provenance,
)
from pipeline.idempotency.visual_request import (
    GenerationMode,
    VisualRequestSpec,
    compute_visual_fingerprint,
)
from pipeline.idempotency.visual_validation import validate_visual_asset
from pipeline.remote_job_store import get_remote_job, save_remote_job

logger = logging.getLogger(__name__)

ProviderFn = Callable[[], Optional[Path]]


@dataclass
class VisualGenerationResult:
    success: bool
    path: Optional[Path] = None
    action: str = ""
    fingerprint: str = ""
    asset_id: str = ""
    asset_hash: str = ""
    generation_id: str = ""
    provider_invocations: int = 0
    metrics: dict[str, int] = field(default_factory=dict)
    state: IdempotencyState = IdempotencyState.NOT_STARTED
    provenance_path: str = ""
    detail: str = ""


def _legacy_key(spec: VisualRequestSpec) -> str:
    return make_generation_key(
        scene_id=spec.scene_id,
        claim_id=spec.entity_id,
        narration=spec.narration_hint,
        visual_prompt=spec.prompt or spec.visual_prompt,
        provider=spec.provider,
        model=spec.model,
        size=spec.size,
    )


def execute_visual_request(
    work_dir: Path,
    spec: VisualRequestSpec,
    out_path: Path,
    *,
    provider_fn: Optional[ProviderFn] = None,
    mock_provider: Optional[MockVisualProvider] = None,
    use_mock: bool = False,
    fallback_provider_fn: Optional[ProviderFn] = None,
) -> VisualGenerationResult:
    """
    BUILD-04A runtime entry:
    fingerprint → idempotency → provider → validate → provenance → checkpoint
    """
    from pipeline.idempotency.mock_guard import assert_no_mock_in_production
    assert_no_mock_in_production(use_mock=use_mock, stage="visual")

    work_dir = Path(work_dir)
    out_path = Path(out_path)
    fingerprint = compute_visual_fingerprint(spec)
    asset_id = asset_id_from_fingerprint(fingerprint, spec.scene_id)
    executor = IdempotentExecutor(work_dir)
    cache = GenerationCache(work_dir)
    legacy_key = _legacy_key(spec)
    inv_counter = {"n": 0}

    mode_str = "image" if spec.generation_mode == GenerationMode.IMAGE_GENERATION else "video"
    # C05-MR: image-derived mp4/webm containers must validate as video assets
    if Path(out_path).suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"}:
        mode_str = "video"

    def _run_provider() -> Path:
        if provider_fn is not None:
            inv_counter["n"] += 1
            result = provider_fn()
            if result is None:
                raise TimeoutError("provider returned no result — state may be unknown")
            return Path(result)
        if use_mock:
            mp = mock_provider or get_mock_provider()
            return mp.generate(out_path=out_path, prompt=spec.prompt, seed=spec.seed)
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
        elif mock_provider is None and not use_mock:
            gen_id = str(int(time.time()))
        if gen_id and not use_mock:
            save_remote_job(
                work_dir,
                generation_key=legacy_key,
                remote_job_id=gen_id,
                provider=spec.provider,
                scene_id=spec.scene_id,
                status="done",
            )
        return {"artifact": str(art), "generation_id": gen_id, "from_cache": False}

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        art = str(out.get("artifact") or "")
        return validate_visual_asset(art, mode=mode_str)

    def _persist(out: dict[str, Any]) -> str:
        art = str(out.get("artifact") or "")
        asset_hash = hash_artifact(art) if Path(art).is_file() else ""
        save_visual_provenance(
            work_dir,
            spec=spec,
            fingerprint=fingerprint,
            asset_path=art,
            asset_hash=asset_hash,
            generation_id=str(out.get("generation_id") or ""),
            requested_seed=spec.seed,
            actual_seed=spec.seed,
            extra={"asset_id": asset_id, "legacy_key": legacy_key},
        )
        return art

    result = executor.execute(
        job_id=spec.job_id,
        stage="visual",
        entity_id=spec.entity_id,
        inputs=spec.normalized_inputs(),
        provider=spec.provider,
        model=spec.model,
        execute_fn=_execute,
        validate_fn=_validate,
        persist_fn=_persist,
        force_regenerate=spec.force_regenerate,
    )

    if use_mock:
        mp = mock_provider or get_mock_provider()
        provider_calls = mp.invocation_count
    else:
        provider_calls = inv_counter["n"]

    if result.action in ("failed", "unknown"):
        pass  # caller handles fallback with distinct identity (BUILD-04A)

    path = Path(result.result_reference) if result.result_reference else None
    prov = load_visual_provenance(work_dir, fingerprint)
    gen_id = ""
    if prov:
        gen_id = str((prov.get("provenance") or {}).get("generation_id") or "")

    return VisualGenerationResult(
        success=result.action in ("execute", "reuse"),
        path=path if path and path.is_file() else None,
        action=result.action,
        fingerprint=fingerprint,
        asset_id=asset_id,
        asset_hash=result.result_hash,
        generation_id=gen_id,
        provider_invocations=provider_calls,
        metrics=result.metrics,
        state=result.state,
        provenance_path=str(provenance_path(work_dir, fingerprint)) if prov else "",
    )


def provenance_path(work_dir: Path, fingerprint: str) -> Path:
    from pipeline.idempotency.visual_provenance import provenance_path as _pp

    return _pp(work_dir, fingerprint)


def reconcile_visual_unknown(
    work_dir: Path,
    spec: VisualRequestSpec,
    *,
    local_artifact: str = "",
) -> VisualGenerationResult:
    """Reconcile UNKNOWN using local artifact or remote job store."""
    from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore
    from pipeline.idempotency.unknown_result import reconcile_unknown

    fingerprint = compute_visual_fingerprint(spec)
    store = IdempotencyStore(Path(work_dir) / "idempotency")
    rec = store.get(fingerprint)
    if not rec:
        return VisualGenerationResult(success=False, action="not_found", fingerprint=fingerprint)
    legacy_key = _legacy_key(spec)
    remote = get_remote_job(work_dir, legacy_key)
    recon = reconcile_unknown(
        store,
        rec,
        remote_job_lookup=remote,
        local_artifact_path=local_artifact or rec.result_reference,
    )
    if recon.resolved and recon.result_reference:
        ok, _ = validate_visual_asset(recon.result_reference)
        if ok:
            return VisualGenerationResult(
                success=True,
                path=Path(recon.result_reference),
                action="reconciled",
                fingerprint=fingerprint,
                state=recon.new_state,
            )
    return VisualGenerationResult(
        success=False,
        action="unknown",
        fingerprint=fingerprint,
        state=IdempotencyState.UNKNOWN,
    )
