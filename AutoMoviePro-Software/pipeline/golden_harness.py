"""Golden harness + failure injection (protocol §103–106)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


GOLDEN_CASES: List[Dict[str, Any]] = [
    {"id": "g01", "niche": "Ancient Civilizations", "topic": "Lost Library of Alexandria", "expect_family": "history"},
    {"id": "g02", "niche": "Ancient Civilizations", "topic": "Göbekli Tepe temples", "expect_family": "history"},
    {"id": "g03", "niche": "Ancient Civilizations", "topic": "iPhone 15 Pro", "expect_reject": True},
    {"id": "g04", "niche": "Gadget Reviews", "topic": "Sony WF-1000XM5", "expect_family": "gadget"},
    {"id": "g05", "niche": "Ancient Civilizations", "topic": "Antikythera Mechanism", "expect_family": "history"},
]


def run_golden_case(case: Dict[str, Any]) -> Dict[str, Any]:
    from pipeline.channel_dna import from_channel_row, validate_topic_against_dna
    from pipeline.topic_scoring import score_topic

    dna = from_channel_row({"niche": case.get("niche")})
    topic = str(case.get("topic") or "")
    gate = validate_topic_against_dna(topic, dna)
    score = score_topic(
        topic,
        dna,
        evergreen_verified=not bool(case.get("expect_reject")),
        freshness=0.8,
        trend_evidence="UNVERIFIED",
    )
    if case.get("expect_reject"):
        ok = (not gate.get("passed")) or (not score.get("passed"))
    else:
        ok = bool(gate.get("passed")) and dna.style_family == case.get("expect_family")
    return {"id": case.get("id"), "passed": ok, "gate": gate, "score_passed": score.get("passed"), "family": dna.style_family}


def run_golden_suite(limit: int = 5) -> Dict[str, Any]:
    rows = [run_golden_case(c) for c in GOLDEN_CASES[: max(1, limit)]]
    return {
        "passed": all(r.get("passed") for r in rows),
        "total": len(rows),
        "ok_count": sum(1 for r in rows if r.get("passed")),
        "cases": rows,
    }


def inject_failure(kind: str) -> Dict[str, Any]:
    """Deterministic failure injection for recovery tests."""
    kind = (kind or "").lower()
    mapping = {
        "api_429": {"error": "rate_limit", "http": 429, "retryable": True},
        "api_500": {"error": "server", "http": 500, "retryable": True},
        "timeout": {"error": "timeout", "retryable": True},
        "browser_crash": {"error": "browser_crash", "retryable": True},
        "ffmpeg_crash": {"error": "ffmpeg_nonzero", "retryable": True},
        "duplicate_upload": {"error": "already_uploaded", "retryable": False},
        "wrong_visual": {"error": "static_visual", "retryable": True},
        "db_lock": {"error": "lock_held", "retryable": True},
    }
    row = dict(mapping.get(kind) or {"error": "unknown", "retryable": False})
    row["injected"] = True
    row["kind"] = kind
    return row


def expected_recovery(kind: str) -> str:
    row = inject_failure(kind)
    if not row.get("retryable"):
        return "ABORT_NO_RETRY"
    if kind == "duplicate_upload":
        return "ABORT_NO_RETRY"
    if kind == "browser_crash":
        return "RECOVER_SESSION"
    if kind == "ffmpeg_crash":
        return "RETRY_FFMPEG"
    if kind in ("api_429", "api_500", "timeout"):
        return "BACKOFF_RETRY"
    return "BOUNDED_RETRY"
