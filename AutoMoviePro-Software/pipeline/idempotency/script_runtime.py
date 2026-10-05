"""Script generation runtime — BUILD-04C integration layer."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.generation_cache import GenerationCache
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import hash_artifact, hash_text
from pipeline.idempotency.mock_script_provider import MockScriptProvider, get_mock_script_provider
from pipeline.idempotency.script_provenance import load_script_provenance, save_script_provenance
from pipeline.idempotency.script_request import ScriptRequestSpec, compute_script_fingerprint
from pipeline.idempotency.script_validation import validate_plan_and_script
from pipeline.idempotency.states import IdempotencyState

logger = logging.getLogger(__name__)

ProviderFn = Callable[[], dict[str, Any]]


@dataclass
class ScriptGenerationResult:
    success: bool
    plan: Optional[dict[str, Any]] = None
    plan_path: Optional[Path] = None
    action: str = ""
    fingerprint: str = ""
    plan_hash: str = ""
    generation_id: str = ""
    provider_invocations: int = 0
    metrics: dict[str, int] = field(default_factory=dict)
    state: IdempotencyState = IdempotencyState.NOT_STARTED


def execute_script_request(
    work_dir: Path,
    spec: ScriptRequestSpec,
    out_path: Path,
    *,
    provider_fn: Optional[ProviderFn] = None,
    mock_provider: Optional[MockScriptProvider] = None,
    use_mock: bool = False,
    skip_generation: bool = False,
    skip_reference: str = "",
) -> ScriptGenerationResult:
    """fingerprint → idempotency → script gen → validate → provenance → checkpoint"""
    work_dir = Path(work_dir)
    out_path = Path(out_path)
    fingerprint = compute_script_fingerprint(spec)
    if not skip_generation:
        from pipeline.creative_production.preflight import preflight_script_generation_request

        preflight_script_generation_request(spec, block=True)
    executor = IdempotentExecutor(work_dir)
    cache = GenerationCache(work_dir)
    legacy_key = f"script:{fingerprint[:32]}"
    inv_counter = {"n": 0}

    existing = executor.store.get(fingerprint)
    if existing and existing.request_state == IdempotencyState.SUCCEEDED and existing.result_reference:
        try:
            ref_plan = json.loads(Path(existing.result_reference).read_text(encoding="utf-8"))
            ok, reason = validate_plan_and_script(ref_plan)
            if not ok:
                existing.request_state = IdempotencyState.FAILED_RETRYABLE
                existing.metadata["invalid_reuse"] = reason
                executor.store.put(existing)
        except Exception as exc:
            existing.request_state = IdempotencyState.FAILED_RETRYABLE
            existing.metadata["invalid_reuse"] = str(exc)[:120]
            executor.store.put(existing)

    if skip_generation and skip_reference:
        ref = Path(skip_reference)
        if ref.is_file():
            try:
                plan = json.loads(ref.read_text(encoding="utf-8"))
                ok, _ = validate_plan_and_script(plan)
                if ok:
                    save_script_provenance(
                        work_dir,
                        spec=spec,
                        fingerprint=fingerprint,
                        plan_path=str(ref),
                        plan_hash=hash_artifact(str(ref)),
                        extra={"skipped_generation": True, "reason": "existing_plan"},
                    )
                    return ScriptGenerationResult(
                        success=True,
                        plan=plan,
                        plan_path=ref,
                        action="embedded_reuse",
                        fingerprint=fingerprint,
                        plan_hash=hash_artifact(str(ref)),
                        provider_invocations=0,
                    )
            except Exception:
                pass

    def _run_provider() -> dict[str, Any]:
        if provider_fn is not None:
            inv_counter["n"] += 1
            return provider_fn()
        if use_mock:
            mp = mock_provider or get_mock_script_provider()
            inv_counter["n"] += 1
            return mp.generate(topic=spec.topic, niche=spec.niche)
        raise ValueError("provider_fn or use_mock required")

    def _execute() -> dict[str, Any]:
        req = cache.request_create(legacy_key, artifact=out_path)
        if req["action"] == "reuse" and Path(str(req.get("artifact") or "")).is_file():
            try:
                plan = json.loads(Path(str(req["artifact"])).read_text(encoding="utf-8"))
                return {
                    "plan": plan,
                    "artifact": str(req["artifact"]),
                    "generation_id": "",
                    "from_cache": True,
                }
            except Exception:
                pass
        plan = _run_provider()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        cache.commit(legacy_key, out_path)
        gen_id = ""
        if use_mock and mock_provider:
            gen_id = mock_provider.last_generation_id
        elif use_mock:
            gen_id = get_mock_script_provider().last_generation_id
        return {
            "plan": plan,
            "artifact": str(out_path),
            "generation_id": gen_id,
            "from_cache": False,
        }

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        plan = out.get("plan")
        if not isinstance(plan, dict):
            art = str(out.get("artifact") or "")
            if art and Path(art).is_file():
                try:
                    plan = json.loads(Path(art).read_text(encoding="utf-8"))
                except Exception:
                    return False, "malformed_json"
            else:
                return False, "empty_response"
        return validate_plan_and_script(plan)

    def _persist(out: dict[str, Any]) -> str:
        art = str(out.get("artifact") or "")
        plan_hash = hash_artifact(art) if Path(art).is_file() else hash_text(json.dumps(out.get("plan") or {}))
        save_script_provenance(
            work_dir,
            spec=spec,
            fingerprint=fingerprint,
            plan_path=art,
            plan_hash=plan_hash,
            generation_id=str(out.get("generation_id") or ""),
            extra={"legacy_key": legacy_key},
        )
        return art

    result = executor.execute(
        job_id=spec.job_id,
        stage="script",
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
        provider_calls = get_mock_script_provider().invocation_count
    else:
        provider_calls = inv_counter["n"]
    if result.action == "reuse":
        provider_calls = min(provider_calls, inv_counter["n"])

    plan = None
    path = Path(result.result_reference) if result.result_reference else None
    if path and path.is_file():
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            plan = None
    elif isinstance(result.output, dict) and result.output.get("plan"):
        plan = result.output.get("plan")

    prov = load_script_provenance(work_dir, fingerprint)
    gen_id = str(prov.get("generation_id") or "") if prov else ""

    return ScriptGenerationResult(
        success=result.action in ("execute", "reuse", "embedded_reuse"),
        plan=plan,
        plan_path=path if path and path.is_file() else None,
        action=result.action,
        fingerprint=fingerprint,
        plan_hash=result.result_hash,
        generation_id=gen_id,
        provider_invocations=provider_calls if result.action == "execute" else 0,
        metrics=result.metrics,
        state=result.state,
    )
