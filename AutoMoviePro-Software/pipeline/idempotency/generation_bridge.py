"""Generation cache + BUILD-03 idempotency bridge."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from pipeline.generation_cache import GenerationCache, make_generation_key
from pipeline.idempotency.executor import IdempotentExecutor
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_artifact


def idempotent_generation_request(
    work_dir: Path,
    *,
    job_id: str,
    scene_id: int,
    claim_id: str = "",
    narration: str = "",
    visual_prompt: str = "",
    provider: str = "",
    model: str = "",
    size: str = "",
    artifact: Optional[Path] = None,
    generate_fn: Optional[Callable[[], Path]] = None,
) -> Dict[str, Any]:
    """
    Wrap GenerationCache with BUILD-03 claim/validate/checkpoint.
    Returns legacy-compatible dict plus idempotency fields.
    """
    legacy_key = make_generation_key(
        scene_id=scene_id,
        claim_id=claim_id,
        narration=narration,
        visual_prompt=visual_prompt,
        provider=provider,
        model=model,
        size=size,
    )
    fingerprint = compute_fingerprint(
        job_id=job_id,
        stage="visual",
        entity_id=f"scene-{scene_id}",
        provider=provider,
        model=model,
        inputs={
            "legacy_key": legacy_key,
            "claim_id": claim_id,
            "narration": narration,
            "visual_prompt": visual_prompt[:500],
            "size": size,
        },
    )
    cache = GenerationCache(work_dir)
    executor = IdempotentExecutor(work_dir)

    def _execute() -> dict[str, Any]:
        req = cache.request_create(legacy_key, artifact=artifact)
        if req["action"] == "reuse":
            return req
        if generate_fn is None:
            raise ValueError("generate_fn required for create path")
        art = generate_fn()
        cache.commit(legacy_key, art)
        return {"action": "create", "artifact": str(art), "key": legacy_key}

    def _validate(out: dict[str, Any]) -> tuple[bool, str]:
        art = str(out.get("artifact") or "")
        if not art:
            return False, "no_artifact"
        p = Path(art)
        if not p.is_file() or p.stat().st_size < 1000:
            return False, "artifact_invalid"
        return True, "ok"

    def _persist(out: dict[str, Any]) -> str:
        return str(out.get("artifact") or "")

    result = executor.execute(
        job_id=job_id,
        stage="visual",
        entity_id=f"scene-{scene_id}",
        inputs={"legacy_key": legacy_key},
        provider=provider,
        model=model,
        execute_fn=_execute,
        validate_fn=_validate,
        persist_fn=_persist,
    )

    out: Dict[str, Any] = {
        "key": legacy_key,
        "fingerprint": result.fingerprint,
        "idempotency_action": result.action,
        "artifact": result.result_reference,
        "create_count": cache.stats()["create_count"],
        "reuse_count": cache.stats()["reuse_count"],
    }
    if result.action == "reuse":
        out["action"] = "reuse"
    elif result.action == "execute":
        out["action"] = "create"
    elif result.action == "duplicate_prevented":
        out["action"] = "duplicate_prevented"
    else:
        out["action"] = result.action
    return out
