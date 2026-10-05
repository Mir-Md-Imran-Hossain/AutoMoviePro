"""BUILD-03 idempotency, checkpoint, resume, and duplicate prevention."""
from pipeline.idempotency.states import IdempotencyState
from pipeline.idempotency.identity import (
    JobIdentity,
    StageIdentity,
    AttemptIdentity,
    ExecutionIdentity,
)
from pipeline.idempotency.fingerprint import compute_fingerprint, hash_artifact, hash_text
from pipeline.idempotency.store import IdempotencyStore, IdempotencyRecord
from pipeline.idempotency.executor import IdempotentExecutor, IdempotentResult
from pipeline.idempotency.checkpoint_store import CheckpointStore
from pipeline.idempotency.resume_resolver import ResumeResolver, ResumePlan
from pipeline.idempotency.retry_policy import RetryClass, classify_error, retry_decision
from pipeline.idempotency.metrics import IdempotencyMetrics

__all__ = [
    "IdempotencyState",
    "JobIdentity",
    "StageIdentity",
    "AttemptIdentity",
    "ExecutionIdentity",
    "compute_fingerprint",
    "hash_artifact",
    "hash_text",
    "IdempotencyStore",
    "IdempotencyRecord",
    "IdempotentExecutor",
    "IdempotentResult",
    "CheckpointStore",
    "ResumeResolver",
    "ResumePlan",
    "RetryClass",
    "classify_error",
    "retry_decision",
    "IdempotencyMetrics",
]
