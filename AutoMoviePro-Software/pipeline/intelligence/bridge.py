"""Intelligence bridge — production integration (BUILD-04G-H)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from pipeline.intelligence.config import get_intelligence_mode, get_research_mode
from pipeline.intelligence.contracts import ChannelProfile, ContentFormat
from pipeline.intelligence.duplicate import analyze_duplicate
from pipeline.intelligence.gate import (
    GateVerdict,
    block_if_not_pass,
    evaluate_gate_result,
    resolve_research_use_mock,
)
from pipeline.intelligence.candidates import candidate_from_dict
from pipeline.intelligence.orchestrator import run_topic_intelligence, select_topic_for_production
from pipeline.intelligence.scoring import channel_profile_from_row

logger = logging.getLogger(__name__)


def intelligence_duplicate_check(
    topic: str,
    *,
    channel_id: int | None = None,
    existing: list[str] | None = None,
) -> tuple[bool, dict[str, Any]]:
    ex = list(existing or [])
    result = analyze_duplicate(topic, ex)
    blocked = result.verdict.value in ("DUPLICATE", "UNKNOWN")
    return blocked, result.to_dict()


def enrich_channel_topic(
    work_dir: Path,
    channel: dict[str, Any],
    topic: str,
    *,
    video_type: str = "long",
    existing_topics: list[str] | None = None,
    blocked_topics: list[str] | None = None,
    use_mock_research: bool | None = None,
) -> dict[str, Any]:
    work_dir = Path(work_dir)
    profile = channel_profile_from_row(channel)
    fmt = ContentFormat.SHORT if video_type.lower() in ("short", "shorts", "reel") else ContentFormat.LONG
    ex = list(existing_topics or []) + list(blocked_topics or [])
    mock = resolve_research_use_mock(use_mock_research)

    try:
        blocked, dup = intelligence_duplicate_check(topic, channel_id=profile.channel_id, existing=ex)
        if blocked:
            return {"accepted": False, "reason": dup.get("verdict") or "DUPLICATE", "duplicate": dup, "topic": topic}

        candidate = candidate_from_dict({
            "title": topic,
            "canonical_topic": topic,
            "format": fmt.value,
            "channel_id": profile.channel_id,
            "niche": profile.niche,
            "source": "pipeline",
        })
        result = run_topic_intelligence(
            work_dir,
            profile,
            [candidate],
            job_id=work_dir.name,
            existing_topics=ex,
            do_research=True,
            use_mock_research=mock,
        )
        ev = (result.get("evaluated") or [{}])[0]
        score = ev.get("score") or {}
        if score.get("hard_blocked"):
            return {"accepted": False, "reason": score.get("block_reason"), "score": score, "topic": topic}
        return {
            "accepted": True,
            "topic": topic,
            "score": score,
            "intelligence": result,
            "research_mode": get_research_mode().value,
            "intelligence_mode": get_intelligence_mode().value,
        }
    except Exception as exc:
        logger.exception("intelligence enrich failed")
        return {"accepted": False, "reason": "UNKNOWN", "gate_error": str(exc), "topic": topic}


def run_intelligence_gate(
    work_dir: Path,
    channel: dict[str, Any],
    topic: str,
    *,
    video_type: str = "long",
    blocked_topics: list[str] | None = None,
    use_mock_research: bool | None = None,
) -> dict[str, Any]:
    result = enrich_channel_topic(
        work_dir, channel, topic,
        video_type=video_type,
        blocked_topics=blocked_topics,
        use_mock_research=use_mock_research,
    )
    verdict = evaluate_gate_result(result, context="topic_selection")
    result["gate_verdict"] = verdict.value
    return result


def pick_topic_from_reserve(
    work_dir: Path,
    channel: dict[str, Any],
    *,
    video_type: str = "long",
) -> Optional[str]:
    profile = channel_profile_from_row(channel)
    fmt = ContentFormat.SHORT if video_type.lower() in ("short", "shorts", "reel") else ContentFormat.LONG
    sel = select_topic_for_production(work_dir, profile, fmt=fmt)
    selected = sel.get("selected")
    if not selected:
        return None
    return str(selected.get("title") or selected.get("canonical_topic") or "")
