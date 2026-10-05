"""Fail-closed intelligence gate (BUILD-04G-H)."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pipeline.intelligence.config import IntelligenceMode, ResearchMode, get_intelligence_mode, get_research_mode, require_fail_closed

logger = logging.getLogger(__name__)

GATE_BLOCKED_MARKER = "INTELLIGENCE_GATE_BLOCKED"


class GateVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_READY = "NOT_READY"


def evaluate_gate_result(result: dict[str, Any] | None, *, context: str = "") -> GateVerdict:
    if result is None:
        return GateVerdict.NOT_READY
    if result.get("gate_error"):
        return GateVerdict.UNKNOWN
    if result.get("accepted") is True:
        return GateVerdict.PASS
    reason = str(result.get("reason") or result.get("verdict") or "")
    if reason in ("UNKNOWN", "PROVIDER_UNAVAILABLE", "DUPLICATE_UNKNOWN"):
        return GateVerdict.UNKNOWN
    if reason in ("NOT_READY", "RESEARCH_REQUIRED", "RESERVE_DEPLETED"):
        return GateVerdict.NOT_READY
    return GateVerdict.FAIL


def block_if_not_pass(
    verdict: GateVerdict,
    *,
    context: str,
    detail: str = "",
    allow_development_bypass: bool = False,
) -> None:
    if verdict == GateVerdict.PASS:
        return
    if allow_development_bypass and get_intelligence_mode() == IntelligenceMode.DEVELOPMENT:
        logger.warning("INTELLIGENCE_GATE bypass (development): %s %s", context, detail)
        return
    msg = f"{GATE_BLOCKED_MARKER}: {context} verdict={verdict.value}"
    if detail:
        msg = f"{msg} detail={detail}"
    logger.error(msg)
    raise RuntimeError(msg)


def assert_production_intelligence_validated(
    *,
    passed: bool,
    context: str,
    detail: str = "",
) -> None:
    """Production mode: pipeline cannot proceed without a validated intelligence gate PASS."""
    if passed or not require_fail_closed():
        return
    msg = f"{GATE_BLOCKED_MARKER}: {context} no validated intelligence"
    if detail:
        msg = f"{msg} detail={detail}"
    logger.error(msg)
    raise RuntimeError(msg)


def resolve_research_use_mock(explicit_mock: bool | None = None) -> bool:
    if explicit_mock is not None:
        if explicit_mock and get_research_mode() == ResearchMode.LIVE and get_intelligence_mode() == IntelligenceMode.PRODUCTION:
            raise RuntimeError(f"{GATE_BLOCKED_MARKER}: mock research forbidden in production LIVE mode")
        return explicit_mock
    mode = get_research_mode()
    if mode == ResearchMode.MOCK:
        return True
    if mode == ResearchMode.LIVE:
        return False
    return False
