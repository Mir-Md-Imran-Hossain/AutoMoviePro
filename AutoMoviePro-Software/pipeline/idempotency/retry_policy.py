"""Bounded retry policy with exponential backoff (BUILD-03 / H3 cost bounds)."""
from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RetryClass(str, Enum):
    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"
    UNKNOWN = "UNKNOWN"


@dataclass
class RetryDecision:
    retry_class: RetryClass
    should_retry: bool
    attempt: int
    max_attempts: int
    delay_sec: float
    reason: str


# Documented nested-layer caps (H3 DEF-H3-001) — not a second retry engine.
DEFAULT_EXECUTOR_MAX_ATTEMPTS = 3
DEFAULT_GOOGLE_GATE_MAX_KEYS = 2
DEFAULT_GOOGLE_GATE_MAX_MODELS = 2  # only if AMP_GOOGLE_MULTI_MODEL=1; else 1
DEFAULT_TTS_RETRIES_PER_KEY = 2
DEFAULT_AGNES_SCENE_BUDGET = 2
DEFAULT_AV_RETRIES = 1
DEFAULT_REPAIR_CYCLES = 3


def worst_case_expensive_attempts(
    *,
    executor_max: int = DEFAULT_EXECUTOR_MAX_ATTEMPTS,
    gate_keys: int = DEFAULT_GOOGLE_GATE_MAX_KEYS,
    gate_models: int = 1,
    tts_per_key: int = DEFAULT_TTS_RETRIES_PER_KEY,
    agnes_budget: int = DEFAULT_AGNES_SCENE_BUDGET,
    av_retries: int = DEFAULT_AV_RETRIES,
    repair_cycles: int = DEFAULT_REPAIR_CYCLES,
) -> int:
    """Upper bound product of nested layers for one scene-equivalent unit of work."""
    return max(1, int(executor_max)) * max(1, int(gate_keys)) * max(1, int(gate_models)) * max(
        1, int(tts_per_key)
    ) * max(1, int(agnes_budget)) * max(1, int(av_retries)) * max(1, int(repair_cycles))


def classify_error(exc: BaseException) -> RetryClass:
    msg = str(exc).lower()
    non_retry = (
        "invalid",
        "authentication",
        "authorization",
        "unauthorized",
        "forbidden",
        "permission",
        "malformed",
        "validation",
        "config",
        "configuration",
        "not configured",
        "missing api",
        "missing key",
        "api key",
        "credential",
        "unsupported",
        "duplicate product blocked",
        "circuit open",
        "budget exceeded",
        "googlecircuitopen",
        "googlebudgetexceeded",
        "preflight",
        "login_required",
        "fail closed",
        "fail-closed",
    )
    unknown = ("timeout", "connection reset", "response lost", "unknown")
    retryable = (
        "rate_limit",
        "429",
        "503",
        "502",
        "temporary",
        "transient",
        "quota",
        "resource exhausted",
        "network",
    )
    for k in non_retry:
        if k in msg:
            return RetryClass.NON_RETRYABLE
    for k in unknown:
        if k in msg and "retry" not in msg:
            return RetryClass.UNKNOWN
    for k in retryable:
        if k in msg:
            return RetryClass.RETRYABLE
    # H3 DEF-H3-007: unlabeled errors are UNKNOWN (no expensive blind retry), not RETRYABLE
    return RetryClass.UNKNOWN


def compute_backoff(attempt: int, *, base: float = 1.0, cap: float = 60.0) -> float:
    exp = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0, exp * 0.1)
    return exp + jitter


def retry_decision(
    *,
    exc: Optional[BaseException],
    attempt: int,
    max_attempts: int = DEFAULT_EXECUTOR_MAX_ATTEMPTS,
) -> RetryDecision:
    if exc is None:
        return RetryDecision(RetryClass.RETRYABLE, False, attempt, max_attempts, 0.0, "no_error")
    rc = classify_error(exc)
    if rc == RetryClass.NON_RETRYABLE:
        return RetryDecision(rc, False, attempt, max_attempts, 0.0, str(exc)[:200])
    if rc == RetryClass.UNKNOWN:
        return RetryDecision(rc, False, attempt, max_attempts, 0.0, "unknown_requires_reconciliation")
    if attempt >= max_attempts:
        return RetryDecision(rc, False, attempt, max_attempts, 0.0, "max_attempts_reached")
    return RetryDecision(rc, True, attempt, max_attempts, compute_backoff(attempt), str(exc)[:200])
