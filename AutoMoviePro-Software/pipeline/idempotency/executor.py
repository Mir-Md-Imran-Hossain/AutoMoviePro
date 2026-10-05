"""Idempotent execution orchestration (BUILD-03)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from domain.enums import JobState
from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_artifact, hash_text
from pipeline.idempotency.identity import ExecutionIdentity
from pipeline.idempotency.result_validation import validate_file_result, validate_json_result
from pipeline.idempotency.retry_policy import RetryClass, retry_decision
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore

logger = logging.getLogger(__name__)


@dataclass
class IdempotentResult:
    action: str  # reuse | execute | duplicate_prevented | failed | unknown
    fingerprint: str
    result_reference: str = ""
    result_hash: str = ""
    output: Any = None
    state: IdempotencyState = IdempotencyState.NOT_STARTED
    metrics: dict[str, int] = field(default_factory=dict)


ExecuteFn = Callable[[], Any]
ValidateFn = Callable[[Any], tuple[bool, str]]
PersistFn = Callable[[Any], str]


class IdempotentExecutor:
    """
    Surgical wrapper: claim → execute/reuse → validate → persist → checkpoint.
    Does NOT replace legacy execution functions.
    """

    def __init__(self, work_dir: Path, *, max_attempts: int = 3, stale_sec: float = 3600):
        self.work_dir = Path(work_dir)
        self.store = IdempotencyStore(self.work_dir / "idempotency", stale_sec=stale_sec)
        self.checkpoint_store = CheckpointStore(self.work_dir / "checkpoints")
        self.max_attempts = max_attempts

    def execute(
        self,
        *,
        job_id: str,
        stage: str,
        entity_id: str,
        inputs: dict[str, Any],
        provider: str = "",
        model: str = "",
        execute_fn: ExecuteFn,
        validate_fn: Optional[ValidateFn] = None,
        persist_fn: Optional[PersistFn] = None,
        worker_id: str = "",
        force_regenerate: bool = False,
    ) -> IdempotentResult:
        fingerprint = compute_fingerprint(
            job_id=job_id,
            stage=stage,
            entity_id=entity_id,
            provider=provider,
            model=model,
            inputs=inputs,
        )
        identity = ExecutionIdentity.from_parts(job_id, stage, entity_id, fingerprint)

        if force_regenerate:
            # Controlled new generation — new entity_id required by caller; same fingerprint blocked
            pass

        record = IdempotencyRecord(
            fingerprint=fingerprint,
            job_id=job_id,
            stage=stage,
            entity_id=entity_id,
            provider=provider,
            max_attempts=self.max_attempts,
        )

        existing = self.store.get(fingerprint)
        if existing and existing.request_state == IdempotencyState.SUCCEEDED and not force_regenerate:
            ok, reason = self._validate_existing(existing)
            if ok:
                self.store.increment_metric("result_reused")
                logger.info(
                    "idempotency reuse job=%s stage=%s fp=%s",
                    job_id,
                    stage,
                    fingerprint[:12],
                )
                return IdempotentResult(
                    action="reuse",
                    fingerprint=fingerprint,
                    result_reference=existing.result_reference,
                    result_hash=existing.result_hash,
                    state=IdempotencyState.SUCCEEDED,
                    metrics=self.store.metrics(),
                )
            existing.request_state = IdempotencyState.FAILED_RETRYABLE
            existing.metadata["invalid_reuse"] = reason
            self.store.put(existing)

        claimed, prior = self.store.atomic_claim(record, worker_id=worker_id)
        if not claimed:
            if prior and prior.request_state == IdempotencyState.SUCCEEDED:
                ok, reason = self._validate_existing(prior)
                if ok:
                    self.store.increment_metric("result_reused")
                    return IdempotentResult(
                        action="reuse",
                        fingerprint=fingerprint,
                        result_reference=prior.result_reference,
                        result_hash=prior.result_hash,
                        state=IdempotencyState.SUCCEEDED,
                        metrics=self.store.metrics(),
                    )
            if prior and prior.request_state == IdempotencyState.IN_PROGRESS:
                waited = self._wait_for_completion(fingerprint, timeout_sec=30.0)
                if waited and waited.request_state == IdempotencyState.SUCCEEDED:
                    ok, reason = self._validate_existing(waited)
                    if ok:
                        self.store.increment_metric("result_reused")
                        return IdempotentResult(
                            action="reuse",
                            fingerprint=fingerprint,
                            result_reference=waited.result_reference,
                            result_hash=waited.result_hash,
                            state=IdempotencyState.SUCCEEDED,
                            metrics=self.store.metrics(),
                        )
                self.store.increment_metric("duplicate_prevented")
                return IdempotentResult(
                    action="duplicate_prevented",
                    fingerprint=fingerprint,
                    state=IdempotencyState.IN_PROGRESS,
                    metrics=self.store.metrics(),
                )
            if prior and prior.request_state == IdempotencyState.UNKNOWN:
                from pipeline.idempotency.unknown_result import reconcile_unknown

                recon = reconcile_unknown(
                    self.store,
                    prior,
                    local_artifact_path=prior.result_reference or "",
                )
                if recon.resolved:
                    self.store.increment_metric("result_reused")
                    return IdempotentResult(
                        action="reuse",
                        fingerprint=fingerprint,
                        result_reference=recon.result_reference or prior.result_reference,
                        result_hash=recon.result_hash or prior.result_hash,
                        state=IdempotencyState.SUCCEEDED,
                        metrics=self.store.metrics(),
                    )
                return IdempotentResult(
                    action="unknown",
                    fingerprint=fingerprint,
                    state=IdempotencyState.UNKNOWN,
                    metrics=self.store.metrics(),
                )
            if prior and prior.request_state == IdempotencyState.FAILED_FINAL:
                return IdempotentResult(
                    action="failed",
                    fingerprint=fingerprint,
                    state=IdempotencyState.FAILED_FINAL,
                    metrics=self.store.metrics(),
                )
            # Never execute without a successful claim.
            terminal = prior.request_state if prior else IdempotencyState.IN_PROGRESS
            self.store.increment_metric("duplicate_prevented")
            return IdempotentResult(
                action="duplicate_prevented",
                fingerprint=fingerprint,
                state=terminal,
                metrics=self.store.metrics(),
            )

        try:
            output = execute_fn()
        except Exception as exc:
            attempt = (prior.attempt if prior else 1)
            decision = retry_decision(exc=exc, attempt=attempt, max_attempts=self.max_attempts)
            rec = self.store.get(fingerprint) or record
            if decision.retry_class == RetryClass.UNKNOWN:
                rec.request_state = IdempotencyState.UNKNOWN
                rec.metadata["error"] = decision.reason
                self.store.put(rec)
                self.store.increment_metric("unknown_count")
                return IdempotentResult(
                    action="unknown",
                    fingerprint=fingerprint,
                    state=IdempotencyState.UNKNOWN,
                    metrics=self.store.metrics(),
                )
            if decision.should_retry:
                rec.request_state = IdempotencyState.FAILED_RETRYABLE
                rec.metadata["error"] = decision.reason
                self.store.put(rec)
                self.store.increment_metric("retry_count")
                return IdempotentResult(
                    action="failed",
                    fingerprint=fingerprint,
                    state=IdempotencyState.FAILED_RETRYABLE,
                    metrics=self.store.metrics(),
                )
            rec.request_state = IdempotencyState.FAILED_FINAL
            rec.metadata["error"] = decision.reason
            self.store.put(rec)
            return IdempotentResult(
                action="failed",
                fingerprint=fingerprint,
                state=IdempotencyState.FAILED_FINAL,
                metrics=self.store.metrics(),
            )

        if validate_fn:
            ok, reason = validate_fn(output)
            if not ok:
                rec = self.store.get(fingerprint) or record
                rec.request_state = IdempotencyState.FAILED_RETRYABLE
                rec.metadata["validation_error"] = reason
                self.store.put(rec)
                return IdempotentResult(
                    action="failed",
                    fingerprint=fingerprint,
                    state=IdempotencyState.FAILED_RETRYABLE,
                    metrics=self.store.metrics(),
                )

        result_ref = ""
        result_hash = ""
        if persist_fn:
            result_ref = persist_fn(output)
            if result_ref.endswith(".json"):
                ok, _ = validate_json_result(result_ref)
            else:
                ok, _ = validate_file_result(result_ref)
            if not ok:
                rec = self.store.get(fingerprint) or record
                rec.request_state = IdempotencyState.FAILED_RETRYABLE
                rec.metadata["persist_validation"] = "failed"
                self.store.put(rec)
                return IdempotentResult(
                    action="failed",
                    fingerprint=fingerprint,
                    state=IdempotencyState.FAILED_RETRYABLE,
                    metrics=self.store.metrics(),
                )
            result_hash = hash_artifact(result_ref) if Path(result_ref).is_file() else hash_text(str(output))
        else:
            result_hash = hash_text(str(output))

        rec = self.store.get(fingerprint) or record
        rec.request_state = IdempotencyState.SUCCEEDED
        rec.result_reference = result_ref
        rec.result_hash = result_hash
        rec.completed_at = time.time()
        self.store.put(rec)
        self.store.increment_metric("generation_completed")

        input_hash = fingerprint
        cp = self.checkpoint_store.create_checkpoint(
            job_id=job_id,
            stage=stage,
            input_hash=input_hash,
            output_hash=result_hash,
            result_reference=result_ref,
            state=JobState.VERIFYING,
        )
        self.checkpoint_store.save_checkpoint(cp)
        self.store.increment_metric("checkpoint_count")

        return IdempotentResult(
            action="execute",
            fingerprint=fingerprint,
            result_reference=result_ref,
            result_hash=result_hash,
            output=output,
            state=IdempotencyState.SUCCEEDED,
            metrics=self.store.metrics(),
        )

    def _validate_existing(self, record: IdempotencyRecord) -> tuple[bool, str]:
        if not record.result_reference:
            return False, "no_reference"
        ref = record.result_reference
        if ref.endswith(".json"):
            return validate_json_result(ref)
        return validate_file_result(ref, expected_hash=record.result_hash or "")

    def _wait_for_completion(
        self,
        fingerprint: str,
        *,
        timeout_sec: float = 30.0,
        poll_sec: float = 0.05,
    ) -> Optional[IdempotencyRecord]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            rec = self.store.get(fingerprint)
            if rec and rec.request_state == IdempotencyState.SUCCEEDED:
                return rec
            if rec and rec.request_state in (
                IdempotencyState.FAILED_FINAL,
                IdempotencyState.UNKNOWN,
            ):
                return rec
            time.sleep(poll_sec)
        return self.store.get(fingerprint)
