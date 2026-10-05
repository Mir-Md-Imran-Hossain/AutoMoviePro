"""Quality evaluation fingerprint (BUILD-04F)."""
from __future__ import annotations

from typing import Any

from pipeline.idempotency.fingerprint import compute_fingerprint
from pipeline.quality.contracts import EVALUATOR_VERSION, QUALITY_CONTRACT_VERSION, RULE_VERSION


def normalized_quality_inputs(
    *,
    artifact_fingerprint: str,
    stage: str = "",
    evaluator_version: str = EVALUATOR_VERSION,
    rule_version: str = RULE_VERSION,
    extra_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inputs = {
        "artifact_fingerprint": artifact_fingerprint.strip(),
        "evaluator_version": evaluator_version.strip(),
        "rule_version": rule_version.strip(),
        "stage": stage.strip(),
        "quality_contract_version": QUALITY_CONTRACT_VERSION,
    }
    if extra_inputs:
        inputs.update(extra_inputs)
    return inputs


def compute_quality_fingerprint(
    *,
    job_id: str,
    subject_id: str,
    stage: str,
    artifact_fingerprint: str,
    evaluator_version: str = EVALUATOR_VERSION,
    rule_version: str = RULE_VERSION,
    extra_inputs: dict[str, Any] | None = None,
) -> str:
    inputs = normalized_quality_inputs(
        artifact_fingerprint=artifact_fingerprint,
        stage=stage,
        evaluator_version=evaluator_version,
        rule_version=rule_version,
        extra_inputs=extra_inputs,
    )
    return compute_fingerprint(
        job_id=job_id,
        stage="quality",
        entity_id=f"cq-{stage}-{subject_id}",
        contract_version=QUALITY_CONTRACT_VERSION,
        provider="quality_evaluator",
        model=evaluator_version,
        inputs=inputs,
    )
