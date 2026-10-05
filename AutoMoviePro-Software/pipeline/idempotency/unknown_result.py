"""Unknown provider result reconciliation (BUILD-03)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pipeline.idempotency.result_validation import validate_file_result
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.store import IdempotencyRecord, IdempotencyStore

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationResult:
    resolved: bool
    new_state: IdempotencyState
    result_reference: str = ""
    result_hash: str = ""
    action: str = "none"
    reason: str = ""


def reconcile_unknown(
    store: IdempotencyStore,
    record: IdempotencyRecord,
    *,
    remote_job_lookup: Optional[dict[str, Any]] = None,
    local_artifact_path: str = "",
) -> ReconciliationResult:
    """
    Attempt safe reconciliation before blind retry.
    Does NOT call external APIs — uses local/ persisted evidence only.
    """
    if record.request_state != IdempotencyState.UNKNOWN:
        return ReconciliationResult(False, record.request_state, reason="not_unknown")

    # Check local artifact
    if local_artifact_path or record.result_reference:
        path = local_artifact_path or record.result_reference
        ok, reason = validate_file_result(path, expected_hash=record.result_hash or "")
        if ok:
            record.request_state = IdempotencyState.SUCCEEDED
            record.result_reference = path
            store.put(record)
            store.increment_metric("recovery_count")
            return ReconciliationResult(True, IdempotencyState.SUCCEEDED, path, record.result_hash, "reuse_local", reason)

    # Check remote job metadata (already persisted locally)
    if remote_job_lookup:
        status = str(remote_job_lookup.get("status") or "")
        remote_id = str(remote_job_lookup.get("remote_job_id") or "")
        if status in ("done", "completed") and remote_id:
            record.metadata["remote_job_id"] = remote_id
            record.request_state = IdempotencyState.UNKNOWN
            store.put(record)
            return ReconciliationResult(
                False,
                IdempotencyState.UNKNOWN,
                action="needs_provider_poll",
                reason="remote_done_but_local_missing",
            )

    logger.warning(
        "reconciliation unresolved fingerprint=%s stage=%s",
        record.fingerprint[:12],
        record.stage,
    )
    store.increment_metric("unknown_count")
    return ReconciliationResult(False, IdempotencyState.UNKNOWN, action="mark_unknown", reason="no_safe_evidence")
