"""FactPack stage pilot — first BUILD-03 runtime integration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.fact_pack import build_fact_pack
from pipeline.idempotency.executor import IdempotentExecutor


def idempotent_build_fact_pack(
    work_dir: Path,
    *,
    job_id: str,
    topic: str,
    notes: str = "",
    claims: Optional[list] = None,
    entity_id: str = "",
) -> Dict[str, Any]:
    """
    Pilot stage: deterministic, offline, low-risk.
    Selected because factpack has clear JSON output and no paid API.
    """
    entity = entity_id or f"topic-{topic.strip().lower()[:64]}"
    executor = IdempotentExecutor(work_dir)
    out_path = Path(work_dir) / "factpack" / f"{entity}.json"
    execution_count = {"n": 0}

    def _execute() -> dict[str, Any]:
        execution_count["n"] += 1
        return build_fact_pack(topic, notes=notes, claims=claims)

    def _validate(pack: dict[str, Any]) -> tuple[bool, str]:
        if not pack.get("claims"):
            return False, "no_claims"
        return True, "ok"

    def _persist(pack: dict[str, Any]) -> str:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(out_path)

    result = executor.execute(
        job_id=job_id,
        stage="factpack",
        entity_id=entity,
        inputs={"topic": topic, "notes": notes, "claims": claims or []},
        execute_fn=_execute,
        validate_fn=_validate,
        persist_fn=_persist,
    )

    output = None
    if result.result_reference and Path(result.result_reference).is_file():
        output = json.loads(Path(result.result_reference).read_text(encoding="utf-8"))

    return {
        "action": result.action,
        "fingerprint": result.fingerprint,
        "fact_pack": output,
        "result_reference": result.result_reference,
        "execution_count": execution_count["n"],
        "metrics": result.metrics,
    }
